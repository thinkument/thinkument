from __future__ import annotations

"""
App Table State Helpers (Pedagogy Sheet — Zoom In)
==================================================

This file is executable documentation for writing *step functions* that:
- emit forms
- read fills/prefills from state
- use helpers for stable, ergonomic interpretation

Mental model
------------
Each step function has the contract:

    step_fn(state: dict, **fn_args) -> patch

Where:
- `state` is input-only (treat as immutable; engine copies on call)
- `patch` is shallow key->value updates (overwrites the engine state)
- to emit a form, include patch["multiframespec"] = <multiframespec dict>

Tuple return shapes are not supported.
"""

import sys
import types
from typing import Any, Dict, Optional

import pytest

from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_form_emitted,
    get_form_fill_info,
    get_form_fills,
    get_form_fills_by_frame,
    get_form_fills_by_micro,
    get_form_fills_by_span,
    get_form_prefills,
    get_form_prefills_for_form,
    get_fills_snapshot_from_app_table_state,
)
from _thinkengine.runme.runme_offline_debug_against_actionscript import SessionProgramScriptedHeadlessRunner


def _install_validators() -> None:
    mod = types.ModuleType("app_table_helpers_validators")

    def nonempty(v):
        if isinstance(v, dict) and "value" in v:
            v = v["value"]
        ok = isinstance(v, str) and v.strip() != ""
        return ok, (None if ok else "must be non-empty")

    mod.nonempty = nonempty
    sys.modules["app_table_helpers_validators"] = mod


def _emit_form_with_explicit_id(state: Dict[str, Any], *, prefill_last: Optional[str] = None) -> Dict[str, Any]:
    fills = {}
    if prefill_last is not None:
        fills["NAME"] = {"last": str(prefill_last)}

    multiframespec = {
        "app_form_id": "FORM_IDENTITY",
        "datums": [
            {
                "id": "NAME",
                "title": "Name",
                "micros": [
                    {"name": "first", "type": "text", "required": True, "validators": ["app_table_helpers_validators:nonempty"]},
                    {"name": "last", "type": "text", "required": True, "validators": ["app_table_helpers_validators:nonempty"]},
                ],
            }
        ],
        "frames": [
            {
                "id": "IDENTITY",
                "title": "Identity",
                "spans": [{"id": "S_NAME", "owns": ["NAME"]}],
            }
        ],
        "fills": fills,
    }
    return {"started": True, "multiframespec": multiframespec}


def _commit_and_probe_helpers(state: Dict[str, Any]) -> Dict[str, Any]:
    raw_pref = get_form_prefills(state)
    raw_fills = get_form_fills(state)
    merged = get_fills_snapshot_from_app_table_state(state)

    fs = get_form_emitted(state, "FORM_IDENTITY")
    pref_scoped = get_form_prefills_for_form(state, "FORM_IDENTITY")
    info = get_form_fill_info(state, "FORM_IDENTITY")
    by_frame = get_form_fills_by_frame(state, "FORM_IDENTITY", "IDENTITY")
    by_span = get_form_fills_by_span(state, "FORM_IDENTITY", "IDENTITY", "S_NAME")
    by_micro = get_form_fills_by_micro(state, "FORM_IDENTITY", "NAME", "first")

    return {
        "probe_has_multiframespec": bool(fs),
        "probe_form_id": info.get("form_id"),
        "probe_raw_pref_keys": sorted(list(raw_pref.keys())),
        "probe_raw_fill_keys": sorted(list(raw_fills.keys())),
        "probe_merged_keys": sorted(list(merged.keys())),
        "probe_scoped_pref_keys": sorted(list(pref_scoped.keys())),
        "probe_has_name": "NAME" in (info.get("datums") or {}),
        "probe_name_sources": ((info.get("datums") or {}).get("NAME") or {}).get("sources"),
        "probe_frame_has_span": "S_NAME" in (by_frame.get("spans") or {}),
        "probe_span_has_name": "NAME" in (by_span.get("datums") or {}),
        "probe_micro_merged": by_micro.get("merged"),
    }


@pytest.fixture(autouse=True)
def _setup():
    _install_validators()

    StepFnregistry.clear()
    StepFnregistry.register(
        name="emit_form_with_id",
        fn=_emit_form_with_explicit_id,
        required_args=set(),
        optional_args={"prefill_last"},
    )
    StepFnregistry.register(name="commit_probe", fn=_commit_and_probe_helpers, required_args=set(), optional_args=set())


def test_helpers_form_id_and_filters_io_only():
    api = get_concrete_session_api()
    manifest = [
        {"public_step_name": "identity_step", "step_fn": "emit_form_with_id", "fn_args": {}},
        {"public_step_name": "commit_step", "step_fn": "commit_probe", "fn_args": {}},
    ]
    st = api.create_VM_session(manifest=manifest, initial_parameter_overrides={}, session_metadata={}, get_map=False)  # type: ignore[arg-type]
    sid = st["session_id"]

    r = SessionProgramScriptedHeadlessRunner(sid)

    ctx1 = r.step_until_stop()
    assert ctx1["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx1.get("form_id") == "FORM_IDENTITY"

    _ = r.step(fill={"NAME": {"first": "Ada", "last": "Lovelace"}})

    done = r.step_until_stop()
    assert done["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    g = out["globals"]

    assert g["probe_has_multiframespec"] is True
    assert g["probe_form_id"] == "FORM_IDENTITY"
    assert g["probe_has_name"] is True

    assert "NAME" in g["probe_raw_fill_keys"]
    assert "NAME" in g["probe_merged_keys"]

    src = g["probe_name_sources"]
    assert isinstance(src, dict)
    assert src.get("is_io_only") is True
    assert src.get("is_prefill_only") is False
    assert src.get("is_mixed") is False

    assert g["probe_frame_has_span"] is True
    assert g["probe_span_has_name"] is True
    assert g["probe_micro_merged"] == "Ada"


def test_helpers_sources_mixed_when_prefill_then_user_edits():
    api = get_concrete_session_api()
    manifest = [
        {"public_step_name": "identity_step", "step_fn": "emit_form_with_id", "fn_args": {"prefill_last": "Lovelace"}},
        {"public_step_name": "commit_step", "step_fn": "commit_probe", "fn_args": {}},
    ]
    st = api.create_VM_session(manifest=manifest, initial_parameter_overrides={}, session_metadata={}, get_map=False)  # type: ignore[arg-type]
    sid = st["session_id"]

    r = SessionProgramScriptedHeadlessRunner(sid)

    ctx1 = r.step_until_stop()
    assert ctx1["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx1.get("form_id") == "FORM_IDENTITY"

    _ = r.step(fill={"NAME": {"first": "Ada"}})

    done = r.step_until_stop()
    assert done["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    g = out["globals"]

    assert "NAME" in g["probe_raw_pref_keys"]
    assert "NAME" in g["probe_raw_fill_keys"]
    assert "NAME" in g["probe_scoped_pref_keys"]

    src = g["probe_name_sources"]
    assert isinstance(src, dict)
    assert src.get("is_mixed") is True
    assert src.get("has_any") is True

    assert g["probe_micro_merged"] == "Ada"