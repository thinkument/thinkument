# think-backend/tests/wipp/engine/app_tables/test_app_table_pedagogy_sheet.py

from __future__ import annotations

"""
App Table Pedagogy Sheet (Ultimate Remote Control)
==================================================

This file is executable documentation for app developers.

If you understand (and can keep passing) the scenarios in this file, you can build
apps confidently on top of thinkengine._app_table_engine’s App Table runtime.

--------------------------------------------------------------------
REMOTE CONTROL SURFACES (what app devs control)
--------------------------------------------------------------------

1) App Table manifest
   - You write: list[{public_step_name, step_fn, fn_args}] OR {"steps":[...]}
   - Engine does: dead-JSON validation, uniqueness checks, step_fn lookup, args validation

2) Step fn registration
   - You register: name -> callable + required_args/optional_args
   - Engine does: validates fn exists, validates fn_args match the spec

3) Step fn contract (the “output remote control”)
   - You return: patch (a Mapping)
   - Engine does:
       - applies patch (dead-JSON enforced for state mutations)
       - forbids patching reserved engine keys
       - if multiframespec emitted via patch["multiframespec"]: records it, merges prefills, expands IO steps

   Canonical emission keys:
       - patch["multiframespec"] = <multiframespec dict>          (L1)
       - patch["render_contract"] = <any>             (L2, lowered by compiler)

   NOTE: tuple return shapes are not supported.

4) Machine state (what you can read/write)
   - You own: all non-reserved keys (app globals)
   - Engine owns: forms lifecycle + io memory (pending_multiframespec, forms_emitted, form_prefills, form_fills, ...)

5) multiframespec design
   - You control: datums, micros, validators, frames/spans, span owns, tags, prefills
   - Engine does:
       - expands forms into MANUAL steps where required micros missing
       - validates fills

6) Manual fill semantics
   - You (UI/user) provide: fill payload dict[datum_id -> macro_value]
   - Engine enforces:
       - dead-JSON membrane
       - no extraneous fields outside span_owns
       - validates datum_widgets_on_this_span only
       - merges partial micro dicts

7) ui/control/page_flow_controller path (optional)
   - UI renders dotted micro names (FID.micro)
   - page_flow_controller collapses dotted keys into macro fill payloads for backend

8) Undo
   - You can call undo
   - Engine restores exact state and collapses inserted MANUAL steps

--------------------------------------------------------------------
WHAT YOU CANNOT DO (hard constraints)
--------------------------------------------------------------------
- Patch engine-owned keys (pending_multiframespec, form_fills, etc.).
- Return non-dead-JSON values anywhere (manifest, patch, multiframespec, fills).
- Emit duplicate form_id within a session timeline.
- During MANUALFILLNEEDEDSTEP, submit extraneous fields outside span_owns.

--------------------------------------------------------------------
PREFILL VALIDATION DIRECTIVE (important knob)
--------------------------------------------------------------------
Step fns may set:
    multiframespec_PREFILL_VALIDATE_VALUES = <directive>

This is consumed by the engine (never appears in globals) and controls whether
prefill *values* are validated. Addressing is always validated.

Directive shapes:
- False / None: disable value validation (addressing still checked)
- True: enable in default mode "complete_only"
- "complete_only": validate only when all required micros are present
- "strict": validate always (partial required micros rejected)
- ["FIELD1","FIELD2"]&#58; validate only those fields (complete_only semantics)
- {"FIELD": true, "OTHER": false}: validate truthy subset (complete_only)
- {"mode":"strict","fields":[...]}: explicit schema
"""

import sys
import types
from typing import Any, Dict, Optional

import pytest

from _thinkengine._parsing.app_table_program_parser import parse_and_validate_app_table
from __exceptions.engine import AppTableParserValidatorError, FatalEngineError, InvalidExternalFillError
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_form_fill_info,
    get_form_prefills,
    get_form_fills,
    get_globals,
    get_fills_snapshot_from_app_table_state,
    query_runtime_writes,
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api

from _thinkengine.runme.runme_offline_debug_against_actionscript import run_session_against_script_headless, SessionProgramScriptedHeadlessRunner



_VALIDATORS_MOD = "app_table_pedagogy_validators"


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

    def is_year(v: Any):
        vv = _unwrap(v)
        try:
            y = int(vv)
            ok = 1500 <= y <= 2100
        except Exception:
            ok = False
        return ok, (None if ok else "must be a valid year")

    def is_positive_int(v: Any):
        vv = _unwrap(v)
        try:
            ok = int(vv) > 0
        except Exception:
            ok = False
        return ok, (None if ok else "must be a positive integer")

    def is_uppercase(v: Any):
        vv = _unwrap(v)
        ok = isinstance(vv, str) and vv.isupper()
        return ok, (None if ok else "must be uppercase")

    mod.nonempty = nonempty
    mod.is_year = is_year
    mod.is_positive_int = is_positive_int
    mod.is_uppercase = is_uppercase

    sys.modules[_VALIDATORS_MOD] = mod


def _multiframespec_identity(*, app_form_id: Optional[str], prefill_last: Optional[str]) -> Dict[str, Any]:
    fills: Dict[str, Any] = {}
    if prefill_last is not None:
        fills["NAME"] = {"last": str(prefill_last)}

    fs: Dict[str, Any] = {
        "datums": [
            {
                "id": "NAME",
                "title": "Your name",
                "micros": [
                    {"name": "first", "type": "text", "required": True, "validators": [f"{_VALIDATORS_MOD}:nonempty"]},
                    {"name": "last", "type": "text", "required": True, "validators": [f"{_VALIDATORS_MOD}:nonempty"]},
                ],
            },
            {
                "id": "DOB",
                "title": "Date of birth",
                "micros": [
                    {"name": "day", "type": "text", "required": True, "validators": [f"{_VALIDATORS_MOD}:nonempty"]},
                    {"name": "month", "type": "text", "required": True, "validators": [f"{_VALIDATORS_MOD}:nonempty"]},
                    {"name": "year", "type": "text", "required": True, "validators": [f"{_VALIDATORS_MOD}:is_year"]},
                ],
            },
            {
                "id": "AGE",
                "title": "Age",
                "micros": [
                    {"name": "value", "type": "number", "required": True, "validators": [f"{_VALIDATORS_MOD}:is_positive_int"]}
                ],
            },
        ],
        "frames": [
            {
                "id": "IDENTITY",
                "title": "Identity",
                "spans": [
                    {"id": "S_NAME", "owns": ["NAME"]},
                    {"id": "S_DOB", "owns": ["DOB"]},
                ],
            },
            {
                "id": "REVIEW",
                "title": "Review",
                "tags": ["no-skip"],
                "spans": [{"id": "S_REVIEW", "owns": []}],
            },
            {
                "id": "AGE_FRAME",
                "title": "Age",
                "spans": [{"id": "S_AGE", "owns": ["AGE"]}],
            },
        ],
        "fills": fills,
    }
    if app_form_id is not None:
        fs["app_form_id"] = str(app_form_id)
    return fs


def _multiframespec_name_only(*, app_form_id: str = "FORM_NAME_ONLY", prefill: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "app_form_id": str(app_form_id),
        "datums": [
            {
                "id": "NAME",
                "title": "Name",
                "micros": [
                    {"name": "first", "type": "text", "required": True, "validators": [f"{_VALIDATORS_MOD}:nonempty"]},
                    {"name": "last", "type": "text", "required": True, "validators": [f"{_VALIDATORS_MOD}:nonempty"]},
                ],
            }
        ],
        "frames": [
            {"id": "F", "title": "F", "spans": [{"id": "S", "owns": ["NAME"]}]},
        ],
        "fills": dict(prefill or {}),
    }


def _multiframespec_two_fields_for_subset_validation(*, prefill_a: Any, prefill_b: Any) -> Dict[str, Any]:
    return {
        "app_form_id": "FORM_SUBSET_VALIDATE",
        "datums": [
            {
                "id": "FIELD_A",
                "title": "A",
                "micros": [{"name": "value", "type": "text", "required": True, "validators": [f"{_VALIDATORS_MOD}:is_uppercase"]}],
            },
            {
                "id": "FIELD_B",
                "title": "B",
                "micros": [{"name": "value", "type": "text", "required": True, "validators": [f"{_VALIDATORS_MOD}:is_uppercase"]}],
            },
        ],
        "frames": [
            {"id": "F", "title": "F", "spans": [{"id": "S", "owns": ["FIELD_A", "FIELD_B"]}]},
        ],
        "fills": {"FIELD_A": {"value": prefill_a}, "FIELD_B": {"value": prefill_b}},
    }


def _step_patch_only_counter(state: Dict[str, Any], *, label: str = "x") -> Dict[str, Any]:
    n = int(state.get("counter", 0) or 0) + 1
    seen = list(state.get("labels", []) or [])
    seen.append(str(label))
    return {"counter": n, "labels": seen}


def _step_state_mutation_is_ignored(state: Dict[str, Any]) -> Dict[str, Any]:
    state["MUTATED_IN_PLACE"] = True  # ignored by engine
    return {}


def _step_emit_identity_form(
    state: Dict[str, Any],
    *,
    prefill_last: Optional[str] = None,
    explicit_form_id: bool = False,
    also_prefill_age: Optional[int] = None,
) -> Dict[str, Any]:
    patch: Dict[str, Any] = {"started": True}
    if also_prefill_age is not None:
        patch["debug_requested_age_prefill"] = int(also_prefill_age)

    app_form_id = "FORM_IDENTITY" if explicit_form_id else None
    fs = _multiframespec_identity(app_form_id=app_form_id, prefill_last=prefill_last)

    if also_prefill_age is not None:
        fs = dict(fs)
        fs_fills = dict(fs.get("fills") or {})
        fs_fills["AGE"] = {"value": int(also_prefill_age)}
        fs["fills"] = fs_fills

    patch["multiframespec"] = fs
    return patch


def _step_commit_identity(state: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(state.get("form_prefills") or {})
    merged.update(state.get("form_fills") or {})

    name = merged.get("NAME") or {}
    dob = merged.get("DOB") or {}
    age = merged.get("AGE") or {}

    return {
        "committed": True,
        "full_name": f"{name.get('first','')} {name.get('last','')}".strip(),
        "dob": dict(dob) if isinstance(dob, dict) else dob,
        "age": int(age.get("value")) if isinstance(age, dict) and "value" in age else None,
    }


def _step_emit_name_prefill_with_directive(_state: Dict[str, Any], *, directive: Any, prefill_last: Optional[str]) -> Dict[str, Any]:
    patch = {"multiframespec_PREFILL_VALIDATE_VALUES": directive}
    fs = _multiframespec_name_only(prefill={"NAME": {"last": str(prefill_last)}} if prefill_last is not None else {})
    patch["multiframespec"] = fs
    return patch


def _step_emit_prefill_with_micro_typo(_state: Dict[str, Any]) -> Dict[str, Any]:
    patch = {"multiframespec_PREFILL_VALIDATE_VALUES": False}
    fs = _multiframespec_name_only(prefill={"NAME": {"not_a_micro": "oops"}})
    patch["multiframespec"] = fs
    return patch


def _step_emit_subset_prefill_validation(_state: Dict[str, Any], *, directive: Any) -> Dict[str, Any]:
    patch = {"multiframespec_PREFILL_VALIDATE_VALUES": directive}
    fs = _multiframespec_two_fields_for_subset_validation(prefill_a="ok", prefill_b="OK")
    patch["multiframespec"] = fs
    return patch


def _step_emit_duplicate_form_id(_state: Dict[str, Any], *, form_id: str) -> Dict[str, Any]:
    return {"multiframespec": _multiframespec_name_only(app_form_id=str(form_id), prefill={})}


def _step_introspect_current_form_into_globals(state: Dict[str, Any], *, form_id: str) -> Dict[str, Any]:
    info = get_form_fill_info(state, str(form_id))
    datums = info.get("datums") or {}
    summary = {}
    if isinstance(datums, dict):
        for fid, d in datums.items():
            if not isinstance(d, dict):
                continue
            src = d.get("sources") or {}
            summary[fid] = {
                "has_any": bool(src.get("has_any")),
                "is_prefill_only": bool(src.get("is_prefill_only")),
                "is_io_only": bool(src.get("is_io_only")),
                "is_mixed": bool(src.get("is_mixed")),
            }
    return {"introspection": summary}


def _step_write_blob_and_scalar(
    _state: Dict[str, Any],
    *,
    group: str,
    enabled: bool = False,
    blob_chars: int = 0,
) -> Dict[str, Any]:
    return {
        "group": str(group),
        "enabled": bool(enabled),
        "blob": "x" * int(blob_chars),
    }


def _step_query_runtime_writes(
    state: Dict[str, Any],
    *,
    query: Dict[str, Any],
    out_key: str = "query_result",
) -> Dict[str, Any]:
    return {str(out_key): query_runtime_writes(state, query)}



@pytest.fixture(autouse=True)
def _setup_backend_and_registry():
    _install_validators()
    StepFnregistry.clear()

    StepFnregistry.register(name="ped.patch_only_counter", fn=_step_patch_only_counter, required_args=set(), optional_args={"label"}, overwrite=True)
    StepFnregistry.register(name="ped.state_mutation_is_ignored", fn=_step_state_mutation_is_ignored, required_args=set(), optional_args=set(), overwrite=True)
    StepFnregistry.register(name="ped.emit_identity_form", fn=_step_emit_identity_form, required_args=set(), optional_args={"prefill_last", "explicit_form_id", "also_prefill_age"}, overwrite=True)
    StepFnregistry.register(name="ped.commit_identity", fn=_step_commit_identity, required_args=set(), optional_args=set(), overwrite=True)
    StepFnregistry.register(name="ped.emit_name_prefill_with_directive", fn=_step_emit_name_prefill_with_directive, required_args=set(), optional_args={"directive", "prefill_last"}, overwrite=True)
    StepFnregistry.register(name="ped.emit_prefill_with_micro_typo", fn=_step_emit_prefill_with_micro_typo, required_args=set(), optional_args=set(), overwrite=True)
    StepFnregistry.register(name="ped.emit_subset_prefill_validation", fn=_step_emit_subset_prefill_validation, required_args=set(), optional_args={"directive"}, overwrite=True)
    StepFnregistry.register(name="ped.emit_duplicate_form_id", fn=_step_emit_duplicate_form_id, required_args=set(), optional_args={"form_id"}, overwrite=True)
    StepFnregistry.register(name="ped.introspect_current_form_into_globals", fn=_step_introspect_current_form_into_globals, required_args=set(), optional_args={"form_id"}, overwrite=True)
    StepFnregistry.register(name="ped.write_blob_and_scalar", fn=_step_write_blob_and_scalar, required_args={"group"}, optional_args={"enabled", "blob_chars"}, overwrite=True)
    StepFnregistry.register(name="ped.query_runtime_writes", fn=_step_query_runtime_writes, required_args={"query"}, optional_args={"out_key"}, overwrite=True)


def test_manifest_accepts_wrapper_shape_and_patch_only_steps_complete_without_manual():
    api = get_concrete_session_api()

    manifest = {
        "steps": [
            {"public_step_name": "c1", "step_fn": "ped.patch_only_counter", "fn_args": {"label": "a"}},
            {"public_step_name": "c2", "step_fn": "ped.patch_only_counter", "fn_args": {"label": "b"}},
        ]
    }

    rr = run_session_against_script_headless(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata={},
        api=api,
        script=[
            {"action": "STEP", "until_stop": True, "stop_kinds": ["ATCOMPLETION"], "expect": {"kind": "ATCOMPLETION"}},
        ],
    )

    out = api.get_outputs(rr.ctx["session_id"])
    assert out["globals"]["counter"] == 2
    assert out["globals"]["labels"] == ["a", "b"]
    assert out["form_prefills"] == {}
    assert out["form_fills"] == {}


def test_manifest_parse_rejects_unknown_step_fn_and_duplicate_public_step_names_and_bad_args():
    with pytest.raises(AppTableParserValidatorError):
        parse_and_validate_app_table([{"public_step_name": "x", "step_fn": "nope", "fn_args": {}}])

    with pytest.raises(AppTableParserValidatorError):
        parse_and_validate_app_table(
            [
                {"public_step_name": "dup", "step_fn": "ped.patch_only_counter", "fn_args": {}},
                {"public_step_name": "dup", "step_fn": "ped.patch_only_counter", "fn_args": {}},
            ]
        )

    with pytest.raises(AppTableParserValidatorError):
        parse_and_validate_app_table([{"public_step_name": "x", "step_fn": "ped.patch_only_counter", "fn_args": {"nope": 1}}])


def test_step_fn_receives_state_copy_in_place_mutation_does_not_persist():
    api = get_concrete_session_api()

    manifest = [
        {"public_step_name": "m", "step_fn": "ped.state_mutation_is_ignored", "fn_args": {}},
        {"public_step_name": "done", "step_fn": "ped.patch_only_counter", "fn_args": {"label": "ok"}},
    ]

    rr = run_session_against_script_headless(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata={},
        api=api,
        script=[{"action": "STEP", "until_stop": True, "stop_kinds": ["ATCOMPLETION"], "expect": {"kind": "ATCOMPLETION"}}],
    )

    out = api.get_outputs(rr.ctx["session_id"])
    assert "MUTATED_IN_PLACE" not in out["globals"]
    assert out["globals"]["counter"] == 1


def test_prefill_directive_complete_only_allows_partial_required_micros_and_consumes_directive_key():
    api = get_concrete_session_api()

    manifest = [
        {"public_step_name": "name", "step_fn": "ped.emit_name_prefill_with_directive", "fn_args": {"directive": "complete_only", "prefill_last": "Lovelace"}},
        {"public_step_name": "done", "step_fn": "ped.patch_only_counter", "fn_args": {"label": "x"}},
    ]

    rr = run_session_against_script_headless(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata={},
        api=api,
        script=[
            {"action": "STEP", "until_stop": True, "expect": {"kind": "MANUALFILLNEEDEDSTEP", "form_id": "FORM_NAME_ONLY"}},
            {"action": "STEP", "fill": {"NAME": {"first": "Ada"}}},
            {"action": "STEP", "until_stop": True, "stop_kinds": ["ATCOMPLETION"], "expect": {"kind": "ATCOMPLETION"}},
        ],
    )

    out = api.get_outputs(rr.ctx["session_id"])
    assert out["form_fills"]["NAME"]["first"] == "Ada"
    assert out["form_fills"]["NAME"]["last"] == "Lovelace"
    assert "multiframespec_PREFILL_VALIDATE_VALUES" not in out["globals"]


def test_prefill_directive_subset_allows_skipping_validation_for_other_fields():
    api = get_concrete_session_api()

    manifest = [
        {"public_step_name": "s", "step_fn": "ped.emit_subset_prefill_validation", "fn_args": {"directive": ["FIELD_B"]}},
        {"public_step_name": "done", "step_fn": "ped.patch_only_counter", "fn_args": {"label": "done"}},
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
    out = api.get_outputs(rr.ctx["session_id"])
    assert out["form_prefills"]["FIELD_A"]["value"] == "ok"
    assert out["form_prefills"]["FIELD_B"]["value"] == "OK"
    assert out["form_fills"] == {}


def test_prefill_directive_truthy_map_subset_equivalent_to_list_subset():
    api = get_concrete_session_api()

    manifest = [
        {"public_step_name": "s", "step_fn": "ped.emit_subset_prefill_validation", "fn_args": {"directive": {"FIELD_B": True, "FIELD_A": False}}},
        {"public_step_name": "done", "step_fn": "ped.patch_only_counter", "fn_args": {"label": "done"}},
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

    out = api.get_outputs(rr.ctx["session_id"])
    assert out["form_prefills"]["FIELD_A"]["value"] == "ok"
    assert out["form_prefills"]["FIELD_B"]["value"] == "OK"
    assert out["form_fills"] == {}


def test_prefill_directive_explicit_schema_dict():
    api = get_concrete_session_api()

    manifest = [
        {"public_step_name": "s", "step_fn": "ped.emit_subset_prefill_validation", "fn_args": {"directive": {"mode": "complete_only", "fields": ["FIELD_B"]}}},
        {"public_step_name": "done", "step_fn": "ped.patch_only_counter", "fn_args": {"label": "done"}},
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

    out = api.get_outputs(rr.ctx["session_id"])
    assert out["form_prefills"]["FIELD_A"]["value"] == "ok"
    assert out["form_prefills"]["FIELD_B"]["value"] == "OK"
    assert out["form_fills"] == {}


def test_form_id_derivation_and_duplicate_form_id_is_fatal():
    api = get_concrete_session_api()

    manifest = [
        {"public_step_name": "f1", "step_fn": "ped.emit_duplicate_form_id", "fn_args": {"form_id": "DUP_FORM"}},
        {"public_step_name": "f2", "step_fn": "ped.emit_duplicate_form_id", "fn_args": {"form_id": "DUP_FORM"}},
    ]
    st = api.create_VM_session(manifest=manifest, initial_parameter_overrides={}, session_metadata={}, get_map=False)  # type: ignore[arg-type]
    sid = st["session_id"]

    while True:
        ctx = api.get_session_context(sid)
        if ctx.get("kind") == "MANUALFILLNEEDEDSTEP":
            break
        api.step_session(sid)

    with pytest.raises(FatalEngineError):
        api.step_session(sid, fill={"NAME": {"first": "A", "last": "B"}})


def test_helpers_patterns_and_introspection_inside_step_fn():
    api = get_concrete_session_api()

    manifest = [
        {"public_step_name": "identity", "step_fn": "ped.emit_identity_form", "fn_args": {"prefill_last": "Lovelace", "explicit_form_id": True}},
        {"public_step_name": "introspect", "step_fn": "ped.introspect_current_form_into_globals", "fn_args": {"form_id": "FORM_IDENTITY"}},
        {"public_step_name": "commit", "step_fn": "ped.commit_identity", "fn_args": {}},
    ]

    rr = run_session_against_script_headless(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata={},
        api=api,
        script=[
            {"action": "STEP", "until_stop": True, "expect": {"kind": "MANUALFILLNEEDEDSTEP", "form_id": "FORM_IDENTITY"}},
            {"action": "STEP", "fill": {"NAME": {"first": "Ada"}}},
            {"action": "STEP", "until_stop": True, "expect": {"kind": "MANUALFILLNEEDEDSTEP", "step": {"span_id": "S_DOB"}}},
            {"action": "STEP", "fill": {"DOB": {"day": "10", "month": "12", "year": "1815"}}},
            {"action": "STEP", "until_stop": True, "expect": {"kind": "MANUALFILLNEEDEDSTEP", "step": {"span_id": "S_AGE"}, "datum_widgets_on_this_span_contains": ["AGE"]}},
            {"action": "STEP", "fill": {"AGE": {"value": 30}}},
            {"action": "STEP", "until_stop": True, "stop_kinds": ["ATCOMPLETION"], "expect": {"kind": "ATCOMPLETION"}},
        ],
    )

    out = api.get_outputs(rr.ctx["session_id"])

    state_view = dict(out["globals"])
    state_view["form_prefills"] = dict(out["form_prefills"])
    state_view["form_fills"] = dict(out["form_fills"])
    state_view["forms_emitted"] = {}

    pref = get_form_prefills(state_view)
    fills = get_form_fills(state_view)
    gl = get_globals(state_view)
    merged = get_fills_snapshot_from_app_table_state(state_view)

    assert "NAME" in pref and "NAME" in fills and "NAME" in merged
    assert gl["committed"] is True

    summary = out["globals"]["introspection"]
    assert summary["NAME"]["has_any"] is True
    assert summary["NAME"]["is_mixed"] is True
    assert summary["DOB"]["is_io_only"] is True


def test_manual_fill_type_must_be_mapping():
    api = get_concrete_session_api()
    manifest = [
        {"public_step_name": "identity", "step_fn": "ped.emit_identity_form", "fn_args": {"explicit_form_id": True}},
    ]
    st = api.create_VM_session(manifest=manifest, initial_parameter_overrides={}, session_metadata={}, get_map=False)  # type: ignore[arg-type]
    sid = st["session_id"]

    while True:
        ctx = api.get_session_context(sid)
        if ctx.get("kind") == "MANUALFILLNEEDEDSTEP":
            break
        api.step_session(sid)

    with pytest.raises(InvalidExternalFillError):
        api.step_session(sid, fill="not a dict")  # type: ignore[arg-type]


def test_runtime_write_index_queries_direct_state_writes_by_arg_name_and_value():
    api = get_concrete_session_api()

    manifest = [
        {
            "public_step_name": "w1",
            "step_fn": "ped.write_blob_and_scalar",
            "fn_args": {"group": "alpha", "enabled": True, "blob_chars": 128},
        },
        {
            "public_step_name": "w2",
            "step_fn": "ped.write_blob_and_scalar",
            "fn_args": {"group": "beta", "enabled": False, "blob_chars": 128},
        },
        {
            "public_step_name": "q",
            "step_fn": "ped.query_runtime_writes",
            "fn_args": {
                "query": {
                    "arg_path": "group",
                    "arg_value_equals": "alpha",
                    "write_kinds": ["state"],
                    "max_results": 16,
                },
                "out_key": "q_alpha",
            },
        },
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
                "stop_kinds": ["ATCOMPLETION"],
                "expect": {"kind": "ATCOMPLETION"},
            },
        ],
    )

    out = api.get_outputs(rr.ctx["session_id"])
    q = out["globals"]["q_alpha"]
    keys = [w["key"] for w in q["writes"]]

    assert q["ok"] is True
    assert "group" in keys
    assert "enabled" in keys
    assert "blob" in keys
    assert all(w["public_step_name"] == "w1" for w in q["writes"])


def test_runtime_write_index_queries_form_prefills_and_manual_fills_by_source_step_args():
    api = get_concrete_session_api()

    manifest = [
        {
            "public_step_name": "identity",
            "step_fn": "ped.emit_identity_form",
            "fn_args": {
                "prefill_last": "Lovelace",
                "explicit_form_id": True,
                "also_prefill_age": 30,
            },
        },
        {
            "public_step_name": "q",
            "step_fn": "ped.query_runtime_writes",
            "fn_args": {
                "query": {
                    "public_step_name": "identity",
                    "write_kinds": ["form_prefill", "form_fill"],
                    "max_results": 32,
                },
                "out_key": "q_identity_writes",
            },
        },
    ]

    rr = run_session_against_script_headless(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata={},
        api=api,
        script=[
            {"action": "STEP", "until_stop": True, "expect": {"kind": "MANUALFILLNEEDEDSTEP", "form_id": "FORM_IDENTITY"}},
            {"action": "STEP", "fill": {"NAME": {"first": "Ada"}}},
            {"action": "STEP", "until_stop": True, "expect": {"kind": "MANUALFILLNEEDEDSTEP", "step": {"span_id": "S_DOB"}}},
            {"action": "STEP", "fill": {"DOB": {"day": "10", "month": "12", "year": "1815"}}},
            {
                "action": "STEP",
                "until_stop": True,
                "stop_kinds": ["ATCOMPLETION"],
                "expect": {"kind": "ATCOMPLETION"},
            },
        ],
    )

    out = api.get_outputs(rr.ctx["session_id"])
    q = out["globals"]["q_identity_writes"]
    kinds = [w["write_kind"] for w in q["writes"]]
    keys = [w["key"] for w in q["writes"]]

    assert "form_prefill" in kinds
    assert "form_fill" in kinds
    assert "NAME" in keys
    assert "DOB" in keys
    assert "AGE" in keys



def test_runtime_write_index_undo_removes_unwound_write_events():
    api = get_concrete_session_api()

    manifest = [
        {
            "public_step_name": "w1",
            "step_fn": "ped.write_blob_and_scalar",
            "fn_args": {"group": "undo", "enabled": True, "blob_chars": 0},
        },
        {
            "public_step_name": "w2",
            "step_fn": "ped.write_blob_and_scalar",
            "fn_args": {"group": "undo", "enabled": False, "blob_chars": 0},
        },
    ]

    st = api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides={},
        session_metadata={},
        get_map=False,
    )  # type: ignore[arg-type]
    sid = st["session_id"]

    r = SessionProgramScriptedHeadlessRunner(sid, api=api)
    r.step_until_stop(stop_kinds=["ATCOMPLETION"])

    idx_before = api.export_session_snapshot(sid)["state"]["_runtime_write_index_v1"]
    assert idx_before["invocation_order"] == [1, 2]

    r.undo_until_stop(stop_kinds=["ATSTART", "MANUALFILLNEEDEDSTEP"])

    idx_after = api.export_session_snapshot(sid)["state"]["_runtime_write_index_v1"]

    assert idx_after["invocation_order"] == []
    assert idx_after["write_events"] == {}