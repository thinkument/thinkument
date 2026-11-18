from __future__ import annotations

"""
Datum lifecycle class-adapter tests.

The class-adapter implementation and author documentation live in:

    thinkwidgetTM
    thinkwidgetTM/DEFINITION.md

This sheet proves the imported adapter surface against the existing datomaton
engine, controller, undo/redo, inheritance, and kernel integration paths.
"""

from typing import Any, Dict, Mapping, Optional

import pytest

from _thinkprogram.thinkwidgetTM import (
    ADAPTER_RESERVED_STATE_KEY,
    CONFIG_KEY,
    MESSAGE_EVENT_AUDIENCE,
    MESSAGE_EVENT_CHANNEL,
    MESSAGE_EVENT_NAME,
    MISSING_SIGNAL_FALLBACK_TO_FILL,
    MISSING_SIGNAL_RAISE,
    Reexplode,
    SIGNAL_CATCHERS_KEY,
    DatumLifecycleWidget,
    compile_datum_widget_class,
    signal_catcher,
    thinkwidgetTM_config,
)

from _thinkprogram._thinkcontinuitykernelTM.api import (
    register_kernel_step_fn_v1,
)

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
from _thinkengine.runme.runme_offline_debug_against_actionscript import (
    SessionProgramScriptedHeadlessRunner,
)
from _thinkengine._app_table_engine._engine_runtime_events_emission.engine_events_mixin import (
    set_session_event_callback,
)


# =============================================================================
# Test helpers
# =============================================================================


def _api():
    return get_concrete_session_api(enable_persistence=False)


def _text_micro(
    name: str = "value",
    *,
    required: bool = True,
) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "text",
        "required": required,
    }


def _register_step(
    name: str,
    multiframespec: Mapping[str, Any],
) -> None:
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
    return [
        {
            "public_step_name": "class_adapter_step",
            "step_fn": step_name,
            "fn_args": {},
        }
    ]


def _single_q_multiframespec(
    *,
    widget_name: str,
    form_id: str,
    datum_id: str = "Q",
    max_reexplosions: int = 10,
) -> Dict[str, Any]:
    return {
        "app_form_id": form_id,
        "datums": [
            {
                "id": datum_id,
                "title": datum_id,
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": True,
                    "max_reexplosions": max_reexplosions,
                    "max_messages": 8,
                    "max_proc_notes": 0,
                },
            }
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": [datum_id],
                    }
                ],
            }
        ],
    }


def _multi_span_same_q_multiframespec(
    *,
    widget_name: str,
    form_id: str,
) -> Dict[str, Any]:
    return {
        "app_form_id": form_id,
        "datums": [
            {
                "id": "Q",
                "title": "Q",
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": True,
                    "max_reexplosions": 20,
                    "max_messages": 8,
                    "max_proc_notes": 0,
                },
            },
            {
                "id": "SIDE",
                "title": "Side",
                "micros": [_text_micro("value")],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {"id": "S_Q_1", "owns": ["Q"]},
                    {"id": "S_SIDE", "owns": ["SIDE"]},
                    {"id": "S_Q_2", "owns": ["Q"]},
                ],
            }
        ],
    }


def _latest_lifecycle_state(
    api: Any,
    sid: str,
    form_id: str,
    datum_id: str,
) -> Mapping[str, Any]:
    store = api._get(sid).state["_datum_lifecycle_v1"]
    return store["forms"][form_id]["datums"][datum_id]["state"]


# =============================================================================
# Example widgets used by tests
# =============================================================================


@thinkwidgetTM_config("test.adapter.profile", overwrite=True, missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL)
class ProfileAdapterWidget(DatumLifecycleWidget):
    def _base_lifecycle(self, fill_data: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            **dict(fill_data["fill_shell"].get("lifecycle") or {}),
            "widget": "test.adapter.profile",
            "mount_explode": True,
            "max_reexplosions": 20,
            "max_messages": 8,
            "max_proc_notes": 0,
        }

    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        assert fill_data["changed_fills"] == {}

        self.phase = "name"
        self.mounts = list(getattr(self, "mounts", []) or []) + [
            position["span_id"]
        ]
        self.mount_current_fills_seen = dict(fill_data["current_fills"])
        self.message("info", f"mounted on {position['span_id']}")

        return Reexplode(
            next_fill_shell={
                **dict(fill_data["fill_shell"]),
                "title": "Name",
                "micros": [_text_micro("name")],
                "lifecycle": self._base_lifecycle(fill_data),
            },
            pre_computed_fills={"name": ""},
            prefill_hints={"name": "Ada"},
        )

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        self.last_signal_seen = dict(signal)
        current = dict(fill_data["current_fills"])

        if getattr(self, "phase", None) == "name" and current.get("name"):
            self.phase = "email"
            self.name = current["name"]
            self.seen_changed_fills = dict(fill_data["changed_fills"])
            self.message("info", "name received")

            return Reexplode(
                next_fill_shell={
                    **dict(fill_data["fill_shell"]),
                    "title": "Email",
                    "micros": [_text_micro("email")],
                    "lifecycle": self._base_lifecycle(fill_data),
                },
                pre_computed_fills={"email": ""},
                prefill_hints={"email": f"{str(self.name).lower()}@example.com"},
            )

        if getattr(self, "phase", None) == "email" and current.get("email"):
            self.phase = "done"
            self.email = current["email"]
            self.message("success", "profile complete")
            return True

        raise ValueError("unexpected profile surface")

    @signal_catcher("refresh")
    def refresh(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        self.refresh_count = int(getattr(self, "refresh_count", 0) or 0) + 1
        self.refresh_signal_seen = dict(signal)
        self.refresh_current_fills_seen = dict(fill_data["current_fills"])
        self.message("info", "refreshed")

        return Reexplode(
            next_fill_shell=dict(fill_data["fill_shell"]),
            pre_computed_fills=dict(fill_data["current_fills"]),
            prefill_hints=dict(fill_data["prefill_hints"]),
        )


@thinkwidgetTM_config("test.adapter.raise_missing_signal", overwrite=True, missing_signal_handler_outcome=MISSING_SIGNAL_RAISE)
class RaiseMissingSignalWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        return Reexplode(
            next_fill_shell={
                **dict(fill_data["fill_shell"]),
                "micros": [_text_micro("value")],
                "lifecycle": {
                    **dict(fill_data["fill_shell"].get("lifecycle") or {}),
                    "widget": "test.adapter.raise_missing_signal",
                    "mount_explode": True,
                    "max_reexplosions": 5,
                },
            },
            pre_computed_fills={"value": ""},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        return True



@thinkwidgetTM_config("test.adapter.bad_return", overwrite=True)
class BadReturnWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        return {"status": "blocked"}

    def _on_fill(self, signal, position, fill_data, limits, stats):
        return {"status": "blocked"}


# =============================================================================
# Static adapter tests
# =============================================================================


def test_static_compilation_registers_plain_platform_lifecycle_fn() -> None:
    fn = getattr(ProfileAdapterWidget, "__datum_widget_compiled_fn_v1__")
    assert callable(fn)
    assert getattr(fn, "__datum_widget_class_v1__") is ProfileAdapterWidget

    catchers = getattr(fn, SIGNAL_CATCHERS_KEY)
    assert catchers == {"refresh": "refresh"}

    config = getattr(fn, CONFIG_KEY)
    assert (
        config["missing_signal_handler_outcome"]
        == MISSING_SIGNAL_FALLBACK_TO_FILL
    )


def test_compile_rejects_non_subclass() -> None:
    class NotAWidget:
        pass

    with pytest.raises(TypeError, match="must inherit DatumLifecycleWidget"):
        compile_datum_widget_class(NotAWidget)


def test_compile_rejects_bad_missing_signal_config() -> None:
    with pytest.raises(ValueError, match="missing_signal_handler_outcome"):
        @thinkwidgetTM_config("somwidgetname", missing_signal_handler_outcome="nonsense")
        class BadConfigWidget(DatumLifecycleWidget):
            def _on_mount(self, position, fill_data, limits, stats):
                return True

            def _on_fill(self, signal, position, fill_data, limits, stats):
                return True



def test_compile_rejects_missing_required_handlers() -> None:
    class MissingHandlersWidget(DatumLifecycleWidget):
        pass

    with pytest.raises(TypeError, match="_on_mount"):
        compile_datum_widget_class(MissingHandlersWidget)

    class MissingFillWidget(DatumLifecycleWidget):
        def _on_mount(self, position, fill_data, limits, stats):
            return True

    with pytest.raises(TypeError, match="_on_fill"):
        compile_datum_widget_class(MissingFillWidget)


def test_signal_catcher_rejects_blank_signal_name() -> None:
    with pytest.raises(ValueError, match="non-empty signal_name"):
        signal_catcher("")


def test_state_attribute_live_illusion_round_trips_through_platform_result() -> None:
    emitted = []

    q = {
        "form_id": "FORM",
        "frame_id": "F",
        "span_id": "S",
        "datum_id": "Q",
        "datum": {
            "id": "Q",
            "title": "Q",
            "micros": [_text_micro("value")],
            "lifecycle": {
                "widget": "test.adapter.profile",
                "mount_explode": True,
                "max_reexplosions": 10,
            },
        },
        "raw_fill": None,
        "partial_fill": {},
        "prefill": {},
        "state": {},
        "messages": [],
        "proc_notes": [],
        "structurally_satisfied": False,
        "reexplode_count": 0,
        "max_reexplosions": 10,
        "max_proc_notes": 0,
        "max_messages": 8,
        "signal": {"kind": "mount", "info": {}},
        "signal_kind": "mount",
        "signal_info": {},
        "ctx": {},
        "emit": (
            lambda payload=None, **kw:
            emitted.append({"payload": payload, **kw})
            or {"payload": payload, **kw}
        ),
    }

    fn = getattr(ProfileAdapterWidget, "__datum_widget_compiled_fn_v1__")
    result = fn(q)

    assert result["status"] == "reexplode"
    assert result["state"]["phase"] == "name"
    assert result["state"]["mounts"] == ["S"]
    assert result["state"]["mount_current_fills_seen"] == {}
    assert result["state"][ADAPTER_RESERVED_STATE_KEY]["last_precomputed_fills"] == {
        "name": ""
    }

    assert result["fill"] == {"name": ""}
    assert result["prefill"] == {"name": "Ada"}
    assert result["messages"] == [{"level": "info", "text": "mounted on S"}]
    assert "proc_notes" not in result
    assert "events" not in result

    assert emitted
    assert emitted[-1]["payload"] == {
        "message": {
            "level": "info",
            "text": "mounted on S",
        }
    }


def test_mount_allows_existing_current_fills_but_no_changed_fills() -> None:
    q = {
        "form_id": "FORM",
        "frame_id": "F",
        "span_id": "S2",
        "datum_id": "Q",
        "datum": {
            "id": "Q",
            "title": "Q",
            "micros": [_text_micro("value")],
            "lifecycle": {
                "widget": "test.adapter.profile",
                "mount_explode": True,
                "max_reexplosions": 10,
            },
        },
        "raw_fill": {"email": "first@example.com"},
        "partial_fill": {"email": "first@example.com"},
        "prefill": {},
        "state": {
            "phase": "done",
            "mounts": ["S1"],
            ADAPTER_RESERVED_STATE_KEY: {
                "last_precomputed_fills": {"email": ""},
            },
        },
        "messages": [],
        "proc_notes": [],
        "structurally_satisfied": True,
        "reexplode_count": 4,
        "max_reexplosions": 10,
        "max_proc_notes": 0,
        "max_messages": 8,
        "signal": {"kind": "mount", "info": {}},
        "signal_kind": "mount",
        "signal_info": {},
        "ctx": {},
        "emit": lambda payload=None, **kw: {"payload": payload, **kw},
    }

    fn = getattr(ProfileAdapterWidget, "__datum_widget_compiled_fn_v1__")
    result = fn(q)

    assert result["status"] == "reexplode"
    assert result["state"]["mounts"] == ["S1", "S2"]
    assert result["state"]["mount_current_fills_seen"] == {
        "email": "first@example.com"
    }
    assert result["state"]["phase"] == "name"


def test_changed_fills_is_value_delta_not_source_causality() -> None:
    q = {
        "form_id": "FORM",
        "frame_id": "F",
        "span_id": "S",
        "datum_id": "Q",
        "datum": {
            "id": "Q",
            "title": "Name",
            "micros": [_text_micro("name")],
            "lifecycle": {
                "widget": "test.adapter.profile",
                "mount_explode": True,
                "max_reexplosions": 10,
            },
        },
        "raw_fill": {"name": "Ada"},
        "partial_fill": {"name": "Ada"},
        "prefill": {},
        "state": {
            "phase": "name",
            ADAPTER_RESERVED_STATE_KEY: {
                "last_precomputed_fills": {"name": ""},
            },
        },
        "messages": [],
        "proc_notes": [],
        "structurally_satisfied": True,
        "reexplode_count": 1,
        "max_reexplosions": 10,
        "max_proc_notes": 0,
        "max_messages": 8,
        "signal": {"kind": "fill", "info": {}},
        "signal_kind": "fill",
        "signal_info": {},
        "ctx": {},
        "emit": lambda payload=None, **kw: {"payload": payload, **kw},
    }

    fn = getattr(ProfileAdapterWidget, "__datum_widget_compiled_fn_v1__")
    result = fn(q)

    assert result["status"] == "reexplode"
    assert result["state"]["seen_changed_fills"] == {"name": "Ada"}

    q_same_again = dict(q)
    q_same_again["state"] = {
        "phase": "name",
        ADAPTER_RESERVED_STATE_KEY: {
            "last_precomputed_fills": {"name": "Ada"},
        },
    }

    result_same = fn(q_same_again)
    assert result_same["state"]["seen_changed_fills"] == {}


def test_bad_handler_return_is_rejected_before_platform_runtime_contract() -> None:
    q = {
        "form_id": "FORM",
        "frame_id": "F",
        "span_id": "S",
        "datum_id": "Q",
        "datum": {
            "id": "Q",
            "title": "Q",
            "micros": [_text_micro("value")],
            "lifecycle": {
                "widget": "test.adapter.bad_return",
                "mount_explode": True,
                "max_reexplosions": 10,
            },
        },
        "raw_fill": None,
        "partial_fill": {},
        "prefill": {},
        "state": {},
        "messages": [],
        "proc_notes": [],
        "structurally_satisfied": False,
        "reexplode_count": 0,
        "max_reexplosions": 10,
        "max_proc_notes": 0,
        "max_messages": 8,
        "signal": {"kind": "mount", "info": {}},
        "signal_kind": "mount",
        "signal_info": {},
        "ctx": {},
        "emit": lambda payload=None, **kw: {"payload": payload, **kw},
    }

    fn = getattr(BadReturnWidget, "__datum_widget_compiled_fn_v1__")

    with pytest.raises(TypeError, match="True or Reexplode"):
        fn(q)


def test_message_acceots_any_str_as_message_level() -> None:
    class LevelWidget(DatumLifecycleWidget):
        pass

    instance = LevelWidget(
        q={"state": {}},
        emit=lambda payload=None, **kw: {"payload": payload, **kw},
    )


    instance.message("anythinggoesman", "not allowed")
    instance.message("WOOHOOOOOOOO", "not allowed")
    instance.message("THISISFORYOURDIVHAHA", "not allowed")



# =============================================================================
# End-to-end engine tests
# =============================================================================


def test_e2e_mount_reexplode_fill_reexplode_done_with_state_and_messages() -> None:
    form_id = "adapter.e2e.profile"
    step_name = "adapter.e2e.profile.step"

    _register_step(
        step_name,
        _single_q_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

    seen_events = []
    set_session_event_callback(lambda ev: seen_events.append(dict(ev)))

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

    ctx = runner.step_until_stop()
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert "name" in str(ctx["datum_widget_decls"]["Q"])

    state_after_mount = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert state_after_mount["phase"] == "name"
    assert state_after_mount["mounts"] == ["S"]
    assert state_after_mount["mount_current_fills_seen"] == {}

    drained = api.drain_session_events(sid)
    assert drained
    assert drained[-1]["name"] == MESSAGE_EVENT_NAME
    assert drained[-1]["payload"]["message"]["text"] == "mounted on S"

    ctx = runner.step(fill={"Q": {"name": "Ada"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "email" in str(ctx["datum_widget_decls"]["Q"])

    state_after_name = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert state_after_name["phase"] == "email"
    assert state_after_name["name"] == "Ada"
    assert state_after_name["seen_changed_fills"] == {"name": "Ada"}
    assert state_after_name[ADAPTER_RESERVED_STATE_KEY]["last_precomputed_fills"] == {
        "email": ""
    }

    ctx = runner.step(fill={"Q": {"email": "ada@example.com"}})
    assert ctx["kind"] == "ATCOMPLETION"

    final_state = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert final_state["phase"] == "done"
    assert final_state["email"] == "ada@example.com"

    out = api.get_outputs(sid)
    assert out["form_fills"]["Q"] == {"email": "ada@example.com"}

    assert seen_events
    assert seen_events[-1]["payload"]["message"]["level"] == "success"
    assert seen_events[-1]["payload"]["message"]["text"] == "profile complete"

    set_session_event_callback(None)


def test_e2e_controller_custom_signal_dispatches_to_signal_catcher() -> None:
    form_id = "adapter.e2e.signal"
    step_name = "adapter.e2e.signal.step"

    _register_step(
        step_name,
        _single_q_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

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

    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "name" in str(ctx["datum_widget_decls"]["Q"])

    ctx = api.step_session(
        sid,
        signal={
            "datum_id": "Q",
            "kind": "refresh",
            "info": {"reason": "test"},
        },
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    state_after_signal = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert state_after_signal["refresh_count"] == 1
    assert state_after_signal["refresh_signal_seen"]["kind"] == "refresh"
    assert state_after_signal["refresh_signal_seen"]["info"]["reason"] == "test"

    drained = api.drain_session_events(sid)
    assert drained[-1]["payload"]["message"]["text"] == "refreshed"


def test_e2e_controller_custom_signal_can_arrive_with_fill() -> None:
    form_id = "adapter.e2e.signal_with_fill"
    step_name = "adapter.e2e.signal_with_fill.step"

    _register_step(
        step_name,
        _single_q_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

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

    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "name" in str(ctx["datum_widget_decls"]["Q"])

    ctx = api.step_session(
        sid,
        fill={"Q": {"name": "SignalName"}},
        signal={
            "datum_id": "Q",
            "kind": "refresh",
            "info": {"reason": "signal-and-fill"},
        },
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    state_after_signal = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert state_after_signal["refresh_count"] == 1
    assert state_after_signal["refresh_current_fills_seen"] == {
        "name": "SignalName"
    }
    assert state_after_signal[ADAPTER_RESERVED_STATE_KEY][
        "last_precomputed_fills"
    ] == {"name": "SignalName"}


def test_e2e_missing_custom_signal_raises_when_configured_to_raise() -> None:
    form_id = "adapter.e2e.missing_signal"
    step_name = "adapter.e2e.missing_signal.step"

    _register_step(
        step_name,
        _single_q_multiframespec(
            widget_name="test.adapter.raise_missing_signal",
            form_id=form_id,
        ),
    )

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

    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    with pytest.raises(Exception, match="no @signal_catcher"):
        api.step_session(
            sid,
            signal={
                "datum_id": "Q",
                "kind": "unknown_custom_signal",
                "info": {},
            },
        )


def test_e2e_same_logical_datum_respans_and_self_state_survives() -> None:
    form_id = "adapter.e2e.respan"
    step_name = "adapter.e2e.respan.step"

    _register_step(
        step_name,
        _multi_span_same_q_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

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

    ctx = api.step_session(sid)
    assert ctx["current_span"] == "S_Q_1"
    assert "name" in str(ctx["datum_widget_decls"]["Q"])

    ctx = api.step_session(sid, fill={"Q": {"name": "First"}})
    assert ctx["current_span"] == "S_Q_1"
    assert "email" in str(ctx["datum_widget_decls"]["Q"])

    ctx = api.step_session(sid, fill={"Q": {"email": "first@example.com"}})
    assert ctx["current_span"] == "S_SIDE"

    ctx = api.step_session(sid, fill={"SIDE": {"value": "side"}})
    assert ctx["current_span"] == "S_Q_2"
    assert "name" in str(ctx["datum_widget_decls"]["Q"])

    state_after_second_mount = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert state_after_second_mount["mounts"] == ["S_Q_1", "S_Q_2"]
    assert state_after_second_mount["phase"] == "name"
    assert state_after_second_mount["mount_current_fills_seen"] == {
        "email": "first@example.com"
    }

    ctx = api.step_session(sid, fill={"Q": {"name": "Second"}})
    assert ctx["current_span"] == "S_Q_2"

    ctx = api.step_session(sid, fill={"Q": {"email": "second@example.com"}})
    assert ctx["kind"] == "ATCOMPLETION"

    final_state = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert final_state["mounts"] == ["S_Q_1", "S_Q_2"]
    assert final_state["name"] == "Second"
    assert final_state["email"] == "second@example.com"


def test_e2e_undo_redo_keeps_adapter_state_and_reexplode_surface_consistent() -> None:
    form_id = "adapter.e2e.undo_redo"
    step_name = "adapter.e2e.undo_redo.step"

    _register_step(
        step_name,
        _single_q_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

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

    ctx = api.step_session(sid)
    assert "name" in str(ctx["datum_widget_decls"]["Q"])

    ctx = api.step_session(sid, fill={"Q": {"name": "Ada"}})
    assert "email" in str(ctx["datum_widget_decls"]["Q"])

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "name" in str(ctx["datum_widget_decls"]["Q"])
    assert "email" not in str(ctx["datum_widget_decls"]["Q"])

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "email" in str(ctx["datum_widget_decls"]["Q"])

    state_after_redo = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert state_after_redo["phase"] == "email"
    assert state_after_redo["name"] == "Ada"







# ---------------------------------------------------------------------------
# Addendum: class inheritance semantics
# ---------------------------------------------------------------------------
#
# These tests prove that the class adapter treats widget classes like normal
# Python classes:
#
#   * lifecycle methods may be inherited
#   * lifecycle methods may be overridden
#   * signal catchers may be inherited
#   * signal catchers may be added by subclasses
#   * signal catchers may be overridden by subclasses for the same signal name
#   * custom helper methods used inside responders participate in normal MRO
#   * inherited responders call overridden helper methods through dynamic dispatch
#   * sibling subclasses do not leak catchers/config/registration into each other
#
# The tests intentionally call compiled lifecycle functions directly. This keeps
# the inheritance proof focused on the adapter surface rather than re-testing the
# engine/session/controller paths already covered above.


def _inheritance_emit_log():
    events = []

    def _emit(payload=None, **kwargs):
        packet = {
            "payload": dict(payload or {}),
            "name": kwargs.get("name"),
            "channel": kwargs.get("channel"),
            "audience": kwargs.get("audience"),
        }
        events.append(packet)
        return packet

    return events, _emit


def _inheritance_q(
    *,
    kind="mount",
    state=None,
    datum=None,
    partial_fill=None,
    prefill=None,
    signal_info=None,
    messages=None,
    form_id="F_INHERIT",
    frame_id="Frame_INHERIT",
    span_id="Span_INHERIT",
    datum_id="Q_INHERIT",
    emit=None,
):
    signal_info = dict(signal_info or {})
    partial_fill = dict(partial_fill or {})
    signal = {"kind": kind, "info": signal_info}

    return {
        "form_id": form_id,
        "frame_id": frame_id,
        "span_id": span_id,
        "datum_id": datum_id,
        "datum": dict(
            datum
            or {
                "widget": "test.adapter.inheritance.full",
                "field": "first",
                "required": True,
            }
        ),
        "prefill": dict(prefill or {}),
        "raw_fill": dict(partial_fill),
        "partial_fill": dict(partial_fill),
        "structurally_satisfied": bool(partial_fill),
        "state": dict(state or {}),
        "messages": list(messages or []),
        "proc_notes": [],
        "max_reexplosions": 10,
        "max_proc_notes": 0,
        "max_messages": 20,
        "reexplode_count": 0,
        "signal": signal,
        "signal_kind": kind,
        "signal_info": signal_info,
        "ctx": {},
        "emit": emit or (lambda payload=None, **kwargs: {"payload": payload, **kwargs}),
    }


class InheritanceBaseWidget(DatumLifecycleWidget):
    """
    Deliberately not registered.

    This class supplies:
      * inherited mount handler
      * inherited fill handler
      * inherited signal catcher
      * helper methods used by those handlers
    """

    def _helper_chain(self):
        return ["base"]

    def _chain_text(self):
        return ">".join(self._helper_chain())

    def _note(self, action):
        return f"{action}:{self._chain_text()}"

    def _current_history(self):
        return list(self._state.get("history", []))

    def _append_history(self, entry):
        history = self._current_history()
        history.append(entry)
        self.history = history

    def _next_shell(self, field_name):
        return {
            "widget": "test.adapter.inheritance.full",
            "field": field_name,
            "required": True,
        }

    def _on_mount(self, position, fill_data, limits, stats):
        # This method is inherited by both concrete subclasses below.
        # It calls helper methods that are overridden in subclasses; the asserts
        # in tests prove normal dynamic dispatch is preserved.
        assert fill_data["changed_fills"] == {}

        self.mount_handler_owner = "InheritanceBaseWidget._on_mount"
        self.mount_chain_seen = self._chain_text()
        self.mount_note_seen = self._note("mount")
        self.mount_current_fills_seen = dict(fill_data["current_fills"])
        self.mount_span_seen = position["span_id"]
        self._append_history(f"mount:{self._chain_text()}")

        self.message("info", self._note("mount"))

        return Reexplode(
            next_fill_shell=self._next_shell("first"),
            pre_computed_fills={"first": ""},
            prefill_hints={"first": self._note("prefill_first")},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        # This base fill handler is intentionally inherited by one subclass and
        # overridden by another.
        self.fill_handler_owner = "InheritanceBaseWidget._on_fill"
        self.fill_chain_seen = self._chain_text()
        self.fill_signal_seen = dict(signal)
        self.fill_current_fills_seen = dict(fill_data["current_fills"])
        self._append_history(f"base_fill:{self._chain_text()}")

        self.message("success", self._note("base_fill_done"))
        return True

    @signal_catcher("base_ping")
    def base_ping(self, signal, position, fill_data, limits, stats):
        # This catcher is inherited by one subclass and overridden by another.
        self.signal_handler_owner = "InheritanceBaseWidget.base_ping"
        self.signal_chain_seen = self._chain_text()
        self.signal_seen = dict(signal)
        self.signal_current_fills_seen = dict(fill_data["current_fills"])
        self._append_history(f"base_ping:{self._chain_text()}")

        self.message("info", self._note("base_ping"))

        return Reexplode(
            next_fill_shell=dict(fill_data["fill_shell"]),
            pre_computed_fills=dict(fill_data["current_fills"]),
            prefill_hints=dict(fill_data["prefill_hints"]),
        )


class InheritanceMiddleWidget(InheritanceBaseWidget):
    """
    Deliberately not registered.

    This class modifies helper behavior and adds a signal catcher.
    """

    def _helper_chain(self):
        return super()._helper_chain() + ["middle"]

    def _middle_only_helper(self):
        return f"middle_only:{self._chain_text()}"

    @signal_catcher("middle_ping")
    def middle_ping(self, signal, position, fill_data, limits, stats):
        self.signal_handler_owner = "InheritanceMiddleWidget.middle_ping"
        self.signal_chain_seen = self._chain_text()
        self.middle_helper_seen = self._middle_only_helper()
        self.signal_seen = dict(signal)
        self._append_history(f"middle_ping:{self._chain_text()}")

        self.message("warning", self._note("middle_ping"))

        return Reexplode(
            next_fill_shell=dict(fill_data["fill_shell"]),
            pre_computed_fills=dict(fill_data["current_fills"]),
            prefill_hints=dict(fill_data["prefill_hints"]),
        )


@thinkwidgetTM_config("test.adapter.inheritance.full", overwrite=True, missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL)
class InheritanceFullWidget(InheritanceMiddleWidget):
    """
    Concrete leaf class.

    Inherits:
      * _on_mount from base
      * middle_ping from middle

    Overrides:
      * _helper_chain
      * _on_fill
      * base_ping for the same signal name as the base class

    Adds:
      * child_ping
      * child-only helper used by overridden fill and child signal catcher
    """

    def _helper_chain(self):
        return super()._helper_chain() + ["full"]

    def _full_only_helper(self):
        return f"full_only:{self._chain_text()}"

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.fill_handler_owner = "InheritanceFullWidget._on_fill"
        self.fill_chain_seen = self._chain_text()
        self.full_helper_seen = self._full_only_helper()
        self.middle_helper_seen_from_fill = self._middle_only_helper()
        self.fill_signal_seen = dict(signal)
        self.fill_current_fills_seen = dict(fill_data["current_fills"])
        self.fill_changed_fills_seen = dict(fill_data["changed_fills"])
        self._append_history(f"full_fill:{self._chain_text()}")

        if "first" in fill_data["current_fills"] and "second" not in fill_data["current_fills"]:
            self.message("info", self._note("full_fill_to_second"))
            return Reexplode(
                next_fill_shell=self._next_shell("second"),
                pre_computed_fills={"second": ""},
                prefill_hints={"second": self._note("prefill_second")},
            )

        self.message("success", self._note("full_fill_done"))
        return True

    @signal_catcher("base_ping")
    def base_ping_override(self, signal, position, fill_data, limits, stats):
        self.signal_handler_owner = "InheritanceFullWidget.base_ping_override"
        self.signal_chain_seen = self._chain_text()
        self.full_helper_seen_from_signal = self._full_only_helper()
        self.signal_seen = dict(signal)
        self.signal_current_fills_seen = dict(fill_data["current_fills"])
        self._append_history(f"full_base_ping_override:{self._chain_text()}")

        self.message("info", self._note("full_base_ping_override"))

        return Reexplode(
            next_fill_shell=dict(fill_data["fill_shell"]),
            pre_computed_fills=dict(fill_data["current_fills"]),
            prefill_hints=dict(fill_data["prefill_hints"]),
        )

    @signal_catcher("child_ping")
    def child_ping(self, signal, position, fill_data, limits, stats):
        self.signal_handler_owner = "InheritanceFullWidget.child_ping"
        self.signal_chain_seen = self._chain_text()
        self.full_helper_seen_from_signal = self._full_only_helper()
        self.middle_helper_seen_from_signal = self._middle_only_helper()
        self.signal_seen = dict(signal)
        self._append_history(f"child_ping:{self._chain_text()}")

        self.message("success", self._note("child_ping"))

        return True


@thinkwidgetTM_config("test.adapter.inheritance.sibling", overwrite=True, missing_signal_handler_outcome=MISSING_SIGNAL_RAISE)
class InheritanceSiblingWidget(InheritanceMiddleWidget):
    """
    Concrete sibling class.

    Inherits:
      * _on_mount from base
      * _on_fill from base
      * base_ping from base
      * middle_ping from middle

    Does not inherit anything from InheritanceFullWidget.
    """

    def _helper_chain(self):
        return super()._helper_chain() + ["sibling"]


@thinkwidgetTM_config("test.adapter.inheritance.override_fill_only", overwrite=True, missing_signal_handler_outcome=MISSING_SIGNAL_RAISE)
class InheritanceOverrideFillOnlyWidget(InheritanceBaseWidget):
    """
    Concrete class proving override of _on_fill while still inheriting mount and
    base signal catcher.
    """

    def _helper_chain(self):
        return super()._helper_chain() + ["override_fill_only"]

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.fill_handler_owner = "InheritanceOverrideFillOnlyWidget._on_fill"
        self.fill_chain_seen = self._chain_text()
        self._append_history(f"override_fill_only_fill:{self._chain_text()}")
        self.message("success", self._note("override_fill_only_done"))
        return True


def test_inheritance_inherited_mount_uses_leaf_helper_overrides():
    events, emit = _inheritance_emit_log()
    fn = compile_datum_widget_class(InheritanceFullWidget)

    result = fn(
        _inheritance_q(
            kind="mount",
            emit=emit,
            datum={
                "widget": "test.adapter.inheritance.full",
                "field": "initial",
                "required": True,
            },
        )
    )

    assert result["status"] == "reexplode"
    assert result["datum"]["field"] == "first"
    assert result["fill"] == {"first": ""}
    assert result["prefill"] == {"first": "prefill_first:base>middle>full"}

    state = result["state"]
    assert state["mount_handler_owner"] == "InheritanceBaseWidget._on_mount"
    assert state["mount_chain_seen"] == "base>middle>full"
    assert state["mount_note_seen"] == "mount:base>middle>full"
    assert state["mount_current_fills_seen"] == {}
    assert state["history"] == ["mount:base>middle>full"]

    assert result["messages"] == [
        {"level": "info", "text": "mount:base>middle>full"}
    ]

    assert len(events) == 1
    assert events[0]["name"] == MESSAGE_EVENT_NAME
    assert events[0]["payload"] == {
        "message": {"level": "info", "text": "mount:base>middle>full"}
    }


def test_inheritance_overridden_fill_uses_inherited_and_leaf_helpers():
    events, emit = _inheritance_emit_log()
    fn = compile_datum_widget_class(InheritanceFullWidget)

    mounted = fn(_inheritance_q(kind="mount", emit=emit))
    filled = fn(
        _inheritance_q(
            kind="fill",
            emit=emit,
            state=mounted["state"],
            datum=mounted["datum"],
            prefill=mounted["prefill"],
            partial_fill={"first": "Ada"},
        )
    )

    assert filled["status"] == "reexplode"
    assert filled["datum"]["field"] == "second"
    assert filled["fill"] == {"second": ""}
    assert filled["prefill"] == {"second": "prefill_second:base>middle>full"}

    state = filled["state"]
    assert state["fill_handler_owner"] == "InheritanceFullWidget._on_fill"
    assert state["fill_chain_seen"] == "base>middle>full"
    assert state["full_helper_seen"] == "full_only:base>middle>full"
    assert state["middle_helper_seen_from_fill"] == "middle_only:base>middle>full"
    assert state["fill_signal_seen"] == {"kind": "fill", "info": {}}
    assert state["fill_current_fills_seen"] == {"first": "Ada"}

    # The delta is computed against the adapter-reserved previous
    # precomputed fill from mount: {"first": ""}.
    assert state["fill_changed_fills_seen"] == {"first": "Ada"}

    assert state["history"] == [
        "mount:base>middle>full",
        "full_fill:base>middle>full",
    ]

    assert filled["messages"] == [
        {"level": "info", "text": "full_fill_to_second:base>middle>full"}
    ]


def test_inheritance_overridden_fill_can_complete_on_second_surface():
    events, emit = _inheritance_emit_log()
    fn = compile_datum_widget_class(InheritanceFullWidget)

    mounted = fn(_inheritance_q(kind="mount", emit=emit))
    first = fn(
        _inheritance_q(
            kind="fill",
            emit=emit,
            state=mounted["state"],
            datum=mounted["datum"],
            prefill=mounted["prefill"],
            partial_fill={"first": "Ada"},
        )
    )
    second = fn(
        _inheritance_q(
            kind="fill",
            emit=emit,
            state=first["state"],
            datum=first["datum"],
            prefill=first.get("prefill", {}),
            partial_fill={"second": "ada@example.com"},
        )
    )

    assert second["status"] == "done"

    state = second["state"]
    assert state["fill_handler_owner"] == "InheritanceFullWidget._on_fill"
    assert state["fill_chain_seen"] == "base>middle>full"
    assert state["full_helper_seen"] == "full_only:base>middle>full"
    assert state["middle_helper_seen_from_fill"] == "middle_only:base>middle>full"
    assert state["fill_current_fills_seen"] == {"second": "ada@example.com"}
    assert state["fill_changed_fills_seen"] == {"second": "ada@example.com"}
    assert state["history"] == [
        "mount:base>middle>full",
        "full_fill:base>middle>full",
        "full_fill:base>middle>full",
    ]

    assert second["messages"] == [
        {"level": "success", "text": "full_fill_done:base>middle>full"}
    ]


def test_inheritance_middle_signal_catcher_is_inherited_by_leaf_class():
    events, emit = _inheritance_emit_log()
    fn = compile_datum_widget_class(InheritanceFullWidget)

    mounted = fn(_inheritance_q(kind="mount", emit=emit))
    result = fn(
        _inheritance_q(
            kind="middle_ping",
            emit=emit,
            state=mounted["state"],
            datum=mounted["datum"],
            prefill=mounted["prefill"],
            partial_fill={"first": "Ada"},
            signal_info={"source": "test"},
        )
    )

    assert result["status"] == "reexplode"

    state = result["state"]
    assert state["signal_handler_owner"] == "InheritanceMiddleWidget.middle_ping"
    assert state["signal_chain_seen"] == "base>middle>full"
    assert state["middle_helper_seen"] == "middle_only:base>middle>full"
    assert state["signal_seen"] == {
        "kind": "middle_ping",
        "info": {"source": "test"},
    }
    assert state["history"] == [
        "mount:base>middle>full",
        "middle_ping:base>middle>full",
    ]

    assert result["messages"] == [
        {"level": "warning", "text": "middle_ping:base>middle>full"}
    ]


def test_inheritance_leaf_signal_catcher_can_use_inherited_helpers():
    events, emit = _inheritance_emit_log()
    fn = compile_datum_widget_class(InheritanceFullWidget)

    mounted = fn(_inheritance_q(kind="mount", emit=emit))
    result = fn(
        _inheritance_q(
            kind="child_ping",
            emit=emit,
            state=mounted["state"],
            datum=mounted["datum"],
            prefill=mounted["prefill"],
            partial_fill={"first": "Ada"},
            signal_info={"nonce": 123},
        )
    )

    assert result["status"] == "done"

    state = result["state"]
    assert state["signal_handler_owner"] == "InheritanceFullWidget.child_ping"
    assert state["signal_chain_seen"] == "base>middle>full"
    assert state["full_helper_seen_from_signal"] == "full_only:base>middle>full"
    assert state["middle_helper_seen_from_signal"] == "middle_only:base>middle>full"
    assert state["signal_seen"] == {
        "kind": "child_ping",
        "info": {"nonce": 123},
    }
    assert state["history"] == [
        "mount:base>middle>full",
        "child_ping:base>middle>full",
    ]

    assert result["messages"] == [
        {"level": "success", "text": "child_ping:base>middle>full"}
    ]


def test_inheritance_leaf_signal_catcher_overrides_same_signal_from_base():
    events, emit = _inheritance_emit_log()
    fn = compile_datum_widget_class(InheritanceFullWidget)

    mounted = fn(_inheritance_q(kind="mount", emit=emit))
    result = fn(
        _inheritance_q(
            kind="base_ping",
            emit=emit,
            state=mounted["state"],
            datum=mounted["datum"],
            prefill=mounted["prefill"],
            partial_fill={"first": "Ada"},
        )
    )

    assert result["status"] == "reexplode"

    state = result["state"]
    assert state["signal_handler_owner"] == "InheritanceFullWidget.base_ping_override"
    assert state["signal_chain_seen"] == "base>middle>full"
    assert state["full_helper_seen_from_signal"] == "full_only:base>middle>full"
    assert state["signal_current_fills_seen"] == {"first": "Ada"}
    assert state["history"] == [
        "mount:base>middle>full",
        "full_base_ping_override:base>middle>full",
    ]

    assert result["messages"] == [
        {"level": "info", "text": "full_base_ping_override:base>middle>full"}
    ]


def test_inheritance_sibling_inherits_base_signal_when_not_overridden():
    events, emit = _inheritance_emit_log()
    fn = compile_datum_widget_class(InheritanceSiblingWidget)

    mounted = fn(
        _inheritance_q(
            kind="mount",
            emit=emit,
            datum={
                "widget": "test.adapter.inheritance.sibling",
                "field": "initial",
                "required": True,
            },
        )
    )
    result = fn(
        _inheritance_q(
            kind="base_ping",
            emit=emit,
            state=mounted["state"],
            datum=mounted["datum"],
            prefill=mounted["prefill"],
            partial_fill={"first": "Ada"},
        )
    )

    assert result["status"] == "reexplode"

    state = result["state"]
    assert state["mount_handler_owner"] == "InheritanceBaseWidget._on_mount"
    assert state["mount_chain_seen"] == "base>middle>sibling"

    assert state["signal_handler_owner"] == "InheritanceBaseWidget.base_ping"
    assert state["signal_chain_seen"] == "base>middle>sibling"
    assert state["signal_current_fills_seen"] == {"first": "Ada"}
    assert state["history"] == [
        "mount:base>middle>sibling",
        "base_ping:base>middle>sibling",
    ]

    assert result["messages"] == [
        {"level": "info", "text": "base_ping:base>middle>sibling"}
    ]


def test_inheritance_sibling_inherits_base_fill_when_not_overridden():
    events, emit = _inheritance_emit_log()
    fn = compile_datum_widget_class(InheritanceSiblingWidget)

    mounted = fn(
        _inheritance_q(
            kind="mount",
            emit=emit,
            datum={
                "widget": "test.adapter.inheritance.sibling",
                "field": "initial",
                "required": True,
            },
        )
    )
    result = fn(
        _inheritance_q(
            kind="fill",
            emit=emit,
            state=mounted["state"],
            datum=mounted["datum"],
            prefill=mounted["prefill"],
            partial_fill={"first": "Ada"},
        )
    )

    assert result["status"] == "done"

    state = result["state"]
    assert state["fill_handler_owner"] == "InheritanceBaseWidget._on_fill"
    assert state["fill_chain_seen"] == "base>middle>sibling"
    assert state["fill_signal_seen"] == {"kind": "fill", "info": {}}
    assert state["fill_current_fills_seen"] == {"first": "Ada"}
    assert state["history"] == [
        "mount:base>middle>sibling",
        "base_fill:base>middle>sibling",
    ]

    assert result["messages"] == [
        {"level": "success", "text": "base_fill_done:base>middle>sibling"}
    ]


def test_inheritance_override_fill_only_keeps_inherited_mount_and_signal():
    events, emit = _inheritance_emit_log()
    fn = compile_datum_widget_class(InheritanceOverrideFillOnlyWidget)

    mounted = fn(
        _inheritance_q(
            kind="mount",
            emit=emit,
            datum={
                "widget": "test.adapter.inheritance.override_fill_only",
                "field": "initial",
                "required": True,
            },
        )
    )
    filled = fn(
        _inheritance_q(
            kind="fill",
            emit=emit,
            state=mounted["state"],
            datum=mounted["datum"],
            prefill=mounted["prefill"],
            partial_fill={"first": "Ada"},
        )
    )
    signaled = fn(
        _inheritance_q(
            kind="base_ping",
            emit=emit,
            state=filled["state"],
            datum=mounted["datum"],
            prefill=mounted["prefill"],
            partial_fill={"first": "Ada"},
        )
    )

    assert mounted["status"] == "reexplode"
    assert filled["status"] == "done"
    assert signaled["status"] == "reexplode"

    state = signaled["state"]
    assert state["mount_handler_owner"] == "InheritanceBaseWidget._on_mount"
    assert state["mount_chain_seen"] == "base>override_fill_only"

    assert state["fill_handler_owner"] == "InheritanceOverrideFillOnlyWidget._on_fill"
    assert state["fill_chain_seen"] == "base>override_fill_only"

    assert state["signal_handler_owner"] == "InheritanceBaseWidget.base_ping"
    assert state["signal_chain_seen"] == "base>override_fill_only"

    assert state["history"] == [
        "mount:base>override_fill_only",
        "override_fill_only_fill:base>override_fill_only",
        "base_ping:base>override_fill_only",
    ]


def test_inheritance_missing_signal_policy_is_subclass_specific():
    events, emit = _inheritance_emit_log()

    full_fn = compile_datum_widget_class(InheritanceFullWidget)
    sibling_fn = compile_datum_widget_class(InheritanceSiblingWidget)

    full_mounted = full_fn(_inheritance_q(kind="mount", emit=emit))
    full_result = full_fn(
        _inheritance_q(
            kind="unknown_signal",
            emit=emit,
            state=full_mounted["state"],
            datum=full_mounted["datum"],
            prefill=full_mounted["prefill"],
            partial_fill={"first": "Ada"},
        )
    )

    assert full_result["status"] == "reexplode"
    assert full_result["state"]["fill_handler_owner"] == "InheritanceFullWidget._on_fill"
    assert full_result["state"]["fill_signal_seen"] == {
        "kind": "unknown_signal",
        "info": {},
    }

    sibling_mounted = sibling_fn(
        _inheritance_q(
            kind="mount",
            emit=emit,
            datum={
                "widget": "test.adapter.inheritance.sibling",
                "field": "initial",
                "required": True,
            },
        )
    )

    with pytest.raises(NotImplementedError):
        sibling_fn(
            _inheritance_q(
                kind="unknown_signal",
                emit=emit,
                state=sibling_mounted["state"],
                datum=sibling_mounted["datum"],
                prefill=sibling_mounted["prefill"],
                partial_fill={"first": "Ada"},
            )
        )


def test_inheritance_signal_catcher_collection_respects_mro_override_resolution():
    full_fn = compile_datum_widget_class(InheritanceFullWidget)
    sibling_fn = compile_datum_widget_class(InheritanceSiblingWidget)

    full_catchers = getattr(full_fn, "__datum_widget_signal_catchers_v1__")
    sibling_catchers = getattr(sibling_fn, "__datum_widget_signal_catchers_v1__")

    assert set(full_catchers) == {"base_ping", "middle_ping", "child_ping"}
    assert set(sibling_catchers) == {"base_ping", "middle_ping"}

    assert full_catchers["base_ping"] == "base_ping_override"
    assert full_catchers["middle_ping"] == "middle_ping"
    assert full_catchers["child_ping"] == "child_ping"

    assert sibling_catchers["base_ping"] == "base_ping"
    assert sibling_catchers["middle_ping"] == "middle_ping"


def test_inheritance_registered_names_are_subclass_specific():
    full_name = getattr(InheritanceFullWidget, "__datum_widget_registered_name_v1__")
    sibling_name = getattr(InheritanceSiblingWidget, "__datum_widget_registered_name_v1__")
    override_name = getattr(
        InheritanceOverrideFillOnlyWidget,
        "__datum_widget_registered_name_v1__",
    )

    assert full_name == "test.adapter.inheritance.full"
    assert sibling_name == "test.adapter.inheritance.sibling"
    assert override_name == "test.adapter.inheritance.override_fill_only"

    assert full_name != sibling_name
    assert full_name != override_name
    assert sibling_name != override_name


def test_inheritance_compiled_functions_are_plain_distinct_lifecycle_functions():
    full_fn = compile_datum_widget_class(InheritanceFullWidget)
    sibling_fn = compile_datum_widget_class(InheritanceSiblingWidget)
    override_fn = compile_datum_widget_class(InheritanceOverrideFillOnlyWidget)

    assert callable(full_fn)
    assert callable(sibling_fn)
    assert callable(override_fn)

    assert full_fn is not sibling_fn
    assert full_fn is not override_fn
    assert sibling_fn is not override_fn

    assert getattr(full_fn, "__datum_widget_class_v1__") is InheritanceFullWidget
    assert getattr(sibling_fn, "__datum_widget_class_v1__") is InheritanceSiblingWidget
    assert (
        getattr(override_fn, "__datum_widget_class_v1__")
        is InheritanceOverrideFillOnlyWidget
    )


def test_inheritance_mount_allows_existing_current_fills_through_inherited_mount():
    events, emit = _inheritance_emit_log()
    fn = compile_datum_widget_class(InheritanceFullWidget)

    result = fn(
        _inheritance_q(
            kind="mount",
            emit=emit,
            partial_fill={"first": "already-known@example.com"},
        )
    )

    assert result["status"] == "reexplode"

    state = result["state"]
    assert state["mount_handler_owner"] == "InheritanceBaseWidget._on_mount"
    assert state["mount_current_fills_seen"] == {
        "first": "already-known@example.com"
    }
    assert state["mount_chain_seen"] == "base>middle>full"

    # Mount still has no changed_fills; this is the corrected mount law.
    # The inherited mount would have asserted if changed_fills were non-empty.






# ---------------------------------------------------------------------------
# Addendum: highest UI/controller façade integration for class adapter signals
# ---------------------------------------------------------------------------
#
# These tests prove the highest interactive façade path:
#
#   dispatch_ui_action(...)
#       -> controller action packet normalization
#       -> role-bound/roleless liaison
#       -> api.step_session(fill=..., signal=...)
#       -> engine manual transition
#       -> datum lifecycle q["signal"]
#       -> compiled class adapter
#       -> @signal_catcher(...) / fallback _on_fill(...)
#
# The lower API tests above already prove direct api.step_session(...).
# This addendum proves that the public controller façade threads:
#
#   1. custom datum-targeted signals,
#   2. custom datum-targeted signals mixed with dotted user_fill,
#   3. missing-signal fallback policy,
#   4. missing-signal raise policy,
#
# into the same datum lifecycle/class-adapter path without requiring any
# adapter-specific controller, engine, or runtime branch.
#
# Important contract difference from the lower direct API path:
#
#   direct api.step_session(..., signal=...)
#       sees the caller-supplied signal info as-is;
#
#   dispatch_ui_action(..., user_signal=...)
#       normalizes/enriches datum-targeted signal.info with controller
#       provenance before the lifecycle fn receives q["signal"].
#
# The controller/facade path intentionally stamps:
#
#   {
#       "datum_id": <target datum id>,
#       "source": "controller_action",
#   }
#
# The controller provenance source is authoritative and may overwrite a
# caller-supplied info["source"]. Therefore these tests assert the enriched
# q["signal"] shape, not the raw user-supplied user_signal["info"] shape.

from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    dispatch_ui_action,
    UserAction,
)


def _expected_controller_signal_seen(
    *,
    kind: str,
    datum_id: str,
    info: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Expected signal shape seen by the class adapter through dispatch_ui_action.

    The highest controller façade does not merely pass through user_signal
    byte-for-byte. It first turns the UI action into a controller-authored
    datum signal and records provenance:

        info["datum_id"] = <target datum id>
        info["source"] = "controller_action"

    This helper intentionally mirrors that public façade contract. It also
    documents that caller-supplied info["source"] is not authoritative on this
    path and is overwritten by the controller provenance stamp.
    """
    enriched_info = dict(info or {})
    enriched_info["datum_id"] = str(datum_id)
    enriched_info["source"] = "controller_action"

    return {
        "kind": str(kind),
        "info": enriched_info,
    }


def test_highest_facade_dispatch_custom_signal_reaches_class_signal_catcher() -> None:
    """
    Proves:

        dispatch_ui_action(user_signal=refresh)
            -> controller-enriched datum signal
            -> datum lifecycle q["signal"]
            -> compiled class adapter
            -> @signal_catcher("refresh")

    No user_fill is supplied here. The re-explosion is caused only by the
    refresh signal catcher.
    """
    form_id = "adapter.highest.signal"
    step_name = "adapter.highest.signal.step"

    _register_step(
        step_name,
        _single_q_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

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

    first = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        render=False,
    )
    assert first["ui_mode"] == "FORM_FILL"
    assert first["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert "name" in str(first["ctx"]["datum_widget_decls"]["Q"])

    events: list[Dict[str, Any]] = []

    second = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_signal={
            "datum_id": "Q",
            "kind": "refresh",
            "info": {
                "reason": "highest-facade-test",
            },
        },
        render=False,
        threaded_callbacks={
            "explosion_events_callback": lambda ev: events.append(dict(ev)),
        }
    )

    assert second["ui_mode"] == "FORM_FILL"
    assert second["event_kind"] == "MANUALFILLNEEDEDSTEP"

    state_after_signal = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert state_after_signal["refresh_count"] == 1
    assert state_after_signal["refresh_signal_seen"] == _expected_controller_signal_seen(
        kind="refresh",
        datum_id="Q",
        info={
            "reason": "highest-facade-test",
        },
    )

    assert events
    assert events[-1]["kind"] == "datum_lifecycle_event_v1"
    assert events[-1]["name"] == MESSAGE_EVENT_NAME
    assert events[-1]["payload"]["message"] == {
        "level": "info",
        "text": "refreshed",
    }


def test_highest_facade_dispatch_custom_signal_with_dotted_fill_reaches_class_signal_catcher() -> None:
    """
    Proves:

        dispatch_ui_action(user_fill={"Q.name": ...}, user_signal=refresh)
            -> dotted fill is normalized into datum current_fills
            -> controller-enriched datum signal reaches q["signal"]
            -> compiled class adapter
            -> @signal_catcher("refresh")

    The signal catcher sees the fill that arrived in the same UI action, and
    the adapter records that fill as its latest adapter-authored
    pre_computed_fills snapshot.
    """
    form_id = "adapter.highest.signal_with_dotted_fill"
    step_name = "adapter.highest.signal_with_dotted_fill.step"

    _register_step(
        step_name,
        _single_q_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

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

    first = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        render=False,
    )
    assert first["ui_mode"] == "FORM_FILL"
    assert first["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert "name" in str(first["ctx"]["datum_widget_decls"]["Q"])

    second = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "Q.name": "FacadeName",
        },
        user_signal={
            "datum_id": "Q",
            "kind": "refresh",
            "info": {
                "reason": "fill-and-signal",
            },
        },
        render=False,
    )

    assert second["ui_mode"] == "FORM_FILL"
    assert second["event_kind"] == "MANUALFILLNEEDEDSTEP"

    state_after_signal = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert state_after_signal["refresh_count"] == 1
    assert state_after_signal["refresh_signal_seen"] == _expected_controller_signal_seen(
        kind="refresh",
        datum_id="Q",
        info={
            "reason": "fill-and-signal",
        },
    )
    assert state_after_signal["refresh_current_fills_seen"] == {
        "name": "FacadeName",
    }
    assert state_after_signal[ADAPTER_RESERVED_STATE_KEY][
        "last_precomputed_fills"
    ] == {
        "name": "FacadeName",
    }


def test_highest_facade_missing_signal_fallback_reaches_on_fill_with_signal_preserved() -> None:
    """
    Proves:

        dispatch_ui_action(user_fill=..., user_signal=unknown_custom_signal)
            -> controller-enriched datum signal reaches q["signal"]
            -> compiled class adapter has no matching @signal_catcher
            -> thinkwidgetTM_config fallback policy delegates to _on_fill(...)
            -> _on_fill sees the preserved signal kind and enriched info

    The caller deliberately supplies info["source"] to prove that controller
    provenance is authoritative on this path and overwrites it with
    "controller_action".
    """
    form_id = "adapter.highest.missing_signal_fallback"
    step_name = "adapter.highest.missing_signal_fallback.step"

    _register_step(
        step_name,
        _single_q_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

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

    first = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        render=False,
    )
    assert first["ui_mode"] == "FORM_FILL"
    assert first["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert "name" in str(first["ctx"]["datum_widget_decls"]["Q"])

    second = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        user_fill={
            "Q.name": "FallbackName",
        },
        user_signal={
            "datum_id": "Q",
            "kind": "unknown.but.allowed.by.fallback",
            "info": {
                "source": "highest-facade",
            },
        },
        render=False,
    )

    assert second["ui_mode"] == "FORM_FILL"
    assert second["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert "email" in str(second["ctx"]["datum_widget_decls"]["Q"])

    state_after_fallback = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert state_after_fallback["phase"] == "email"
    assert state_after_fallback["name"] == "FallbackName"
    assert state_after_fallback["last_signal_seen"] == _expected_controller_signal_seen(
        kind="unknown.but.allowed.by.fallback",
        datum_id="Q",
        info={
            "source": "highest-facade",
        },
    )


def _controller_loop_events(
    events: list[Mapping[str, Any]],
) -> list[Dict[str, Any]]:
    """
    Return only canonical controller-loop boundary events.

    Informative datum lifecycle events may legally appear between start and
    end, so tests must not assume that every event in the dispatch slice is a
    controller event.
    """
    return [
        dict(event)
        for event in events
        if event.get("name") in {
            "controller.loop.start",
            "controller.loop.end",
        }
    ]


def _event_dispatch_id(event: Mapping[str, Any]) -> str:
    """
    Read the dispatch correlation id without coupling the test to whether the
    event envelope stores it at top level or in payload.

    Delete the fallback branch later if the canonical event schema exposes only
    one location.
    """
    dispatch_id = event.get("dispatch_id")

    if dispatch_id is None:
        payload = event.get("payload")
        if isinstance(payload, Mapping):
            dispatch_id = payload.get("dispatch_id")

    assert dispatch_id is not None, event
    return str(dispatch_id)


def _event_U(event: Mapping[str, Any]) -> Any:
    """
    Controller events carry U.

    Informative datum events do not need to carry U, which is why this helper is
    used only after filtering for controller-loop boundary events.
    """
    if "U" in event:
        return event["U"]

    payload = event.get("payload")
    if isinstance(payload, Mapping) and "U" in payload:
        return payload["U"]

    raise AssertionError(f"controller event has no U: {event!r}")


def _system_error_from_dispatch_packet(
    packet: Mapping[str, Any],
) -> Mapping[str, Any]:
    """
    Extract the bounded systematic error from the highest façade result.

    The finalized controller contract is that an ordinary exception after
    controller.loop.start becomes a normal returned packet describing a
    systematic dispatch failure. It is not re-raised through
    dispatch_ui_action(...).

    Keep the accepted layouts deliberately narrow. Once the public packet
    schema is frozen to exactly one shape, collapse this helper to that shape.
    """
    direct = packet.get("system_error")
    if isinstance(direct, Mapping):
        return direct

    error = packet.get("error")
    if isinstance(error, Mapping):
        nested = error.get("system_error")
        if isinstance(nested, Mapping):
            return nested

        # Some controller packets use the error object itself as the bounded
        # systematic error record.
        if any(
            key in error
            for key in (
                "exception_type",
                "error_type",
                "type",
                "message",
            )
        ):
            return error

    result = packet.get("result")
    if isinstance(result, Mapping):
        nested = result.get("system_error")
        if isinstance(nested, Mapping):
            return nested

    raise AssertionError(
        "system-error dispatch packet did not expose a bounded system error: "
        f"{packet!r}"
    )


def _system_error_type(system_error: Mapping[str, Any]) -> str:
    """
    The controller preserves the original ordinary exception type.

    NotImplementedError is the class-adapter raise-policy failure generated for
    an unknown custom signal with no matching @signal_catcher.
    """
    for key in (
        "exception_type",
        "error_type",
        "type",
        "class_name",
    ):
        value = system_error.get(key)
        if value is not None:
            return str(value)

    raise AssertionError(
        f"bounded system error did not expose its exception type: {system_error!r}"
    )


def _system_error_message(system_error: Mapping[str, Any]) -> str:
    for key in (
        "message",
        "error_message",
        "detail",
        "reason",
    ):
        value = system_error.get(key)
        if value is not None:
            return str(value)

    raise AssertionError(
        f"bounded system error did not expose its message: {system_error!r}"
    )


# ---------------------------------------------------------------------------
# Addendum: empty premount shell law
# ---------------------------------------------------------------------------


EMPTY_PREMOUNT_WIDGET = "test.adapter.empty_premount_shell"


def _micro_without_engine_defaults_v1(micro: Mapping[str, Any]) -> Dict[str, Any]:
    """
    The engine may normalize authored micros by adding default bookkeeping fields
    such as tags=[].

    This test is about the shelling law:
        premount micros == []
        mount explosion creates the first usable micro shell

    It should not fail merely because the platform enriches a micro declaration.
    """
    m = dict(micro)
    if m.get("tags") == []:
        m.pop("tags")
    return m


def _micros_without_engine_defaults_v1(
    micros: Any,
) -> list[Dict[str, Any]]:
    assert isinstance(micros, list), micros
    return [
        _micro_without_engine_defaults_v1(m)
        for m in micros
        if isinstance(m, Mapping)
    ]


@thinkwidgetTM_config(
    EMPTY_PREMOUNT_WIDGET,
    overwrite=True,
    missing_signal_handler_outcome=MISSING_SIGNAL_FALLBACK_TO_FILL,
)
class EmptyPremountShellWidget(DatumLifecycleWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        shell = dict(fill_data["fill_shell"])

        self.mount_seen_initial_micros = list(shell.get("micros") or [])
        self.mount_changed_fills = dict(fill_data["changed_fills"])
        self.mount_current_fills = dict(fill_data["current_fills"])

        lifecycle = dict(shell.get("lifecycle") or {})
        lifecycle["widget"] = EMPTY_PREMOUNT_WIDGET

        return Reexplode(
            next_fill_shell={
                **shell,
                "title": "First shell generated by mount",
                "micros": [_text_micro("generated")],
                "lifecycle": lifecycle,
            },
            pre_computed_fills={"generated": ""},
            prefill_hints={"generated": "created-by-mount"},
        )

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.done_value = dict(fill_data["current_fills"]).get("generated")
        self.fill_seen_micros = list(dict(fill_data["fill_shell"]).get("micros") or [])
        self.fill_seen_micro_names = [
            str(m.get("name"))
            for m in self.fill_seen_micros
            if isinstance(m, Mapping)
        ]
        return True


def _empty_premount_multiframespec(
    *,
    widget_name: str,
    form_id: str,
    datum_id: str = "Q",
) -> Dict[str, Any]:
    return {
        "app_form_id": form_id,
        "datums": [
            {
                "id": datum_id,
                "title": datum_id,
                "micros": [],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": True,
                    "max_reexplosions": 10,
                    "max_messages": 8,
                    "max_proc_notes": 0,
                },
            }
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "owns": [datum_id],
                    }
                ],
            }
        ],
    }


def test_e2e_widget_does_not_need_premount_micros_mount_generates_first_shell() -> None:
    form_id = "adapter.e2e.empty_premount_shell"
    step_name = "adapter.e2e.empty_premount_shell.step"

    _register_step(
        step_name,
        _empty_premount_multiframespec(
            widget_name=EMPTY_PREMOUNT_WIDGET,
            form_id=form_id,
        ),
    )

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

    ctx = runner.step_until_stop()

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert "generated" in str(ctx["datum_widget_decls"]["Q"])

    mounted_state = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert mounted_state["mount_seen_initial_micros"] == []
    assert mounted_state["mount_changed_fills"] == {}
    assert mounted_state["mount_current_fills"] == {}

    ctx = runner.step(fill={"Q": {"generated": "filled-after-mount"}})
    assert ctx["kind"] == "ATCOMPLETION"

    final_state = _latest_lifecycle_state(api, sid, form_id, "Q")
    assert final_state["done_value"] == "filled-after-mount"
    assert final_state["fill_seen_micro_names"] == ["generated"]
    assert _micros_without_engine_defaults_v1(final_state["fill_seen_micros"]) == [
        _text_micro("generated")
    ]

    out = api.get_outputs(sid)
    assert out["form_fills"]["Q"] == {"generated": "filled-after-mount"}



# ---------------------------------------------------------------------------
# Addendum: role assignment + role mismatch modulation through highest
# controller façade for thinkwidgetTM class-adapter datums
# ---------------------------------------------------------------------------
#
# This addendum proves the intended integration law:
#
#   thinkwidgetTM / datomaton authoring layer
#       -> author datum.roles / datum.role in the multiframespec
#       -> do not call role-mismatch helpers manually
#       -> use the highest interactive controller façade with role=...
#       -> controller role-bound liaison:
#            - preflights submitted fill against role mismatch policy
#            - delegates to the roleless base session API
#            - modulates the returned ctx through
#              _obfuscate_ctx_for_specific_viewer_role(...)
#
# The class adapter remains role-agnostic. Roles are datum-shell metadata.
# The controller owns role mismatch modulation before rendering/returning ctx.
#
# Important public-ctx laws:
#
#   1. Datum role assignment is datum-level when datum.roles/datum.role exists.
#      Otherwise the owning span's roles/role is the fallback.
#
#   2. The controller modulates the ctx the engine actually returned. It does
#      not invent other authored datums merely because they match the viewer.
#
#   3. Public interactive ctx is current-frame scoped. Future frames, future
#      spans, future datum declarations, and future datum fills are not public
#      ctx.
#
#   4. Same-span mixed-role datums are different from future-frame datums:
#        - a mismatched same-span datum is redacted/removed;
#        - a matched same-span datum is preserved;
#        - this is preservation, not invention.
#
# Therefore, if the engine is stopped on a maker-only lifecycle widget and a
# reviewer views that stop:
#
#   - the maker datum is redacted/removed;
#   - the editable frontier may be empty;
#   - a future reviewer-owned datum is not invented into the current ctx;
#   - a same-span reviewer-owned datum remains visible because it was already
#     in the current public ctx.
#
# A reviewer-owned class-adapter datum is visible normally when it is the
# current live stop.


from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    dispatch_ui_action,
    UserAction,
)


def _role_modulation_session_metadata() -> Dict[str, Any]:
    return {
        "manual_io": {
            "persistence": "disabled",
            "include_forms_emitted_order_in_ctx": False,
        },
        "roles": {
            "maker": {
                "label": "Maker",
            },
            "reviewer": {
                "label": "Reviewer",
            },
        },
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                "maker": "redacted",
                "reviewer": "redacted",
            },
        },
    }


def _mixed_role_same_span_widget_multiframespec(
    *,
    widget_name: str,
    form_id: str,
) -> Dict[str, Any]:
    """
    Same-span mixed-role authored sheet.

    PROFILE is a maker-owned thinkwidgetTM lifecycle datum.
    REVIEW is a reviewer-owned ordinary datum.

    Both datums are authored into the same current span. Therefore, when a
    reviewer views the first live stop, PROFILE is redacted but REVIEW is still
    preserved in same-span current-frame vectors. That is not leakage and not
    invention: REVIEW was already in the public current ctx.
    """
    return {
        "app_form_id": form_id,
        "datums": [
            {
                "id": "PROFILE",
                "title": "Maker Profile Secret",
                "roles": ["maker"],
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": True,
                    "max_reexplosions": 20,
                    "max_messages": 8,
                    "max_proc_notes": 0,
                },
            },
            {
                "id": "REVIEW",
                "title": "Reviewer Secret Note",
                "roles": ["reviewer"],
                "micros": [_text_micro("note")],
            },
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "role": "maker",
                        "roles": ["maker"],
                        "owns": ["PROFILE", "REVIEW"],
                    }
                ],
            }
        ],
        "fills": {
            "REVIEW": {
                "note": "reviewer-only-existing-fill",
            }
        },
    }


# Backward-compatible helper name for nearby tests / future local edits.
def _mixed_role_widget_multiframespec(
    *,
    widget_name: str,
    form_id: str,
) -> Dict[str, Any]:
    return _mixed_role_same_span_widget_multiframespec(
        widget_name=widget_name,
        form_id=form_id,
    )


def _maker_current_reviewer_future_multiframespec(
    *,
    widget_name: str,
    form_id: str,
) -> Dict[str, Any]:
    """
    Two-frame authored sheet for the no-invention law.

    PROFILE is the current maker-owned lifecycle datum.
    REVIEW is a reviewer-owned future-frame datum.

    A reviewer viewing the current PROFILE stop should get PROFILE redacted and
    should not receive REVIEW in any current public ctx vector. REVIEW may be
    authored in the full program, but it is outside the returned live ctx
    frontier and outside the public current-frame projection.
    """
    return {
        "app_form_id": form_id,
        "datums": [
            {
                "id": "PROFILE",
                "title": "Maker Profile Secret",
                "roles": ["maker"],
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": True,
                    "max_reexplosions": 20,
                    "max_messages": 8,
                    "max_proc_notes": 0,
                },
            },
            {
                "id": "REVIEW",
                "title": "Reviewer Secret Note",
                "roles": ["reviewer"],
                "micros": [_text_micro("note")],
            },
        ],
        "frames": [
            {
                "id": "MAKER_FRAME",
                "spans": [
                    {
                        "id": "S_PROFILE",
                        "role": "maker",
                        "roles": ["maker"],
                        "owns": ["PROFILE"],
                    }
                ],
            },
            {
                "id": "REVIEW_FRAME",
                "spans": [
                    {
                        "id": "S_REVIEW",
                        "role": "reviewer",
                        "roles": ["reviewer"],
                        "owns": ["REVIEW"],
                    }
                ],
            },
        ],
        "fills": {
            "REVIEW": {
                "note": "reviewer-only-existing-fill",
            }
        },
    }


def _single_role_widget_multiframespec(
    *,
    widget_name: str,
    form_id: str,
    datum_id: str,
    role: str,
) -> Dict[str, Any]:
    """
    Single current-stop sheet.

    This isolates the positive visibility proof: when the current live stop is
    a reviewer-owned widget, a reviewer sees it normally through the highest
    controller façade.
    """
    return {
        "app_form_id": form_id,
        "datums": [
            {
                "id": datum_id,
                "title": f"{role.title()} Owned Widget",
                "roles": [role],
                "micros": [_text_micro("value")],
                "lifecycle": {
                    "widget": widget_name,
                    "mount_explode": True,
                    "max_reexplosions": 20,
                    "max_messages": 8,
                    "max_proc_notes": 0,
                },
            }
        ],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": "S",
                        "role": role,
                        "roles": [role],
                        "owns": [datum_id],
                    }
                ],
            }
        ],
    }


def _create_session_for_multiframespec(
    *,
    step_name: str,
    multiframespec: Mapping[str, Any],
) -> tuple[Any, str]:
    _register_step(
        step_name,
        multiframespec,
    )

    api = _api()
    st = api.create_VM_session(
        manifest=_manifest(step_name),
        initial_parameter_overrides={},
        session_metadata=_role_modulation_session_metadata(),
    )
    return api, str(st["session_id"])


def test_highest_facade_maker_role_sees_maker_widget_and_gets_reviewer_widget_redacted() -> None:
    """
    End-to-end proof for the authoring abstraction devs use:

        datum.roles = ["maker"]
        datum.roles = ["reviewer"]

    The widget author does nothing role-specific in the class adapter. The
    controller façade returns a role-modulated ctx for the maker viewer.

    In this same-span sheet, REVIEW exists in the live ctx but is reviewer-only,
    so maker receives it only as a redacted declaration/fill and never as a
    fillable datum.
    """
    form_id = "adapter.roles.e2e.maker_view"
    step_name = "adapter.roles.e2e.maker_view.step"

    _api_obj, sid = _create_session_for_multiframespec(
        step_name=step_name,
        multiframespec=_mixed_role_same_span_widget_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

    packet = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        role="maker",
        render=False,
    )

    assert packet["ui_mode"] == "FORM_FILL"
    assert packet["event_kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = packet["ctx"]
    info = ctx["role_mismatch_modulation_info"]

    assert info["role_viewing"] == "maker"
    assert info["is_mismatch"] is True
    assert info["mismatch_datum_ids"] == ["REVIEW"]

    # The maker-owned lifecycle datum remains visible and fillable.
    assert "PROFILE" in ctx["datum_widget_decls"]
    assert "PROFILE" in ctx["datum_widgets_on_this_span"]
    assert "PROFILE" in ctx["span_to_datum_widgets"]["S"]
    assert "PROFILE" in ctx["frames"][0]["field_ids"]
    assert "PROFILE" in ctx["step"]["span_owns"]

    profile_decl = ctx["datum_widget_decls"]["PROFILE"]
    assert not profile_decl.get("role_mismatch_obfuscated", False)
    assert "name" in str(profile_decl)

    # The reviewer datum is present only as redacted datum-owned data. It is not
    # fillable and is removed from ownership/navigation vectors for maker.
    assert "REVIEW" not in ctx["datum_widgets_on_this_span"]
    assert "REVIEW" not in ctx["span_to_datum_widgets"]["S"]
    assert "REVIEW" not in ctx["frames"][0]["field_ids"]
    assert "REVIEW" not in ctx["step"]["span_owns"]
    assert "REVIEW" not in ctx["step"]["span_authoritative"]

    review_decl = ctx["datum_widget_decls"]["REVIEW"]
    assert review_decl["kind"] == "role_mismatch_obfuscated_datum_v1"
    assert review_decl["role_mismatch_obfuscated"] is True
    assert review_decl["datum_args"]["viewer_role"] == "maker"
    assert review_decl["datum_args"]["required_roles"] == ["reviewer"]

    rendered = str(ctx)
    assert "Reviewer Secret Note" not in rendered
    assert "reviewer-only-existing-fill" not in rendered


def test_highest_facade_reviewer_role_gets_current_maker_widget_redacted_without_inventing_future_review_widget() -> None:
    """
    Correct no-invention proof.

    The current live stop is PROFILE, a maker-owned lifecycle widget in the
    current maker frame. REVIEW is authored in the full program, but lives in a
    future reviewer frame. A reviewer viewing the current maker stop should get
    PROFILE obfuscated/removed and should not receive REVIEW in the public ctx.

    This proves the controller modulates the ctx the engine returned. It does
    not invent a reviewer-owned datum merely because the viewer is reviewer.
    """
    form_id = "adapter.roles.e2e.reviewer_on_maker_stop"
    step_name = "adapter.roles.e2e.reviewer_on_maker_stop.step"

    _api_obj, sid = _create_session_for_multiframespec(
        step_name=step_name,
        multiframespec=_maker_current_reviewer_future_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

    packet = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        role="reviewer",
        render=False,
    )

    assert packet["ui_mode"] == "FORM_FILL"
    assert packet["event_kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = packet["ctx"]
    info = ctx["role_mismatch_modulation_info"]

    assert info["role_viewing"] == "reviewer"
    assert info["is_mismatch"] is True
    assert info["mismatch_datum_ids"] == ["PROFILE"]

    # The mismatched current lifecycle widget is removed from every fillable /
    # ownership vector in the public current-frame ctx.
    assert ctx["datum_widgets_on_this_span"] == []
    assert ctx["span_to_datum_widgets"] == {"S_PROFILE": []}
    assert ctx["frames"][0]["field_ids"] == []
    assert ctx["step"]["datum_widgets_on_this_span"] == []
    assert ctx["step"]["span_authoritative"] == []
    assert ctx["step"]["span_owns"] == []
    assert ctx["multiframespec"]["frames"][0]["spans"][0]["owns"] == []

    profile_decl = ctx["datum_widget_decls"]["PROFILE"]
    assert profile_decl["kind"] == "role_mismatch_obfuscated_datum_v1"
    assert profile_decl["role_mismatch_obfuscated"] is True
    assert profile_decl["datum_args"]["viewer_role"] == "reviewer"
    assert profile_decl["datum_args"]["required_roles"] == ["maker"]

    rendered = str(ctx)
    assert "Maker Profile Secret" not in rendered
    assert "maker-only-placeholder" not in rendered
    assert "Ada" not in rendered

    # Future reviewer material is not public ctx and is not invented into the
    # current live frontier.
    assert "REVIEW" not in ctx["datum_widgets_on_this_span"]
    assert "REVIEW" not in ctx["span_to_datum_widgets"].get("S_PROFILE", [])
    assert "REVIEW" not in str(ctx["frames"])
    assert "REVIEW" not in str(ctx["step"])
    assert "REVIEW" not in ctx["datum_widget_decls"]
    assert "REVIEW" not in ctx.get("datum_widget_fills", {})
    assert "REVIEW" not in str(ctx["multiframespec"])
    assert "Reviewer Secret Note" not in rendered
    assert "reviewer-only-existing-fill" not in rendered


def test_highest_facade_same_span_matched_reviewer_datum_is_preserved_not_invented() -> None:
    """
    Same-span mixed-role law.

    PROFILE and REVIEW are both authored into the same current span. For a
    reviewer, PROFILE is redacted, but REVIEW is allowed and therefore remains
    in current-frame ownership vectors. This is not invention: REVIEW was
    already in the current span.
    """
    form_id = "adapter.roles.e2e.same_span_reviewer_preserved"
    step_name = "adapter.roles.e2e.same_span_reviewer_preserved.step"

    _api_obj, sid = _create_session_for_multiframespec(
        step_name=step_name,
        multiframespec=_mixed_role_same_span_widget_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

    packet = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        role="reviewer",
        render=False,
    )

    assert packet["ui_mode"] == "FORM_FILL"
    assert packet["event_kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = packet["ctx"]
    info = ctx["role_mismatch_modulation_info"]

    assert info["role_viewing"] == "reviewer"
    assert info["is_mismatch"] is True
    assert info["mismatch_datum_ids"] == ["PROFILE"]

    # PROFILE is the current lifecycle stop and is mismatched, so it is no
    # longer fillable for reviewer.
    assert ctx["datum_widgets_on_this_span"] == []

    # REVIEW is not invented. It survives because it was authored into the same
    # current span and matches reviewer.
    assert ctx["span_to_datum_widgets"]["S"] == ["REVIEW"]
    assert ctx["frames"][0]["field_ids"] == ["REVIEW"]
    assert ctx["step"]["datum_widgets_on_this_span"] == []
    assert ctx["step"]["span_authoritative"] == ["REVIEW"]
    assert ctx["step"]["span_owns"] == ["REVIEW"]

    profile_decl = ctx["datum_widget_decls"]["PROFILE"]
    assert profile_decl["kind"] == "role_mismatch_obfuscated_datum_v1"
    assert profile_decl["role_mismatch_obfuscated"] is True
    assert profile_decl["datum_args"]["viewer_role"] == "reviewer"
    assert profile_decl["datum_args"]["required_roles"] == ["maker"]

    assert "REVIEW" in ctx["datum_widget_decls"]
    review_decl = ctx["datum_widget_decls"]["REVIEW"]
    assert not review_decl.get("role_mismatch_obfuscated", False)

    rendered = str(ctx)
    assert "Maker Profile Secret" not in rendered
    assert "Ada" not in rendered
    assert "Reviewer Secret Note" in rendered


def test_highest_facade_reviewer_role_sees_reviewer_owned_class_adapter_widget_when_it_is_current() -> None:
    """
    Positive reviewer visibility proof.

    When the current live stop is a reviewer-owned thinkwidgetTM lifecycle datum,
    the reviewer sees it normally through the highest role-modulated controller
    façade.
    """
    form_id = "adapter.roles.e2e.reviewer_current_widget"
    step_name = "adapter.roles.e2e.reviewer_current_widget.step"

    _api_obj, sid = _create_session_for_multiframespec(
        step_name=step_name,
        multiframespec=_single_role_widget_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
            datum_id="REVIEW_PROFILE",
            role="reviewer",
        ),
    )

    packet = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        role="reviewer",
        render=False,
    )

    assert packet["ui_mode"] == "FORM_FILL"
    assert packet["event_kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = packet["ctx"]
    info = ctx["role_mismatch_modulation_info"]

    assert info["role_viewing"] == "reviewer"
    assert info["is_mismatch"] is False
    assert info["mismatch_datum_ids"] == []

    assert "REVIEW_PROFILE" in ctx["datum_widget_decls"]
    assert "REVIEW_PROFILE" in ctx["datum_widgets_on_this_span"]
    assert "REVIEW_PROFILE" in ctx["span_to_datum_widgets"]["S"]
    assert "REVIEW_PROFILE" in ctx["frames"][0]["field_ids"]
    assert "REVIEW_PROFILE" in ctx["step"]["span_owns"]

    decl = ctx["datum_widget_decls"]["REVIEW_PROFILE"]
    assert not decl.get("role_mismatch_obfuscated", False)
    assert "name" in str(decl)


def test_highest_facade_role_mismatch_preflight_blocks_reviewer_submission_to_maker_widget() -> None:
    """
    Write-side proof.

    The controller does not merely redact on read. Before STEP, the role-bound
    liaison checks submitted fill datum ids against the same datum-role
    formalism. A reviewer cannot submit PROFILE, because PROFILE is maker-only.

    The base session API is still roleless; this guard is owned by the
    controller façade liaison.
    """
    form_id = "adapter.roles.e2e.submission_guard"
    step_name = "adapter.roles.e2e.submission_guard.step"

    _api_obj, sid = _create_session_for_multiframespec(
        step_name=step_name,
        multiframespec=_mixed_role_same_span_widget_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

    first = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        role="maker",
        render=False,
    )
    assert first["ui_mode"] == "FORM_FILL"
    assert first["event_kind"] == "MANUALFILLNEEDEDSTEP"

    with pytest.raises(PermissionError, match="PROFILE"):
        dispatch_ui_action(
            sid,
            action=UserAction.STEP,
            role="reviewer",
            user_fill={
                "PROFILE.name": "not allowed",
            },
            render=False,
        )


def test_highest_facade_allows_matching_role_submission_to_class_adapter_widget() -> None:
    """
    Positive write-side proof.

    A maker may submit the maker-owned class-adapter datum. The submitted
    dotted fill reaches the normal thinkwidgetTM lifecycle path after the
    controller's role preflight passes.
    """
    form_id = "adapter.roles.e2e.allowed_submission"
    step_name = "adapter.roles.e2e.allowed_submission.step"

    api, sid = _create_session_for_multiframespec(
        step_name=step_name,
        multiframespec=_mixed_role_same_span_widget_multiframespec(
            widget_name="test.adapter.profile",
            form_id=form_id,
        ),
    )

    first = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        role="maker",
        render=False,
    )
    assert first["ui_mode"] == "FORM_FILL"
    assert first["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert "name" in str(first["ctx"]["datum_widget_decls"]["PROFILE"])

    second = dispatch_ui_action(
        sid,
        action=UserAction.STEP,
        role="maker",
        user_fill={
            "PROFILE.name": "Ada",
        },
        render=False,
    )

    assert second["ui_mode"] == "FORM_FILL"
    assert second["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert "email" in str(second["ctx"]["datum_widget_decls"]["PROFILE"])

    state_after_name = _latest_lifecycle_state(
        api,
        sid,
        form_id,
        "PROFILE",
    )
    assert state_after_name["phase"] == "email"
    assert state_after_name["name"] == "Ada"