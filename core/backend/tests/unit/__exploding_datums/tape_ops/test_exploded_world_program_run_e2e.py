# think-backend/tests/wippp/test_exploded_world_program_scripted_run_e2e.py
from __future__ import annotations

"""
Exploded World Program Scripted Run E2E
=======================================

This sheet pedagogizes the scripting surface for Q-aware App Table programs.

It proves:

1. A developer can script a realistic program to completion by submitting one
   nested datum fill per public manual surface.

2. Reexploding datums are not special to the runner:
      - first fill may reexplode the same span,
      - next fill satisfies the new micro surface,
      - script continues.

3. A wrong script fails fast:
      - demanding ATCOMPLETION while a reexploded datum still needs input
        raises immediately with the current MANUALFILLNEEDEDSTEP surface;
      - runner does not spin.

4. Script history is slim by default:
      - no multiframespec snapshot,
      - no giant lifecycle proc_notes,
      - no full output duplication.

5. Scripted undo/redo replays the same public tape semantics as the UI API.
"""

import time
from typing import Any, Dict, Mapping

import pytest

from __datomatonTM import (
    register_datum_widget_v1
)
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_DATUM_LIFECYCLE,
    KEY_RUNTIME_WRITE_INDEX,
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_data_indexing import (
    WRITE_KIND_DATUM_LIFECYCLE,
    query_runtime_writes_v1,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
from _thinkengine.runme.runme_offline_debug_against_actionscript import SessionProgramScriptedHeadlessRunner, run_session_against_script_headless


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _number_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "number", "required": required}


def _api():
    return get_concrete_session_api(enable_persistence=False)


def _register_step(name: str, multiframespec: Mapping[str, Any]) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {"multiframespec": dict(multiframespec)}

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _manifest(step_name: str) -> list[dict[str, Any]]:
    return [{"public_step_name": "scripted_app", "step_fn": step_name, "fn_args": {}}]


def _contains_run(obj: Any, ch: str, n: int, *, max_nodes: int = 200_000) -> bool:
    needle = ch * n
    stack = [obj]
    seen: set[int] = set()
    visited = 0
    while stack and visited < max_nodes:
        cur = stack.pop()
        visited += 1
        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, str):
            if needle in cur:
                return True
        elif isinstance(cur, Mapping):
            for k, v in cur.items():
                stack.append(k)
                stack.append(v)
        elif isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)
    return False


# ---------------------------------------------------------------------------
# Application-like form
# ---------------------------------------------------------------------------


def _register_application_widgets() -> None:
    def kyc_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Toy but application-shaped Q datum.

        User first enters SSN tail. The widget asks for a confirmation micro.
        This models KYC/identity review without doing real external work.
        """
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            if str(partial.get("confirm") or "").lower() not in {"yes", "y", "true"}:
                return {
                    "status": "blocked",
                    "message": {"level": "error", "text": "identity confirmation must be yes"},
                    "state": {"phase": "confirm"},
                }
            return {
                "status": "done",
                "message": {"level": "success", "text": "identity confirmed"},
                "state": {"phase": "done"},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "title": "Confirm identity",
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.scripted.kyc",
                    "max_reexplosions": 1,
                    "max_proc_notes": 2,
                    "max_messages": 4,
                },
            },
            "fill": {"confirm": ""},
            "prefill": {"confirm": "yes"},
            "state": {"phase": "confirm"},
            "message": {"level": "info", "text": "confirm identity"},
            "proc_notes": {"audit_token_preview": "kyc-preview"},
        }

    def affordability_widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Toy Q datum that blocks until the amount is small enough.
        """
        partial = dict(q.get("partial_fill") or {})
        try:
            amount = float(partial.get("value"))
        except Exception:
            amount = 0.0

        if amount > 500_000:
            return {
                "status": "blocked",
                "message": {"level": "error", "text": "amount too high for this demo"},
                "state": {"last_amount": amount},
            }

        return {
            "status": "done",
            "message": {"level": "success", "text": "amount accepted"},
            "state": {"last_amount": amount},
        }

    register_datum_widget_v1("test.scripted.kyc", kyc_widget, overwrite=True)
    register_datum_widget_v1("test.scripted.affordability", affordability_widget, overwrite=True)


def _loan_application_multiframespec(*, giant_proc_notes: str = "") -> Dict[str, Any]:
    if giant_proc_notes:
        def kyc_giant(q: Mapping[str, Any]) -> Mapping[str, Any]:
            datum = dict(q["datum"])
            partial = dict(q.get("partial_fill") or {})
            if "confirm" in partial:
                return {"status": "done", "message": {"level": "success", "text": ""}, "state": {}}
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "micros": [_text_micro("confirm")],
                    "lifecycle": {
                        "widget": "test.scripted.kyc.giant",
                        "max_reexplosions": 1,
                        "max_proc_notes": 1,
                        "max_messages": 4,
                    },
                },
                "fill": {"confirm": ""},
                "state": {},
                "message": {"level": "info", "text": "confirm"},
                "proc_notes": {"giant": giant_proc_notes},
            }

        register_datum_widget_v1("test.scripted.kyc.giant", kyc_giant, overwrite=True)
        kyc_widget = "test.scripted.kyc.giant"
    else:
        kyc_widget = "test.scripted.kyc"

    return {
        "app_form_id": "scripted.loan.application",
        "datums": [
            {"id": "NAME", "title": "Name", "micros": [_text_micro()]},
            {
                "id": "AMOUNT",
                "title": "Loan amount",
                "micros": [_number_micro()],
                "lifecycle": {
                    "widget": "test.scripted.affordability",
                    "max_reexplosions": 0,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            {
                "id": "KYC",
                "title": "Identity check",
                "micros": [_text_micro("ssn4")],
                "lifecycle": {
                    "widget": kyc_widget,
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            {"id": "NOTES", "title": "Notes", "micros": [_text_micro(required=True)]},
        ],
        "frames": [
            {
                "id": "INTAKE",
                "title": "Intake",
                "spans": [
                    {"id": "S_NAME", "owns": ["NAME"]},
                    {"id": "S_AMOUNT", "owns": ["AMOUNT"]},
                    {"id": "S_KYC", "owns": ["KYC"]},
                    {"id": "S_NOTES", "owns": ["NOTES"]},
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Scripted-run E2E
# ---------------------------------------------------------------------------


def test_scripted_loan_application_happy_path_pedagogical_q_reexplode_to_completion():
    _register_application_widgets()

    step_name = "test.scripted.loan.happy.step"
    _register_step(step_name, _loan_application_multiframespec())

    api = _api()
    result = run_session_against_script_headless(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
                "include_global_fill_keys_in_ctx": False,
                "include_field_value_keys_in_ctx": False,
            }
        },
        api=api,
        script=[
            {
                "action": "STEP",
                "until_stop": True,
                "expect": {
                    "kind": "MANUALFILLNEEDEDSTEP",
                    "current_span": "S_NAME",
                    "datum_widgets_on_this_span_contains": ["NAME"],
                },
            },
            {
                "action": "STEP",
                "fill": {"NAME": {"value": "Ada Lovelace"}},
                "expect": {
                    "kind": "MANUALFILLNEEDEDSTEP",
                    "current_span": "S_AMOUNT",
                    "datum_widgets_on_this_span_contains": ["AMOUNT"],
                },
            },
            {
                "action": "STEP",
                "fill": {"AMOUNT": {"value": 250000}},
                "expect": {
                    "kind": "MANUALFILLNEEDEDSTEP",
                    "current_span": "S_KYC",
                    "datum_widgets_on_this_span_contains": ["KYC"],
                },
            },
            {
                "action": "STEP",
                "fill": {"KYC": {"ssn4": "1234"}},
                "expect": {
                    "kind": "MANUALFILLNEEDEDSTEP",
                    "current_span": "S_KYC",
                    "datum_widgets_on_this_span_contains": ["KYC"],
                },
            },
            {
                "action": "STEP",
                "fill": {"KYC": {"confirm": "yes"}},
                "expect": {
                    "kind": "MANUALFILLNEEDEDSTEP",
                    "current_span": "S_NOTES",
                    "datum_widgets_on_this_span_contains": ["NOTES"],
                },
            },
            {
                "action": "STEP",
                "fill": {"NOTES": {"value": "ready"}},
                "expect": {"kind": "ATCOMPLETION"},
            },
        ],
    )

    assert result.ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(result.session_id)
    assert out["form_fills"]["NAME"]["value"] == "Ada Lovelace"
    assert out["form_fills"]["AMOUNT"]["value"] == 250000
    assert out["form_fills"]["KYC"]["confirm"] == "yes"
    assert out["form_fills"]["NOTES"]["value"] == "ready"


def test_scripted_runner_fails_fast_when_q_reexplode_needs_another_fill_but_script_demands_completion():
    _register_application_widgets()

    step_name = "test.scripted.loan.stuck.step"
    _register_step(step_name, _loan_application_multiframespec())

    api = _api()

    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    runner.step_until_stop()
    runner.step(fill={"NAME": {"value": "Ada"}})
    runner.step(fill={"AMOUNT": {"value": 100000}})

    # We are at KYC. Supplying only ssn4 reexplodes to confirm, so demanding
    # completion is a script bug. The runner must not spin.
    with pytest.raises(RuntimeError, match="MANUALFILLNEEDEDSTEP|encountered MANUALFILLNEEDEDSTEP"):
        runner.step_until_stop(
            fill={"KYC": {"ssn4": "1234"}},
            stop_kinds=["ATCOMPLETION"],
            max_iters=4,
        )


def test_scripted_runner_blocks_invalid_business_q_and_then_recovers_with_retry():
    _register_application_widgets()

    step_name = "test.scripted.loan.block.retry.step"
    _register_step(step_name, _loan_application_multiframespec())

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={"manual_io": {"persistence": "disabled", "include_forms_emitted_order_in_ctx": False}},
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    ctx = runner.step_until_stop()
    assert ctx["current_span"] == "S_NAME"

    ctx = runner.step(fill={"NAME": {"value": "Grace"}})
    assert ctx["current_span"] == "S_AMOUNT"

    ctx = runner.step(fill={"AMOUNT": {"value": 999999}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_AMOUNT"
    assert "AMOUNT" in ctx["last_error"]

    ctx = runner.step(fill={"AMOUNT": {"value": 400000}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_KYC"


def test_scripted_undo_redo_over_reexploded_program_surfaces_is_public_and_bounded():
    _register_application_widgets()

    step_name = "test.scripted.loan.undo.redo.step"
    _register_step(step_name, _loan_application_multiframespec())

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {"persistence": "disabled", "include_forms_emitted_order_in_ctx": False},
            "redo": {"max_depth": 64},
        },
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    runner.step_until_stop()
    runner.step(fill={"NAME": {"value": "Ada"}})
    runner.step(fill={"AMOUNT": {"value": 200000}})

    ctx = runner.step(fill={"KYC": {"ssn4": "9999"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_KYC"
    assert "confirm" in str(ctx["datum_widget_decls"]["KYC"])

    ctx = runner.undo()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_KYC"
    assert "ssn4" in str(ctx["datum_widget_decls"]["KYC"])
    assert "confirm" not in str(ctx["datum_widget_decls"]["KYC"])

    ctx = runner.redo()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_KYC"
    assert "confirm" in str(ctx["datum_widget_decls"]["KYC"])

    ctx = runner.step(fill={"KYC": {"confirm": "yes"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S_NOTES"


def test_script_history_is_slim_by_default_even_with_giant_q_proc_notes():
    _register_application_widgets()

    giant = "Z" * 800_000
    step_name = "test.scripted.loan.slim.history.step"
    _register_step(step_name, _loan_application_multiframespec(giant_proc_notes=giant))

    api = _api()
    result = run_session_against_script_headless(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
                "include_global_fill_keys_in_ctx": False,
                "include_field_value_keys_in_ctx": False,
            }
        },
        api=api,
        keep_full_history=False,
        script=[
            {"action": "STEP", "until_stop": True},
            {"action": "STEP", "fill": {"NAME": {"value": "Ada"}}},
            {"action": "STEP", "fill": {"AMOUNT": {"value": 100000}}},
            {"action": "STEP", "fill": {"KYC": {"ssn4": "1234"}}},
            {"action": "STEP", "fill": {"KYC": {"confirm": "yes"}}},
            {"action": "STEP", "fill": {"NOTES": {"value": "done"}}, "expect": {"kind": "ATCOMPLETION"}},
        ],
    )

    assert result.ctx["kind"] == "ATCOMPLETION"
    assert not _contains_run(result.history, "Z", 1000)

    st = api._get(result.session_id).state
    assert _contains_run(st[KEY_DATUM_LIFECYCLE], "Z", 1000)
    assert not _contains_run(st[KEY_RUNTIME_WRITE_INDEX], "Z", 1000)

    q = query_runtime_writes_v1(
        st,
        {
            "write_kinds": [WRITE_KIND_DATUM_LIFECYCLE],
            "max_results": 3,
            "include_values": False,
        },
    )
    assert q["ok"] is True
    assert len(q["writes"]) <= 3
    assert not _contains_run(q, "Z", 1000)


def test_scripted_many_reexploding_program_ticks_scale_without_runner_loop_or_snapshot_wall():
    """
    Program-level scripted scalability.

    This does not benchmark HTML. It measures the direct scripting artery:
    session creation -> manual stops -> Q reexplode -> Q done -> completion.
    """
    def reexplode_once(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})
        if "confirm" in partial:
            return {"status": "done", "message": {"level": "success", "text": ""}, "state": {}}
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.scripted.scale.reexplode_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            "fill": {"confirm": ""},
            "state": {},
            "message": {"level": "info", "text": "confirm"},
            "proc_notes": {"tiny": True},
        }

    register_datum_widget_v1("test.scripted.scale.reexplode_once", reexplode_once, overwrite=True)

    n = 60
    fs = {
        "app_form_id": "scripted.scale",
        "datums": [
            {
                "id": f"D{i}",
                "title": f"D{i}",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.scripted.scale.reexplode_once",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            }
            for i in range(n)
        ],
        "frames": [
            {
                "id": "F",
                "spans": [{"id": f"S{i}", "owns": [f"D{i}"]} for i in range(n)],
            }
        ],
    }

    step_name = "test.scripted.scale.step"
    _register_step(step_name, fs)

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={"manual_io": {"persistence": "disabled", "include_forms_emitted_order_in_ctx": False}},
    )
    sid = str(st["session_id"])
    runner = SessionProgramScriptedHeadlessRunner(sid, api=api)

    t0 = time.perf_counter()
    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    for i in range(n):
        ctx = runner.step(fill={f"D{i}": {"value": f"v{i}"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        ctx = runner.step(fill={f"D{i}": {"confirm": "yes"}})
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    print(
        "[exploded-script-summary] many_reexploding_program "
        f"n={n} manual_ticks={2 * n} elapsed={elapsed:.6f}s "
        f"avg_tick_ms={elapsed * 1000 / (2 * n):.3f}"
    )

    assert elapsed < 20.0

def test_scripted_runner_accepts_dotted_micro_fill_syntax_for_reexploding_programs():
    _register_application_widgets()

    step_name = "test.scripted.loan.dotted.syntax.step"
    _register_step(step_name, _loan_application_multiframespec())

    api = _api()
    result = run_session_against_script_headless(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
                "include_global_fill_keys_in_ctx": False,
                "include_field_value_keys_in_ctx": False,
            }
        },
        api=api,
        script=[
            {"action": "STEP", "until_stop": True},
            {"action": "STEP", "fill": {"NAME.value": "Ada Lovelace"}},
            {"action": "STEP", "fill": {"AMOUNT.value": 100000}},
            {"action": "STEP", "fill": {"KYC.ssn4": "1234"}},
            {"action": "STEP", "fill": {"KYC.confirm": "yes"}},
            {
                "action": "STEP",
                "fill": {"NOTES.value": "done"},
                "expect": {"kind": "ATCOMPLETION"},
            },
        ],
    )

    assert result.ctx["kind"] == "ATCOMPLETION"
    out = api.get_outputs(result.session_id)
    assert out["form_fills"]["NAME"]["value"] == "Ada Lovelace"
    assert out["form_fills"]["KYC"]["confirm"] == "yes"