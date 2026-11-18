# think-backend/tests/unit/engine/data/core/test_prefills_on_emitted_multiframespecs.py

from __future__ import annotations

"""
Pedagogical Sheet: Prefills on Emitted multiframespecs (Manual vs Skip vs no-skip)
============================================================================

This file is executable documentation focused on ONE kernel rule-set:

Manual vs skip is purely a function of span ownership + satisfaction.

(See original file text for full explanation; behavior unchanged.)

IMPORTANT: step fns must return a Mapping. To emit a form:
    return {"multiframespec": <multiframespec dict>, ...}
Tuple return shapes are not supported.
"""

import sys
import types
from typing import Any, Dict, Optional

import pytest

from _thinkengine.runme.runme_offline_debug_against_actionscript import run_session_against_script_headless
from __exceptions.engine import FatalEngineError
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
from __multiframespecTM.api import (
    normalize_prefill_validation_directive,
    validate_and_normalize_prefills,
    validate_prefill_addressing_only,
)


_VALIDATORS_MOD = "ped_prefills_validators"


def _assert_exc_type(exc: BaseException, name: str) -> None:
    """Assert exception type by name without importing the exception class."""
    assert exc.__class__.__name__ == name


class _Fakemultiframespec:
    def __init__(self, datums):
        self.datums = datums


def _install_validators() -> None:
    mod = types.ModuleType(_VALIDATORS_MOD)

    def _unwrap(v: Any) -> Any:
        if isinstance(v, dict) and "value" in v:
            return v["value"]
        return v

    def nonempty(v: Any):
        vv = _unwrap(v)
        ok = isinstance(vv, str) and vv.strip() != ""
        return ok, (None if ok else "must be non-empty")

    def alpha_only(v: Any):
        vv = _unwrap(v)
        ok = isinstance(vv, str) and vv.isalpha()
        return ok, (None if ok else "must be alpha-only")

    mod.nonempty = nonempty
    mod.alpha_only = alpha_only
    sys.modules[_VALIDATORS_MOD] = mod


def _multiframespec_name_form(*, fills: Optional[Dict[str, Any]] = None, no_skip: bool = False) -> Dict[str, Any]:
    frame_tags = ["no-skip"] if bool(no_skip) else []
    return {
        "app_form_id": "FORM_NAME",
        "datums": [
            {
                "id": "NAME",
                "title": "Your name",
                "micros": [
                    {
                        "name": "first",
                        "type": "text",
                        "required": True,
                        "tags": [],
                        "validators": [f"{_VALIDATORS_MOD}:nonempty", f"{_VALIDATORS_MOD}:alpha_only"],
                    },
                    {
                        "name": "last",
                        "type": "text",
                        "required": True,
                        "tags": [],
                        "validators": [f"{_VALIDATORS_MOD}:nonempty"],
                    },
                ],
                "tags": [],
            }
        ],
        "frames": [
            {
                "id": "FRAME_NAME",
                "title": "Name",
                "tags": frame_tags,
                "spans": [
                    {
                        "id": "SPAN_NAME",
                        "owns": ["NAME"],
                        "tags": [],
                    }
                ],
            }
        ],
        "fills": dict(fills or {}),
    }


def _step_emit_name_form(
    _state: Dict[str, Any],
    *,
    fills: Optional[Dict[str, Any]] = None,
    no_skip: bool = False,
    directive: Any = None,
) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    if directive is not None:
        patch["multiframespec_PREFILL_VALIDATE_VALUES"] = directive
    patch["multiframespec"] = _multiframespec_name_form(fills=fills, no_skip=bool(no_skip))
    return patch


def _step_noop(_state: Dict[str, Any]) -> Dict[str, Any]:
    return {}


@pytest.fixture(autouse=True)
def _setup() -> None:
    _install_validators()
    StepFnregistry.clear()

    StepFnregistry.register(
        name="pedpref.emit_name_form",
        fn=_step_emit_name_form,
        required_args=set(),
        optional_args={"fills", "no_skip", "directive"},
        overwrite=True,
    )
    StepFnregistry.register(
        name="pedpref.noop",
        fn=_step_noop,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )



# ---------------------------------------------------------------------------
# Extracted from test_fills_contract_core_cocktail_zoo.py:
# _multiframespec_fills_contract: addressing + directive policy semantics
# ---------------------------------------------------------------------------

def test_validate_prefill_addressing_only_unknown_datum_and_micro_key() -> None:
    fs = _Fakemultiframespec(
        datums=[
            {"id": "weight", "micros": [{"name": "value"}, {"name": "units"}]},
            {"id": "height", "micros": [{"name": "value"}]},
        ]
    )

    with pytest.raises(Exception) as e1:
        validate_prefill_addressing_only(fs=fs, prefills={"weigth": {"value": 1}})  # typo
    _assert_exc_type(e1.value, "FormFillsContractError")
    # Should include unknown datum id and likely a nearest hint
    assert "unknown datum id" in str(e1.value)

    with pytest.raises(Exception) as e2:
        validate_prefill_addressing_only(fs=fs, prefills={"weight": {"bogus": 1}})
    _assert_exc_type(e2.value, "FormFillsContractError")
    assert "unknown micro" in str(e2.value)
    assert "allowed micros" in str(e2.value)


def test_normalize_prefill_validation_directive_shapes() -> None:
    assert normalize_prefill_validation_directive(None) == {"enabled": False, "mode": "complete_only", "fields": None}
    assert normalize_prefill_validation_directive(False) == {"enabled": False, "mode": "complete_only", "fields": None}
    assert normalize_prefill_validation_directive(True) == {"enabled": True, "mode": "complete_only", "fields": None}

    d = normalize_prefill_validation_directive("strict")
    assert d["enabled"] is True and d["mode"] == "strict"

    d2 = normalize_prefill_validation_directive(["a", "b"])
    assert d2["enabled"] is True and d2["mode"] == "complete_only" and d2["fields"] == {"a", "b"}

    d3 = normalize_prefill_validation_directive({"mode": "complete_only", "fields": "x"})
    assert d3["enabled"] is True and d3["fields"] == {"x"}


def test_validate_and_normalize_prefills_strict_is_partial_safe() -> None:
    # strict => validate provided values, but do NOT enforce required micros
    fs = _Fakemultiframespec(
        datums=[
            {
                "id": "doc",
                "micros": [
                    {
                        "name": "title",
                        "required": True,
                        "validators": [
                            {"path": "_thinkprogram._iomicrosTM.validators.text:min_words", "args": {"min_words": 2}}
                        ],
                    },
                    {"name": "desc", "required": True},
                ],
            }
        ]
    )

    directive = normalize_prefill_validation_directive("strict")

    # Missing required "desc" is allowed in strict (partial-safe),
    # but provided "title" is validated.
    with pytest.raises(Exception) as e1:
        validate_and_normalize_prefills(
            fs=fs,
            prefills={"doc": {"title": "solo"}},  # fails min_words=2
            directive=directive,
        )
    _assert_exc_type(e1.value, "FormFillsContractError")
    assert "prefill validation failed" in str(e1.value)
    assert "at least 2 words" in str(e1.value)

    out = validate_and_normalize_prefills(
        fs=fs,
        prefills={"doc": {"title": "two words"}},  # ok
        directive=directive,
    )
    assert out["doc"]["title"] == "two words"


def test_validate_and_normalize_prefills_complete_only_validates_only_when_satisfied() -> None:
    fs = _Fakemultiframespec(
        datums=[
            {
                "id": "doc",
                "micros": [
                    {
                        "name": "title",
                        "required": True,
                        "validators": [
                            {"path": "_thinkprogram._iomicrosTM.validators.text:min_words", "args": {"min_words": 2}}
                        ],
                    },
                    {"name": "desc", "required": True},
                ],
            }
        ]
    )
    directive = normalize_prefill_validation_directive("complete_only")

    # Not satisfied => validation is skipped (even though title is invalid)
    out = validate_and_normalize_prefills(
        fs=fs,
        prefills={"doc": {"title": "solo"}},  # invalid, but missing desc => not satisfied => skip
        directive=directive,
    )
    assert out["doc"]["title"] == "solo"

    # Satisfied => validation runs and fails
    with pytest.raises(Exception) as e2:
        validate_and_normalize_prefills(
            fs=fs,
            prefills={"doc": {"title": "solo", "desc": "ok"}},  # satisfied => validate => fail
            directive=directive,
        )
    _assert_exc_type(e2.value, "FormFillsContractError")
    assert "at least 2 words" in str(e2.value)

    # Satisfied and valid => ok
    out2 = validate_and_normalize_prefills(
        fs=fs,
        prefills={"doc": {"title": "two words", "desc": "ok"}},
        directive=directive,
    )
    assert out2["doc"]["title"] == "two words"


def test_manual_form_fill_no_prefills_inserts_manual_step_for_missing_span() -> None:
    api = get_concrete_session_api()
    manifest = [
        {"public_step_name": "emit", "step_fn": "pedpref.emit_name_form", "fn_args": {"fills": {}, "no_skip": False}},
        {"public_step_name": "done", "step_fn": "pedpref.noop", "fn_args": {}},
    ]

    rr = run_session_against_script_headless(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata={},
        api=api,
        script=[
            {
                "action": "STEP",
                "until_stop": True,
                "expect": {
                    "kind": "MANUALFILLNEEDEDSTEP",
                    "form_id": "FORM_NAME",
                    "step": {"frame_id": "FRAME_NAME", "span_id": "SPAN_NAME"},
                    "datum_widgets_on_this_span_contains": ["NAME"],
                },
            },
            {"action": "STEP", "fill": {"NAME": {"first": "Ada", "last": "Lovelace"}}},
            {"action": "STEP", "until_stop": True, "stop_kinds": ["ATCOMPLETION"], "expect": {"kind": "ATCOMPLETION"}},
        ],
    )

    out = api.get_outputs(rr.session_id)
    assert out["form_prefills"] == {}
    assert out["form_fills"]["NAME"]["first"] == "Ada"
    assert out["form_fills"]["NAME"]["last"] == "Lovelace"


def test_manual_form_with_partial_prefills_still_inserts_manual_and_ui_shows_prefilled_values() -> None:
    api = get_concrete_session_api()
    manifest = [
        {
            "public_step_name": "emit",
            "step_fn": "pedpref.emit_name_form",
            "fn_args": {"fills": {"NAME": {"last": "Lovelace"}}, "no_skip": False},
        },
        {"public_step_name": "done", "step_fn": "pedpref.noop", "fn_args": {}},
    ]

    rr = run_session_against_script_headless(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata={},
        api=api,
        script=[
            {
                "action": "STEP",
                "until_stop": True,
                "expect": {
                    "kind": "MANUALFILLNEEDEDSTEP",
                    "step": {"frame_id": "FRAME_NAME", "span_id": "SPAN_NAME"},
                    "datum_widgets_on_this_span_contains": ["NAME"],
                },
                "form_expect": {
                    "form_id": "CURRENT",
                    "micro_merged": {
                        "NAME.first": None,
                        "NAME.last": "Lovelace",
                    },
                    "datum_sources": {"NAME": {"is_prefill_only": True, "has_any": True}},
                },
            },
            {"action": "STEP", "fill": {"NAME": {"first": "Ada"}}},
            {"action": "STEP", "until_stop": True, "stop_kinds": ["ATCOMPLETION"], "expect": {"kind": "ATCOMPLETION"}},
        ],
    )

    out = api.get_outputs(rr.session_id)
    assert out["form_prefills"]["NAME"]["last"] == "Lovelace"
    assert out["form_fills"]["NAME"]["first"] == "Ada"
    assert out["form_fills"]["NAME"]["last"] == "Lovelace"


def test_complete_prefills_are_skippable_no_manual_steps_inserted() -> None:
    api = get_concrete_session_api()
    manifest = [
        {
            "public_step_name": "emit",
            "step_fn": "pedpref.emit_name_form",
            "fn_args": {"fills": {"NAME": {"first": "Ada", "last": "Lovelace"}}, "no_skip": False},
        },
        {"public_step_name": "done", "step_fn": "pedpref.noop", "fn_args": {}},
    ]

    rr = run_session_against_script_headless(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata={},
        api=api,
        script=[
            {"action": "STEP", "until_stop": True, "stop_kinds": ["ATCOMPLETION"], "expect": {"kind": "ATCOMPLETION"}},
        ],
    )

    out = api.get_outputs(rr.session_id)
    assert out["form_prefills"]["NAME"]["first"] == "Ada"
    assert out["form_prefills"]["NAME"]["last"] == "Lovelace"
    assert out["form_fills"] == {}


def test_prefills_unknown_datum_id_raises_fatal() -> None:
    api = get_concrete_session_api()
    manifest = [
        {
            "public_step_name": "emit",
            "step_fn": "pedpref.emit_name_form",
            "fn_args": {"fills": {"NO_SUCH_DATUM": {"value": "x"}}, "no_skip": False},
        },
        {"public_step_name": "done", "step_fn": "pedpref.noop", "fn_args": {}},
    ]

    with pytest.raises(FatalEngineError):
        run_session_against_script_headless(
            manifest=manifest,
            initial_parameter_overrides={},
            session_metadata={},
            api=api,
            script=[{"action": "STEP"}],
        )


def test_prefills_unknown_micro_key_raises_fatal_even_if_value_validation_disabled() -> None:
    api = get_concrete_session_api()
    manifest = [
        {
            "public_step_name": "emit",
            "step_fn": "pedpref.emit_name_form",
            "fn_args": {"directive": False, "fills": {"NAME": {"not_a_micro": "oops"}}, "no_skip": False},
        },
        {"public_step_name": "done", "step_fn": "pedpref.noop", "fn_args": {}},
    ]

    with pytest.raises(FatalEngineError):
        run_session_against_script_headless(
            manifest=manifest,
            initial_parameter_overrides={},
            session_metadata={},
            api=api,
            script=[{"action": "STEP"}],
        )


def test_complete_only_default_validates_complete_prefills_and_rejects_invalid_values() -> None:
    api = get_concrete_session_api()
    manifest = [
        {
            "public_step_name": "emit",
            "step_fn": "pedpref.emit_name_form",
            "fn_args": {"fills": {"NAME": {"first": 444, "last": "Lovelace"}}, "no_skip": False},
        },
        {"public_step_name": "done", "step_fn": "pedpref.noop", "fn_args": {}},
    ]

    with pytest.raises(FatalEngineError):
        run_session_against_script_headless(
            manifest=manifest,
            initial_parameter_overrides={},
            session_metadata={},
            api=api,
            script=[{"action": "STEP"}],
        )