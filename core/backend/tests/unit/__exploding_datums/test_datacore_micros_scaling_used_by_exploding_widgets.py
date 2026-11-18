from __future__ import annotations

"""
E2E proof sheet: datacore micro scaling into datomaton widgets
==============================================================

Purpose
-------
This sheet proves that adding a new micro type to the base platform datacore
does not require hardcoded changes in datomaton widgets, multiframespec UI
lowering, partial-fill validation, mount/reexplode lifecycle handling, final
commit handling, or effective datum-shell hydration.

The sheet intentionally introduces a synthetic new micro type at test time:

    rating_e2e

and proves that it flows through:

    MICRO_TYPES
      -> multiframespec datum shell
      -> renderer-agnostic UI context
      -> DatumFillValidator raw semantic validation
      -> accepted-fill coercion for transition partial fills
      -> datomaton widget q["datum"] / q["partial_fill"]
      -> reexplode result["datum"]
      -> lifecycle memory page
      -> hydrated effective multiframespec shell

Core platform contract proved here
----------------------------------
There are two intentionally separate layers:

1. DatumFillValidator / parse_and_validate_macro_fill

   These validate raw macro fills. They enforce:
      - required micros, when requested
      - attached micro validators
      - attached macro validators
      - validator return-shape contract

   They do NOT own generic micro-type coercion. A direct call to
   DatumFillValidator.parse_and_validate_fill(...) returns the raw accepted
   macro value.

2. Runtime transition accepted-fill coercion

   Once a candidate fill has been accepted by the validator, the manual
   transition path canonicalizes accepted values through the datum's micro
   declarations and MICRO_TYPES. Therefore the transition helper returns:

      bundle["candidate"]              -> raw merged input
      bundle["partially_validated"]    -> accepted + canonical/coerced values

   Datomaton widgets should receive:
      q["raw_fill"]                    -> raw merged candidate
      q["partial_fill"]                -> canonical accepted partial fill

This separation is important because it keeps DatumFillValidator focused on
semantic validation while making runtime partial fills stable and type-safe for
widgets, lifecycle memory overlays, and final commits.

No production code should need to mention rating_e2e explicitly.
"""

import sys
import types
from typing import Any, Mapping

import pytest

from _thinkprogram._iomicrosTM.core.micro_registry import (
    MicroTypeDefinition,
    ValidatorPolicy,
    MICRO_TYPES,
)
from _thinkprogram._iomicrosTM.core.api_validation import DatumFillValidator
from _thinkprogram._iomicrosTM.core.api_fills import (
    build_datum_validator,
    datum_fill_data_meets_its_structural_micros_shell,
    coerce_accepted_macro_fill_for_datum,
    parse_validate_and_coerce_macro_fill,
)
from _thinkprogram._iomicrosTM.core.api_coercion import coerce_micro_value
from _thinkprogram._iomicrosTM.core.api_prefills import FormFillsLayerV1
from _thinkprogram._iomicrosTM.tiny_helpers import assert_dead_json

from __datomatonTM import (
    Q_SIGNAL_FILL,
    Q_SIGNAL_MOUNT,
    Q_STATUS_DONE,
    Q_STATUS_REEXPLODE,
    register_datum_widget_v1,
)
from __datomatonTM._eval import explode_datum_widget

from __multiframespecTM.api import (
    translate__multiframespec_to_ui_context,
)
from _thinkengine._app_table_engine._engine_runtime_fillspan_state_machine_mechanics.span_main_algos._span_fills_structural_and_semantic_gating import (
    _partially_validate_manual_datum_fill_for_transition_v1,
    _fully_validate_manual_datum_fill_for_commit_v1,
)
from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    apply_q_mount_batch_v1,
    apply_q_reexplode_batch_v1,
    get_latest_engine_form_page_data_read,
    hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory,
)


# ---------------------------------------------------------------------------
# Synthetic validator module used by dotted-path validator specs.
# ---------------------------------------------------------------------------

VALIDATOR_MODULE = "rating_e2e_validators"


def _unwrap(v: Any) -> Any:
    if isinstance(v, Mapping) and "value" in v:
        return v["value"]
    return v


def rating_between(v: Any, *, minimum: int = 1, maximum: int = 5):
    value = _unwrap(v)
    try:
        n = int(value)
    except Exception:
        return False, f"rating must be an integer between {minimum} and {maximum}"

    ok = int(minimum) <= n <= int(maximum)
    return ok, None if ok else f"rating must be between {minimum} and {maximum}"


def rating_even_macro(_self: Any, macro: Mapping[str, Any]):
    value = macro.get("score")
    try:
        n = int(_unwrap(value))
    except Exception:
        return False, "score must be integer-like"

    ok = (n % 2) == 0
    return ok, None if ok else "score must be even"


def install_rating_validator_module() -> None:
    mod = types.ModuleType(VALIDATOR_MODULE)
    mod.rating_between = rating_between
    mod.rating_even_macro = rating_even_macro
    sys.modules[VALIDATOR_MODULE] = mod


# ---------------------------------------------------------------------------
# Synthetic micro type.
# ---------------------------------------------------------------------------

MICRO_NAME = "rating_e2e"
WIDGET_NAME = "rating_e2e_widget"


def coerce_rating_e2e(raw: Any) -> int:
    if isinstance(raw, Mapping) and "value" in raw:
        raw = raw["value"]

    if isinstance(raw, bool):
        raise ValueError("rating_e2e does not accept bool")

    try:
        return int(raw)
    except Exception as exc:
        raise ValueError(f"rating_e2e expects int-like input, got {raw!r}") from exc


def cast_rating_to_str(raw: Any) -> str:
    return str(coerce_rating_e2e(raw))


def cast_rating_to_int(raw: Any) -> int:
    return coerce_rating_e2e(raw)


@pytest.fixture(autouse=True)
def install_rating_micro_type():
    """
    Install a brand-new micro type into the platform sheet for each test.

    This proves the downstream code is data-driven from MICRO_TYPES and datum
    shells rather than hardcoded to the current production micro list.
    """
    install_rating_validator_module()

    old = MICRO_TYPES.get(MICRO_NAME)

    MICRO_TYPES[MICRO_NAME] = MicroTypeDefinition(
        name=MICRO_NAME,
        description="Synthetic integer rating micro used only by scaling tests.",
        modality="llm",
        validators=(
            ValidatorPolicy(
                path=f"{VALIDATOR_MODULE}:rating_between",
                mandatory_enforced=True,
                arg_map={"minimum": "minimum", "maximum": "maximum"},
                guidance_channel="local_guidance",
            ),
        ),
        validator_modalities=(),
        python_types=(int,),
        coerce=coerce_rating_e2e,
        coerce_to_micro_types=("integer", "number", "text", "object-json"),
        python_casts={
            int: cast_rating_to_int,
            str: cast_rating_to_str,
        },
    )

    yield

    if old is None:
        MICRO_TYPES.pop(MICRO_NAME, None)
    else:
        MICRO_TYPES[MICRO_NAME] = old


# ---------------------------------------------------------------------------
# Shared datum/spec builders.
# ---------------------------------------------------------------------------

def rating_datum(*, lifecycle: Mapping[str, Any] | None = None) -> dict[str, Any]:
    datum = {
        "id": "D_RATING",
        "title": "Rating",
        "micros": [
            {
                "name": "score",
                "type": MICRO_NAME,
                "required": True,
                "args": {
                    "minimum": 1,
                    "maximum": 5,
                    "stars": 5,
                    "renderer_marker": "custom-rating-renderer-arg",
                },
                "validators": [
                    {
                        "path": f"{VALIDATOR_MODULE}:rating_between",
                        "args": {"minimum": 1, "maximum": 5},
                    }
                ],
                "style": {
                    "density": "compact",
                },
            },
            {
                "name": "note",
                "type": "text",
                "required": False,
            },
        ],
        "macro_validation_lambdas": [
            f"{VALIDATOR_MODULE}:rating_even_macro",
        ],
    }

    if lifecycle is not None:
        datum["lifecycle"] = dict(lifecycle)

    return datum


def rating_multiframespec(*, lifecycle: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "app_form_id": "FORM_RATING",
        "datums": [
            rating_datum(lifecycle=lifecycle),
        ],
        "frames": [
            {
                "id": "F_MAIN",
                "spans": [
                    {
                        "id": "S_MAIN",
                        "owns": ["D_RATING"],
                    }
                ],
            }
        ],
        "fills": {},
    }


def _rating_micro_resolver(sink_id: str, micro_name: str) -> str:
    """
    Resolver used by typed fill-layer proof.

    It is intentionally tiny and test-local. Production code should derive this
    from the effective datum shell.
    """
    if sink_id == "D_RATING" and micro_name in {
        "score",
        "second_score",
        "mounted_score",
    }:
        return MICRO_NAME
    return "text"


# ---------------------------------------------------------------------------
# 1. UI lowering proof: new micro survives renderer membrane.
# ---------------------------------------------------------------------------

def test_new_micro_type_survives_multiframespec_to_ui_context_without_hardcoding():
    fs = rating_multiframespec()

    ctx = translate__multiframespec_to_ui_context(
        fs,
        {
            "frame_id": "F_MAIN",
            "span_id": "S_MAIN",
            "readonly": False,
            "datum_widget_fills": {},
            "datum_widgets_on_this_span": ["D_RATING"],
            "session_metadata": {},
        },
    )

    assert_dead_json(ctx, path="ui_ctx")

    decl = ctx["datum_widget_decls"]["D_RATING"]
    fields = decl["datum_args"]["micro_input_fields"]

    score_micro = next(m for m in fields if m["name"] == "score")

    assert score_micro["type"] == MICRO_NAME
    assert score_micro["required"] is True
    assert score_micro["args"]["stars"] == 5
    assert score_micro["args"]["renderer_marker"] == "custom-rating-renderer-arg"
    assert score_micro["renderer_marker"] == "custom-rating-renderer-arg"
    assert score_micro["style"]["density"] == "compact"

    # The platform did not need a switch/case for rating_e2e.
    assert MICRO_NAME not in {"text", "number", "integer", "select", "email", "date"}


# ---------------------------------------------------------------------------
# 2. Datum validation proof: attached lambdas run; coercion lives elsewhere.
# ---------------------------------------------------------------------------

def test_new_micro_type_uses_attached_micro_macro_validators_but_datum_validator_does_not_coerce():
    """
    DatumFillValidator is the engine-facing semantic validator.

    Contract from api_validation/api_fills:
      - it enforces required micros
      - it runs attached micro validators
      - it runs attached macro validators
      - it returns the raw macro shape/value

    It does NOT canonicalize/coerce micro values. Micro-owned coercion lives in:
      - api_coercion.coerce_micro_value
      - api_fills.coerce_accepted_macro_fill_for_datum
      - api_fills.parse_validate_and_coerce_macro_fill
      - api_prefills.FormFillsLayerV1 when constructed with a micro_resolver
    """
    d = DatumFillValidator(
        id="D_RATING",
        title="Rating",
        micros=rating_datum()["micros"],
        macro_validation_lambdas=rating_datum()["macro_validation_lambdas"],
    )

    out = d.parse_and_validate_fill(
        raw={"score": "4", "note": "good"},
        enforce_required_micros=True,
        enforce_micro_lambdas=True,
        enforce_macro_lambdas=True,
    )

    # IMPORTANT: DatumFillValidator validates but returns raw values.
    assert out["score"] == "4"
    assert isinstance(out["score"], str)
    assert out["note"] == "good"

    # Prove the new micro type's coercer itself works through the proper coercion API.
    coerced = coerce_micro_value(
        src_micro_type=MICRO_NAME,
        dst_micro_type=MICRO_NAME,
        raw="4",
    )
    assert coerced == 4
    assert isinstance(coerced, int)

    # Prove the accepted-fill coercion API canonicalizes the validator-approved macro.
    accepted_coerced = coerce_accepted_macro_fill_for_datum(
        datum=rating_datum(),
        accepted=out,
    )
    assert accepted_coerced["score"] == 4
    assert isinstance(accepted_coerced["score"], int)
    assert accepted_coerced["note"] == "good"

    # Prove the combined parse+validate+coerce wrapper canonicalizes too.
    wrapped = parse_validate_and_coerce_macro_fill(
        datum=rating_datum(),
        raw={"score": "4", "note": "good"},
        enforce_required_micros=True,
        enforce_micro_lambdas=True,
        enforce_macro_lambdas=True,
    )
    assert wrapped["score"] == 4
    assert isinstance(wrapped["score"], int)
    assert wrapped["note"] == "good"

    # Prove the canonical fills layer can also coerce using a resolver.
    layer = FormFillsLayerV1.from_any(
        {"D_RATING": {"score": "4"}},
        kind="fill",
        micro_resolver=_rating_micro_resolver,
    )
    assert layer.get_value("D_RATING", "score") == 4
    assert isinstance(layer.get_value("D_RATING", "score"), int)

    with pytest.raises(Exception) as too_large:
        d.parse_and_validate_fill(
            raw={"score": "8"},
            enforce_required_micros=True,
            enforce_micro_lambdas=True,
            enforce_macro_lambdas=True,
        )
    assert "between 1 and 5" in str(too_large.value)

    with pytest.raises(Exception) as odd_macro:
        d.parse_and_validate_fill(
            raw={"score": "3"},
            enforce_required_micros=True,
            enforce_micro_lambdas=True,
            enforce_macro_lambdas=True,
        )
    assert "score must be even" in str(odd_macro.value)


def test_contract_lock_datum_validator_validates_but_does_not_coerce_custom_micros():
    """
    Contract lock.

    If this test starts failing because score becomes int, then production
    semantics changed: DatumFillValidator started coercing custom micro values.
    That would be a real platform contract change and should be reviewed.
    Runtime paths that need canonical values should use the explicit
    accepted-fill coercion layer instead.
    """
    datum = rating_datum()
    validator = build_datum_validator(datum)

    out = validator.parse_and_validate_fill(
        raw={"score": "4"},
        enforce_required_micros=True,
        enforce_micro_lambdas=True,
        enforce_macro_lambdas=True,
    )

    assert out == {"score": "4"}
    assert isinstance(out["score"], str)

    canonical = coerce_micro_value(
        src_micro_type=MICRO_NAME,
        dst_micro_type=MICRO_NAME,
        raw=out["score"],
    )
    assert canonical == 4
    assert isinstance(canonical, int)


# ---------------------------------------------------------------------------
# 3. Partial-fill proof: requiredness is separate from semantic validation.
# ---------------------------------------------------------------------------

def test_partial_fill_accepts_missing_required_micros_but_validates_present_new_micro():
    datum = rating_datum()
    validator = build_datum_validator(datum)

    # Missing required score is tolerated during partial validation.
    partial_missing = validator.parse_and_validate_fill(
        raw={"note": "draft only"},
        enforce_required_micros=False,
        enforce_micro_lambdas=True,
        enforce_macro_lambdas=False,
    )
    assert partial_missing == {"note": "draft only"}

    # The accepted-fill coercion layer preserves partial semantics:
    # absent required micros remain absent.
    partial_missing_coerced = coerce_accepted_macro_fill_for_datum(
        datum=datum,
        accepted=partial_missing,
    )
    assert partial_missing_coerced == {"note": "draft only"}

    # Present score still runs the new micro semantic validator.
    with pytest.raises(Exception) as bad_present_value:
        validator.parse_and_validate_fill(
            raw={"score": "9", "note": "bad score"},
            enforce_required_micros=False,
            enforce_micro_lambdas=True,
            enforce_macro_lambdas=False,
        )
    assert "between 1 and 5" in str(bad_present_value.value)


# ---------------------------------------------------------------------------
# 4. Transition helper proof: candidate -> canonical partial -> satisfaction.
# ---------------------------------------------------------------------------

def test_transition_partial_validation_bundle_for_new_micro_type():
    """
    Transition partial validation uses the final runtime pipeline:

        raw existing/provided values
            -> candidate macro fill
            -> DatumFillValidator partial acceptance
            -> accepted-fill coercion by datum micros + MICRO_TYPES
            -> DatumFillValidator re-run on canonical values
            -> structural satisfaction

    Therefore:
      - bundle["candidate"] preserves raw merged input;
      - bundle["partially_validated"] is canonical/coerced accepted data.
    """
    datum = rating_datum()
    validator = build_datum_validator(datum)

    bundle = _partially_validate_manual_datum_fill_for_transition_v1(
        fid="D_RATING",
        datum=datum,
        validator=validator,
        fill={
            "D_RATING": {
                "score": "4",
            }
        },
        existing={
            "D_RATING": {
                "note": "already here",
            }
        },
    )

    assert bundle["candidate"] == {
        "note": "already here",
        "score": "4",
    }

    # Candidate is raw merged input.
    assert bundle["candidate"]["score"] == "4"
    assert isinstance(bundle["candidate"]["score"], str)

    # Partially validated is accepted + canonical/coerced.
    assert bundle["partially_validated"]["score"] == 4
    assert isinstance(bundle["partially_validated"]["score"], int)
    assert bundle["partially_validated"]["note"] == "already here"
    assert bundle["structurally_satisfied"] is True

    # Full commit validation preserves canonical values.
    validated = _fully_validate_manual_datum_fill_for_commit_v1(
        fid="D_RATING",
        datum=datum,
        validator=validator,
        partially_validated=bundle["partially_validated"],
    )
    assert validated["score"] == 4
    assert isinstance(validated["score"], int)
    assert validated["note"] == "already here"

    # The micro registry coercion contract remains independently usable.
    canonical_score = coerce_micro_value(
        src_micro_type=MICRO_NAME,
        dst_micro_type=MICRO_NAME,
        raw=validated["score"],
    )
    assert canonical_score == 4
    assert isinstance(canonical_score, int)


def test_parse_validate_and_coerce_macro_fill_returns_canonical_custom_micro_values():
    """
    Direct proof of the combined helper used by runtime-style code that wants
    validated + canonical values in one call.
    """
    datum = rating_datum()

    out = parse_validate_and_coerce_macro_fill(
        datum=datum,
        raw={"score": "4", "note": "good"},
        enforce_required_micros=True,
        enforce_micro_lambdas=True,
        enforce_macro_lambdas=True,
    )

    assert out == {
        "score": 4,
        "note": "good",
    }
    assert isinstance(out["score"], int)


def test_partial_accepted_fill_coercion_coerces_present_custom_micro_but_allows_missing_required():
    """
    Accepted-fill coercion is partial-safe.

    It canonicalizes values that are present, but it does not invent missing
    required micros and does not enforce requiredness. Requiredness remains a
    validator/satisfaction concern.
    """
    datum = rating_datum()
    validator = build_datum_validator(datum)

    accepted_raw = validator.parse_and_validate_fill(
        raw={"note": "draft"},
        enforce_required_micros=False,
        enforce_micro_lambdas=True,
        enforce_macro_lambdas=False,
    )

    accepted = coerce_accepted_macro_fill_for_datum(
        datum=datum,
        accepted=accepted_raw,
    )

    assert accepted == {"note": "draft"}

    accepted_raw_2 = validator.parse_and_validate_fill(
        raw={"score": "4"},
        enforce_required_micros=False,
        enforce_micro_lambdas=True,
        enforce_macro_lambdas=False,
    )

    accepted_2 = coerce_accepted_macro_fill_for_datum(
        datum=datum,
        accepted=accepted_raw_2,
    )

    assert accepted_2 == {"score": 4}
    assert isinstance(accepted_2["score"], int)


# ---------------------------------------------------------------------------
# 5. Datomaton widget proof: widget sees new shell + canonical partial fill.
# ---------------------------------------------------------------------------

def test_datomaton_widget_receives_new_micro_shell_and_canonical_partial_fill():
    """
    Datomaton widgets receive the datum shell and the platform's partial fill.

    The widget eval function itself accepts whatever partial_fill the caller
    provides. The manual transition path is responsible for producing the
    canonical partial_fill. This test therefore builds partial_fill through the
    same transition helper used by the engine.

    Proven here:
      - q["datum"]["micros"] exposes the new micro type;
      - q["raw_fill"] exposes the raw merged candidate;
      - q["partial_fill"] exposes accepted + canonical/coerced data;
      - the widget did not need any rating_e2e hardcoding in the platform.
    """
    observed: dict[str, Any] = {}

    def widget(q: Mapping[str, Any]):
        score_micro = next(
            m for m in q["datum"]["micros"]
            if m["name"] == "score"
        )

        observed["micro_types"] = [
            m["type"] for m in q["datum"]["micros"]
        ]
        observed["score_micro_type"] = score_micro["type"]
        observed["raw_score_type"] = type(q["raw_fill"]["score"]).__name__
        observed["raw_score"] = q["raw_fill"]["score"]
        observed["partial_score_type"] = type(q["partial_fill"]["score"]).__name__
        observed["partial_score"] = q["partial_fill"]["score"]
        observed["structurally_satisfied"] = q["structurally_satisfied"]

        return {
            "status": Q_STATUS_DONE,
            "state": {
                "saw_rating_micro": MICRO_NAME in observed["micro_types"],
                "raw_score": observed["raw_score"],
                "partial_score": observed["partial_score"],
            },
            "message": {
                "level": "success",
                "text": "accepted",
            },
        }

    register_datum_widget_v1(WIDGET_NAME, widget, overwrite=True)

    datum = rating_datum(
        lifecycle={
            "widget": WIDGET_NAME,
            "max_reexplosions": 0,
        }
    )
    validator = build_datum_validator(datum)

    bundle = _partially_validate_manual_datum_fill_for_transition_v1(
        fid="D_RATING",
        datum=datum,
        validator=validator,
        fill={"D_RATING": {"score": "4"}},
        existing={"D_RATING": {}},
    )

    ev = explode_datum_widget(
        state={},
        form_id="FORM_RATING",
        frame_id="F_MAIN",
        span_id="S_MAIN",
        datum_id="D_RATING",
        datum=datum,
        raw_fill=bundle["candidate"],
        partial_fill=bundle["partially_validated"],
        prefill=None,
        structurally_satisfied=bundle["structurally_satisfied"],
        signal_kind=Q_SIGNAL_FILL,
    )

    assert ev.status == Q_STATUS_DONE
    assert ev.state["saw_rating_micro"] is True

    # raw_fill preserves submitted/merged user data.
    assert ev.state["raw_score"] == "4"
    assert observed["raw_score_type"] == "str"

    # partial_fill is canonical/coerced runtime data.
    assert ev.state["partial_score"] == 4
    assert observed["partial_score_type"] == "int"
    assert observed["partial_score"] == 4
    assert observed["score_micro_type"] == MICRO_NAME
    assert observed["structurally_satisfied"] is True


# ---------------------------------------------------------------------------
# 6. Reexplode proof: widget can introduce new current-effective micro shell.
# ---------------------------------------------------------------------------

def test_datomaton_reexplode_preserves_new_micro_type_in_effective_datum_shell():
    """
    Reexplode proof.

    The important E2E invariants are:

      - the widget sees canonical partial_fill for the original custom micro;
      - the widget can return a replacement datum shell containing another
        micro of the same custom type;
      - the replacement shell survives lifecycle memory and hydration;
      - the working fill overlay preserves canonical values.
    """
    def widget(q: Mapping[str, Any]):
        old_datum = dict(q["datum"])
        old_micros = list(old_datum["micros"])

        replacement = dict(old_datum)
        replacement["title"] = "Rating Reexploded"
        replacement["micros"] = old_micros + [
            {
                "name": "second_score",
                "type": MICRO_NAME,
                "required": False,
                "args": {"minimum": 1, "maximum": 5, "stars": 5},
                "validators": [
                    {
                        "path": f"{VALIDATOR_MODULE}:rating_between",
                        "args": {"minimum": 1, "maximum": 5},
                    }
                ],
            }
        ]

        return {
            "status": Q_STATUS_REEXPLODE,
            "datum": replacement,
            "fill": {
                # q["partial_fill"] came from the transition helper, so it is canonical.
                "score": q["partial_fill"]["score"],
                # This one is authored by the widget as an int.
                "second_score": 2,
            },
            "state": {"reexploded": True},
            "message": {
                "level": "info",
                "text": "added second_score",
            },
            "proc_notes": {
                "reason": "scale-new-micro-shell",
            },
        }

    register_datum_widget_v1(WIDGET_NAME, widget, overwrite=True)

    datum = rating_datum(
        lifecycle={
            "widget": WIDGET_NAME,
            "max_reexplosions": 1,
        }
    )
    validator = build_datum_validator(datum)

    bundle = _partially_validate_manual_datum_fill_for_transition_v1(
        fid="D_RATING",
        datum=datum,
        validator=validator,
        fill={"D_RATING": {"score": "4"}},
        existing={"D_RATING": {}},
    )

    state: dict[str, Any] = {}

    ev = explode_datum_widget(
        state=state,
        form_id="FORM_RATING",
        frame_id="F_MAIN",
        span_id="S_MAIN",
        datum_id="D_RATING",
        datum=datum,
        raw_fill=bundle["candidate"],
        partial_fill=bundle["partially_validated"],
        prefill=None,
        structurally_satisfied=bundle["structurally_satisfied"],
        signal_kind=Q_SIGNAL_FILL,
    )

    assert ev.status == Q_STATUS_REEXPLODE
    assert ev.reexplode_datum is not None
    assert any(
        m["name"] == "second_score" and m["type"] == MICRO_NAME
        for m in ev.reexplode_datum["micros"]
    )

    undo = apply_q_reexplode_batch_v1(
        state=state,
        form_id="FORM_RATING",
        frame_id="F_MAIN",
        span_id="S_MAIN",
        evaluations=[ev],
        working_fills={"D_RATING": ev.working_fill},
    )
    assert undo["kind"] == "__datum_lifecycle_incremental_undo_v1__"

    hydrated = hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory(
        multiframespec=rating_multiframespec(
            lifecycle={
                "widget": WIDGET_NAME,
                "max_reexplosions": 1,
            }
        ),
        state=state,
        form_id="FORM_RATING",
    )

    hydrated_datum = hydrated["datums"][0]
    assert hydrated_datum["title"] == "Rating Reexploded"
    assert any(
        m["name"] == "second_score" and m["type"] == MICRO_NAME
        for m in hydrated_datum["micros"]
    )

    latest = get_latest_engine_form_page_data_read(
        state=state,
        form_id="FORM_RATING",
        frame_id="F_MAIN",
        span_id="S_MAIN",
    )

    # Preserved from q["partial_fill"], which is canonical transition data.
    assert latest["D_RATING"]["score"] == 4
    assert isinstance(latest["D_RATING"]["score"], int)

    # Widget-authored int remains int.
    assert latest["D_RATING"]["second_score"] == 2
    assert isinstance(latest["D_RATING"]["second_score"], int)


# ---------------------------------------------------------------------------
# 7. Mount proof: mount_explode can introduce new micro shell before render.
# ---------------------------------------------------------------------------

def test_mount_explode_with_new_micro_type_commits_shell_and_working_fill_overlay():
    """
    Mount proof.

    A datomaton widget can reexplode on mount, before regular fill processing.
    The replacement shell may contain a custom micro type, and the mount working
    fill overlay may include canonical values for both original and newly
    introduced custom micros.
    """
    def mount_widget(q: Mapping[str, Any]):
        assert q["signal_kind"] == Q_SIGNAL_MOUNT
        assert q["ctx"]["is_mount"] is True
        assert any(m["type"] == MICRO_NAME for m in q["datum"]["micros"])

        replacement = dict(q["datum"])
        replacement["title"] = "Mounted Rating"
        replacement["micros"] = list(replacement["micros"]) + [
            {
                "name": "mounted_score",
                "type": MICRO_NAME,
                "required": False,
                "args": {"minimum": 1, "maximum": 5},
                "validators": [
                    {
                        "path": f"{VALIDATOR_MODULE}:rating_between",
                        "args": {"minimum": 1, "maximum": 5},
                    }
                ],
            }
        ]

        return {
            "status": Q_STATUS_REEXPLODE,
            "datum": replacement,
            "fill": {
                "score": 4,
                "mounted_score": 2,
            },
            "state": {"mounted": True},
            "message": {
                "level": "info",
                "text": "mount reexploded",
            },
            "proc_notes": {
                "mount": "introduced mounted_score",
            },
        }

    register_datum_widget_v1(WIDGET_NAME, mount_widget, overwrite=True)

    datum = rating_datum(
        lifecycle={
            "widget": WIDGET_NAME,
            "mount_explode": True,
            "max_reexplosions": 1,
        }
    )

    state: dict[str, Any] = {}

    ev = explode_datum_widget(
        state=state,
        form_id="FORM_RATING",
        frame_id="F_MAIN",
        span_id="S_MAIN",
        datum_id="D_RATING",
        datum=datum,
        raw_fill={},
        partial_fill={},
        prefill=None,
        structurally_satisfied=False,
        signal_kind=Q_SIGNAL_MOUNT,
        signal_info={
            "form_id": "FORM_RATING",
            "frame_id": "F_MAIN",
            "span_id": "S_MAIN",
            "datum_id": "D_RATING",
        },
    )

    assert ev.status == Q_STATUS_REEXPLODE
    assert ev.has_working_fill is True

    apply_q_mount_batch_v1(
        state=state,
        form_id="FORM_RATING",
        frame_id="F_MAIN",
        span_id="S_MAIN",
        evaluations=[ev],
        working_fills={"D_RATING": ev.working_fill},
    )

    hydrated = hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory(
        multiframespec=rating_multiframespec(
            lifecycle={
                "widget": WIDGET_NAME,
                "mount_explode": True,
                "max_reexplosions": 1,
            }
        ),
        state=state,
        form_id="FORM_RATING",
    )

    hydrated_datum = hydrated["datums"][0]
    assert hydrated_datum["title"] == "Mounted Rating"
    assert any(
        m["name"] == "mounted_score" and m["type"] == MICRO_NAME
        for m in hydrated_datum["micros"]
    )

    latest = get_latest_engine_form_page_data_read(
        state=state,
        form_id="FORM_RATING",
        frame_id="F_MAIN",
        span_id="S_MAIN",
    )
    assert latest["D_RATING"]["score"] == 4
    assert latest["D_RATING"]["mounted_score"] == 2


# ---------------------------------------------------------------------------
# 8. Final commit proof: commit helper preserves canonical values.
# ---------------------------------------------------------------------------

def test_final_commit_helper_revalidates_and_preserves_canonical_custom_micro_value():
    """
    Final commit proof.

    The final commit helper should not regress a canonical partial value back to
    raw. It should enforce requiredness, re-run validators, and return canonical
    values.
    """
    datum = rating_datum()
    validator = build_datum_validator(datum)

    partial_bundle = _partially_validate_manual_datum_fill_for_transition_v1(
        fid="D_RATING",
        datum=datum,
        validator=validator,
        fill={"D_RATING": {"score": "4", "note": "ready"}},
        existing={"D_RATING": {}},
    )

    assert partial_bundle["partially_validated"]["score"] == 4
    assert isinstance(partial_bundle["partially_validated"]["score"], int)

    committed = _fully_validate_manual_datum_fill_for_commit_v1(
        fid="D_RATING",
        datum=datum,
        validator=validator,
        partially_validated=partial_bundle["partially_validated"],
    )

    assert committed == {
        "score": 4,
        "note": "ready",
    }
    assert isinstance(committed["score"], int)


# ---------------------------------------------------------------------------
# 9. Negative proof: widgets cannot return malformed lifecycle packets.
# ---------------------------------------------------------------------------

def test_datomaton_widget_contract_rejects_bad_reexplode_without_datum():
    def bad_widget(_q: Mapping[str, Any]):
        return {
            "status": Q_STATUS_REEXPLODE,
            "state": {},
            "message": "bad",
            # Missing required result["datum"].
        }

    register_datum_widget_v1(WIDGET_NAME, bad_widget, overwrite=True)

    datum = rating_datum(
        lifecycle={
            "widget": WIDGET_NAME,
            "max_reexplosions": 1,
        }
    )

    with pytest.raises(Exception) as exc:
        explode_datum_widget(
            state={},
            form_id="FORM_RATING",
            frame_id="F_MAIN",
            span_id="S_MAIN",
            datum_id="D_RATING",
            datum=datum,
            raw_fill={"score": 4},
            partial_fill={"score": 4},
            prefill=None,
            structurally_satisfied=True,
            signal_kind=Q_SIGNAL_FILL,
        )

    assert "reexplode result must include datum" in str(exc.value)