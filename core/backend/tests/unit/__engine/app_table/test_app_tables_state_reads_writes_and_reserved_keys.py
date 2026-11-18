from __future__ import annotations

from contextlib import contextmanager

import pytest

from _thinkengine.runme.runme_offline_debug_against_actionscript import SessionProgramScriptedHeadlessRunner
from __exceptions.engine import FatalEngineError
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api


@contextmanager
def _isolated_registry_step_fns():
    old = dict(StepFnregistry._REG)  # type: ignore[attr-defined]
    try:
        yield
    finally:
        StepFnregistry._REG = old  # type: ignore[attr-defined]


def _new_api():
    return get_concrete_session_api()


def _state_demo_multiframespec(*, fills: dict) -> dict:
    return {
        "app_form_id": "PED_FORM_STATE",
        "datums": [
            {
                "id": "X",
                "title": "X",
                "micros": [{"name": "value", "type": "text", "required": True}],
            }
        ],
        "frames": [
            {
                "id": "F1",
                "spans": [{"id": "S1", "owns": ["X"]}],
            }
        ],
        "fills": dict(fills),
    }


def _ped_state_step1_write_custom_and_emit_form(state: dict) -> dict:
    log = list(state.get("custom_log") or [])
    log.append("step1")
    patch = {
        "custom_log": log,
        "counter": int(state.get("counter") or 0) + 1,
        "note": "step1 patched globals and emitted a form",
        "multiframespec": _state_demo_multiframespec(fills={"X": "prefilled-x"}),
    }
    return patch


def _ped_state_step2_read_then_append_custom(state: dict) -> dict:
    log = list(state.get("custom_log") or [])
    log.append("step2")

    pref = state.get("form_prefills") or {}
    x_seen = pref.get("X")

    return {
        "custom_log": log,
        "counter": int(state.get("counter") or 0) + 1,
        "x_seen_from_reserved_form_prefills": x_seen,
        "note2": "step2 read and appended state; also read reserved runtime keys",
    }


def _ped_state_illegal_patch_reserved_key(state: dict) -> dict:
    return {
        "form_prefills": {"X": "evil"},
    }


def _register_ped_state_step_fns() -> None:
    StepFnregistry.register(
        name="ped_state_step1_write_custom_and_emit_form",
        fn=_ped_state_step1_write_custom_and_emit_form,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )
    StepFnregistry.register(
        name="ped_state_step2_read_then_append_custom",
        fn=_ped_state_step2_read_then_append_custom,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )
    StepFnregistry.register(
        name="ped_state_illegal_patch_reserved_key",
        fn=_ped_state_illegal_patch_reserved_key,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def test_pedagogical_state_reads_writes_across_step_fns_and_reserved_key_effects() -> None:
    with _isolated_registry_step_fns():
        _register_ped_state_step_fns()
        api = _new_api()

        manifest = {
            "steps": [
                {"public_step_name": "S1", "step_fn": "ped_state_step1_write_custom_and_emit_form", "fn_args": {}},
                {"public_step_name": "S2", "step_fn": "ped_state_step2_read_then_append_custom", "fn_args": {}},
            ]
        }

        st = api.create_VM_session(manifest=manifest, initial_parameter_overrides={"custom_log": [], "counter": 0}, session_metadata={})
        r = SessionProgramScriptedHeadlessRunner(st["session_id"], api=api)

        ctx = r.step_until_stop(stop_kinds=("ATCOMPLETION",))
        assert ctx["kind"] == "ATCOMPLETION"

        outputs = api.get_outputs(st["session_id"])
        gl = outputs.get("globals") or {}
        assert gl["custom_log"] == ["step1", "step2"]
        assert gl["counter"] == 2

        assert gl["x_seen_from_reserved_form_prefills"] == "prefilled-x"