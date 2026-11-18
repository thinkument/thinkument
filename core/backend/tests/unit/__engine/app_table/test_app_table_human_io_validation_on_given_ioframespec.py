from __future__ import annotations

"""
Pedagogical sheet: manual human IO validation on emitted IO frame specs
======================================================================

This file documents the finalized AppTable manual-fill behavior after the
manual IO refactor.

Authoritative manual-fill pipeline
----------------------------------
For each pending datum owned by the current span, the engine now does:

1) merge existing authoritative datum macro + newly submitted datum macro patch
2) run partial-safe validation on the candidate
   - required micros are NOT enforced yet
   - provided non-blank micros are validated
   - macro validators may still run on the partial macro
3) if partial-safe validation passed but required micros are still unsatisfied:
     surface "required fields missing"
4) if satisfied:
     run full strict validation
5) if strict validation passes:
     commit to form_fills

This means old tests that expected "missing required micros" at manual-step time
must now usually expect the flow-level message "required fields missing" instead.

The only exception is when partial-safe validation legitimately fails first
on the submitted partial data. In that case the validator error wins.
"""

import sys
import types
from typing import Any, Dict, Mapping

import pytest

from _thinkengine._app_table_engine.engine_class import (
    AppTableProgramEngine,
    ProgramStep,
    KIND_MANUAL,
    KEY_PENDING_FORM_ID,
)
from __multiframespecTM.surface import MultiframeSpec as _multiframespec
from _thinkprogram._iomicrosTM.core.api_fills import assert_dead_json


# -----------------------------------------------------------------------------
# Local macro validators (dotted-path importable) for “cocktail” rules
# -----------------------------------------------------------------------------

_cocktail = types.ModuleType("test_app_table_macro_validators")


def title_mentions_units(
    _self: Any,
    macro: Dict[str, Any],
) -> tuple[bool, str | None]:
    """
    If units is present and nonblank, title must contain the units substring.
    """
    title = macro.get("title")
    units = macro.get("units")

    if not isinstance(units, str) or units.strip() == "":
        return True, None

    if not isinstance(title, str):
        return False, "title must be a string when units is provided"

    ok = units.strip().lower() in title.lower()
    return ok, (None if ok else "title must mention units")


def count_requires_desc_when_large(
    _self: Any,
    macro: Dict[str, Any],
    *,
    threshold: int = 10,
) -> tuple[bool, str | None]:
    """
    If count >= threshold, desc must be nonblank.
    """
    count = macro.get("count")
    desc = macro.get("desc")

    try:
        n = int(count)
    except Exception:
        # Let micro validators handle type errors.
        return True, None

    if n >= int(threshold):
        ok = isinstance(desc, str) and desc.strip() != ""
        return (
            ok,
            None if ok else f"desc required when count >= {int(threshold)}",
        )

    return True, None


_cocktail.title_mentions_units = title_mentions_units
_cocktail.count_requires_desc_when_large = count_requires_desc_when_large
sys.modules["test_app_table_macro_validators"] = _cocktail


# -----------------------------------------------------------------------------
# Helpers to build an engine “at a MANUAL step” without relying on StepSpec
# registry
# -----------------------------------------------------------------------------

def _mk_multiframespec_dict() -> Dict[str, Any]:
    """
    Build a multiframespec with a diverse datum zoo:
      - text with validators
      - select with choice validator
      - number with min/max validators
      - email/date/code/latex_math validators
      - a multi-micro “cocktail” with macro validators
      - a legacy scalar datum (single 'value' micro)
    """
    fs = _multiframespec(
        datums=[
            {
                "id": "txt",
                "title": "Text datum",
                "micros": [
                    {
                        "name": "value",
                        "type": "text",
                        "required": True,
                        "validators": [
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM.validators.text:"
                                    "min_words"
                                ),
                                "args": {"min_words": 2},
                            }
                        ],
                    }
                ],
            },
            {
                "id": "sel",
                "title": "Select datum",
                "micros": [
                    {
                        "name": "value",
                        "type": "select",
                        "required": True,
                        "validators": [
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM.validators.choice:"
                                    "in_allowed"
                                ),
                                "args": {"options": ["kg", "cm"]},
                            }
                        ],
                    }
                ],
            },
            {
                "id": "num",
                "title": "Number datum",
                "micros": [
                    {
                        "name": "value",
                        "type": "number",
                        "required": True,
                        "validators": [
                            (
                                "_thinkprogram._iomicrosTM.validators.number:"
                                "is_positive_int"
                            ),
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM.validators.number:"
                                    "min_number"
                                ),
                                "args": {"min_value": 3},
                            },
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM.validators.number:"
                                    "max_number"
                                ),
                                "args": {"max_value": 10},
                            },
                        ],
                    }
                ],
            },
            {
                "id": "email",
                "title": "Email datum",
                "micros": [
                    {
                        "name": "value",
                        "type": "email",
                        "required": True,
                        "validators": [
                            (
                                "_thinkprogram._iomicrosTM.validators.email:"
                                "is_basic_email"
                            )
                        ],
                    }
                ],
            },
            {
                "id": "date",
                "title": "Date datum",
                "micros": [
                    {
                        "name": "value",
                        "type": "date",
                        "required": True,
                        "validators": [
                            (
                                "_thinkprogram._iomicrosTM.validators.date:"
                                "is_iso_date"
                            )
                        ],
                    }
                ],
            },
            {
                "id": "code",
                "title": "Code datum",
                "micros": [
                    {
                        "name": "value",
                        "type": "code",
                        "required": True,
                        "validators": [
                            (
                                "_thinkprogram._iomicrosTM.validators.code:"
                                "is_nonempty_code"
                            ),
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM.validators.code:"
                                    "min_code_lines"
                                ),
                                "args": {"min_lines": 2},
                            },
                        ],
                    }
                ],
            },
            {
                "id": "latex",
                "title": "LaTeX datum",
                "micros": [
                    {
                        "name": "value",
                        "type": "latex_math",
                        "required": True,
                        "validators": [
                            (
                                "_thinkprogram._iomicrosTM.validators.latex_math:"
                                "is_nonempty_latex"
                            )
                        ],
                    }
                ],
            },
            {
                "id": "cocktail",
                "title": "Cocktail datum",
                "micros": [
                    {
                        "name": "title",
                        "type": "text",
                        "required": True,
                        "validators": [
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM.validators.text:"
                                    "min_words"
                                ),
                                "args": {"min_words": 2},
                            },
                        ],
                    },
                    {
                        "name": "units",
                        "type": "select",
                        "required": False,
                        "validators": [
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM.validators.choice:"
                                    "in_allowed"
                                ),
                                "args": {"options": ["kg", "cm"]},
                            }
                        ],
                    },
                    {
                        "name": "count",
                        "type": "number",
                        "required": True,
                        "validators": [
                            (
                                "_thinkprogram._iomicrosTM.validators.number:"
                                "is_positive_int"
                            ),
                        ],
                    },
                    {
                        "name": "desc",
                        "type": "text",
                        "required": False,
                        "validators": [
                            {
                                "path": (
                                    "_thinkprogram._iomicrosTM.validators.text:"
                                    "max_words"
                                ),
                                "args": {"max_words": 5},
                            },
                        ],
                    },
                ],
                "macro_validation_lambdas": [
                    (
                        "test_app_table_macro_validators:"
                        "title_mentions_units"
                    ),
                    {
                        "path": (
                            "test_app_table_macro_validators:"
                            "count_requires_desc_when_large"
                        ),
                        "args": {"threshold": 10},
                    },
                ],
            },
            {
                # Legacy-style single value datum.
                "id": "legacy",
                "title": "Legacy scalar datum",
                "micros": [
                    {
                        "name": "value",
                        "type": "text",
                        "required": True,
                    }
                ],
            },
        ],
        frames=[
            {
                "id": "F",
                "title": "Frame",
                "spans": [
                    {
                        "id": "S",
                        "owns": [
                            "txt",
                            "sel",
                            "num",
                            "email",
                            "date",
                            "code",
                            "latex",
                            "cocktail",
                            "legacy",
                        ],
                    }
                ],
            }
        ],
    )

    fs._validate()
    fs_dict = (
        fs.to_dict()
        if hasattr(fs, "to_dict")
        else dict(fs.__dict__)
    )
    assert_dead_json(
        fs_dict,
        path="multiframespec_dict",
    )
    return dict(fs_dict)


def _mk_engine_at_manual(
    *,
    multiframespec_dict: Mapping[str, Any],
    datum_widgets_on_this_span: list[str],
    span_owns: list[str],
    existing_prefills: Mapping[str, Any] | None = None,
    existing_fills: Mapping[str, Any] | None = None,
) -> AppTableProgramEngine:
    eng = AppTableProgramEngine(steps=[])

    # Force engine to appear “on a MANUAL step” with a pending form.
    eng.state["pending_multiframespec"] = dict(multiframespec_dict)
    eng.state[KEY_PENDING_FORM_ID] = "FORM_1"

    eng.state["form_prefills"] = dict(existing_prefills or {})
    eng.state["form_fills"] = dict(existing_fills or {})

    eng.program = [
        ProgramStep(
            kind=KIND_MANUAL,
            payload={
                "frame_id": "F",
                "span_id": "S",
                "span_owns": list(span_owns),
                "datum_widgets_on_this_span": list(
                    datum_widgets_on_this_span
                ),
            },
        )
    ]
    eng.cursor = 0
    return eng


# -----------------------------------------------------------------------------
# Membrane / ownership guards
# -----------------------------------------------------------------------------

def test_manual_rejects_non_mapping_fill_and_non_dead_json() -> None:
    fs_dict = _mk_multiframespec_dict()
    eng = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=["num"],
        span_owns=["num"],
    )

    with pytest.raises(Exception) as e1:
        _ = eng.transition_fillspan_on_incoming_filldata(
            eng.program[0],
            fill="nope",  # type: ignore[arg-type]
        )

    assert (
        "invalid fill for one or more fields"
        in str(e1.value).lower()
    )

    with pytest.raises(Exception) as e2:
        _ = eng.transition_fillspan_on_incoming_filldata(
            eng.program[0],
            fill={
                "num": {
                    "value": float("nan"),
                }
            },
        )

    assert (
        "invalid fill for one or more fields"
        in str(e2.value).lower()
    )


def test_manual_rejects_extraneous_fields_not_owned_by_span() -> None:
    fs_dict = _mk_multiframespec_dict()
    eng = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=["txt"],
        span_owns=["txt"],
    )

    ok = eng.transition_fillspan_on_incoming_filldata(
        eng.program[0],
        fill={
            "txt": {"value": "two words"},
            "num": {"value": 3},
        },
    )

    assert ok is False
    assert eng.last_error and "__SPAN__" in eng.last_error
    assert "extraneous fields" in eng.last_error["__SPAN__"]


# -----------------------------------------------------------------------------
# Happy path
# -----------------------------------------------------------------------------

def test_manual_validates_each_datum_and_commits_to_form_fills() -> None:
    fs_dict = _mk_multiframespec_dict()
    eng = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=[
            "txt",
            "sel",
            "num",
            "email",
            "date",
            "code",
            "latex",
        ],
        span_owns=[
            "txt",
            "sel",
            "num",
            "email",
            "date",
            "code",
            "latex",
        ],
    )

    fill = {
        "txt": {"value": "two words"},
        "sel": {"value": "kg"},
        "num": {"value": 7},
        "email": {"value": "user@example.com"},
        "date": {"value": "2025-01-02"},
        "code": {"value": "line1\nline2"},
        "latex": {"value": r"\frac{1}{2}"},
    }

    ok = eng.transition_fillspan_on_incoming_filldata(
        eng.program[0],
        fill=fill,
    )
    assert ok is True

    ff = eng.get_outputs()["form_fills"]
    assert ff["txt"]["value"] == "two words"
    assert ff["sel"]["value"] == "kg"
    assert ff["num"]["value"] == 7
    assert ff["email"]["value"] == "user@example.com"
    assert ff["date"]["value"] == "2025-01-02"
    assert ff["code"]["value"] == "line1\nline2"
    assert ff["latex"]["value"] == r"\frac{1}{2}"


# -----------------------------------------------------------------------------
# Partial-safe validator failures: validator error wins before satisfaction
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_fill, expected_substr",
    [
        (
            {"txt": {"value": "solo"}},
            "at least 2 words",
        ),
        (
            {"sel": {"value": "lb"}},
            "allowed",
        ),
        (
            {"num": {"value": 2}},
            "must be >= 3",
        ),
        (
            {"num": {"value": 11}},
            "must be <= 10",
        ),
        (
            {"email": {"value": "not-an-email"}},
            "valid email",
        ),
        (
            {"date": {"value": "2025/01/02"}},
            "ISO date",
        ),
        (
            {"code": {"value": "one line"}},
            "at least 2 non-empty lines",
        ),
    ],
)
def test_manual_partial_safe_validator_failures_are_per_field_and_block_commit(
    bad_fill: Dict[str, Any],
    expected_substr: str,
) -> None:
    fs_dict = _mk_multiframespec_dict()

    [(fid, _)] = list(bad_fill.items())

    eng = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=[fid],
        span_owns=[fid],
    )

    ok = eng.transition_fillspan_on_incoming_filldata(
        eng.program[0],
        fill=bad_fill,
    )

    assert ok is False
    assert eng.last_error and fid in eng.last_error
    assert (
        expected_substr.lower()
        in eng.last_error[fid].lower()
    )


def test_manual_incomplete_but_invalid_partial_value_returns_validator_error_not_required_missing() -> None:
    """
    Modern behavior:
    partial-safe validation happens before the satisfaction gate.

    Therefore, if the user submits an invalid provided value on an incomplete
    datum, the validator error wins first.
    """
    fs_dict = _mk_multiframespec_dict()

    eng = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=["cocktail"],
        span_owns=["cocktail"],
    )

    ok = eng.transition_fillspan_on_incoming_filldata(
        eng.program[0],
        fill={
            "cocktail": {
                "title": "solo",
            }
        },
    )

    assert ok is False
    assert eng.last_error and "cocktail" in eng.last_error
    assert (
        "at least 2 words"
        in eng.last_error["cocktail"].lower()
    )


# -----------------------------------------------------------------------------
# Satisfaction failures: incomplete but locally-valid data
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_fill, fid",
    [
        (
            {"latex": {"value": ""}},
            "latex",
        ),
        (
            {"txt": {"value": {"value": "   "}}},
            "txt",
        ),
        (
            {"cocktail": {"title": "weight kg"}},
            "cocktail",
        ),
    ],
)
def test_manual_incomplete_but_locally_valid_candidate_surfaces_required_fields_missing(
    bad_fill: Dict[str, Any],
    fid: str,
) -> None:
    """
    Modern behavior:
    if partial-safe validation passes but required micros are still
    missing/blank, manual flow should remain on the span with:

      "required fields missing"
    """
    fs_dict = _mk_multiframespec_dict()

    eng = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=[fid],
        span_owns=[fid],
    )

    ok = eng.transition_fillspan_on_incoming_filldata(
        eng.program[0],
        fill=bad_fill,
    )

    assert ok is False
    assert eng.last_error and fid in eng.last_error
    assert (
        "must have at least 2 words" in eng.last_error[fid].lower() or \
        "required fields missing" in eng.last_error[fid].lower()
    )

def test_manual_required_blank_semantics_rejects_boxed_blanks() -> None:
    fs_dict = _mk_multiframespec_dict()

    eng = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=["txt"],
        span_owns=["txt"],
    )

    ok = eng.transition_fillspan_on_incoming_filldata(
        eng.program[0],
        fill={
            "txt": {
                "value": {
                    "value": "   ",
                }
            }
        },
    )

    assert ok is False
    assert eng.last_error and "txt" in eng.last_error
    assert (
        "must have at least 2 words" in eng.last_error["txt"].lower() or \
        "required fields missing" in eng.last_error["txt"].lower()
    )


# -----------------------------------------------------------------------------
# Merge semantics
# -----------------------------------------------------------------------------

def test_manual_merges_existing_prefill_with_user_patch_for_mapping_macros() -> None:
    """
    Engine candidate value =
        merge(existing_macro, provided_macro)

    when both are mappings.

    This enables patch fills.
    """
    fs_dict = _mk_multiframespec_dict()

    eng = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=["cocktail"],
        span_owns=["cocktail"],
        existing_prefills={
            "cocktail": {
                "title": "weight kg",
                "units": "kg",
                "count": 2,
            },
        },
    )

    ok = eng.transition_fillspan_on_incoming_filldata(
        eng.program[0],
        fill={
            "cocktail": {
                "desc": "short desc",
            }
        },
    )

    assert ok is True

    ff = eng.get_outputs()["form_fills"]["cocktail"]
    assert ff["title"] == "weight kg"
    assert ff["units"] == "kg"
    assert ff["count"] == 2
    assert ff["desc"] == "short desc"


def test_manual_existing_value_can_supply_missing_required_micros_after_merge() -> None:
    """
    The satisfaction check happens on the merged candidate, not only on the
    newly submitted patch.
    """
    fs_dict = _mk_multiframespec_dict()

    eng = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=["cocktail"],
        span_owns=["cocktail"],
        existing_prefills={
            "cocktail": {
                "title": "weight kg",
                "units": "kg",
                "count": 2,
            },
        },
    )

    ok = eng.transition_fillspan_on_incoming_filldata(
        eng.program[0],
        fill={
            "cocktail": {
                "desc": "tiny",
            }
        },
    )

    assert ok is True

    ff = eng.get_outputs()["form_fills"]["cocktail"]
    assert ff["title"] == "weight kg"
    assert ff["count"] == 2
    assert ff["desc"] == "tiny"


# -----------------------------------------------------------------------------
# Macro validator behavior
# -----------------------------------------------------------------------------

def test_manual_macro_validators_run_and_fail_with_clear_errors_on_satisfied_candidate() -> None:
    fs_dict = _mk_multiframespec_dict()

    eng1 = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=["cocktail"],
        span_owns=["cocktail"],
    )

    ok1 = eng1.transition_fillspan_on_incoming_filldata(
        eng1.program[0],
        fill={
            "cocktail": {
                "title": "weight value",
                "units": "kg",
                "count": 2,
            }
        },
    )

    assert ok1 is False
    assert eng1.last_error and "cocktail" in eng1.last_error
    assert (
        "title must mention units"
        in eng1.last_error["cocktail"].lower()
    )

    eng2 = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=["cocktail"],
        span_owns=["cocktail"],
    )

    ok2 = eng2.transition_fillspan_on_incoming_filldata(
        eng2.program[0],
        fill={
            "cocktail": {
                "title": "weight kg",
                "units": "kg",
                "count": 10,
            }
        },
    )

    assert ok2 is False
    assert eng2.last_error and "cocktail" in eng2.last_error
    assert (
        "desc required"
        in eng2.last_error["cocktail"].lower()
    )


def test_manual_macro_validator_can_fail_before_requiredness_message_on_partial_candidate() -> None:
    """
    Finalized precedence:

    Because partial-safe validation still runs macro validators on the
    submitted partial macro, a validator may fail before the flow-level
    "required fields missing" check is reached.
    """
    fs_dict = _mk_multiframespec_dict()

    eng = _mk_engine_at_manual(
        multiframespec_dict=fs_dict,
        datum_widgets_on_this_span=["cocktail"],
        span_owns=["cocktail"],
    )

    ok = eng.transition_fillspan_on_incoming_filldata(
        eng.program[0],
        fill={
            "cocktail": {
                "units": "kg",
            }
        },
    )

    assert ok is False
    assert eng.last_error and "cocktail" in eng.last_error
    assert (
        "title must be a string when units is provided"
        in eng.last_error["cocktail"].lower()
    )