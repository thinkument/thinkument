from __future__ import annotations

"""
Controller-loop event safety E2E
================================

This sheet proves the exact in-process controller envelope law:

    controller.loop.start
        -> zero or more informative datum/external events
        -> controller.loop.end

For every dispatch whose start packet was successfully committed to the
canonical session event sink:

* every ordinary ``Exception`` raised by controller execution is converted into
  one correlated ``controller.loop.end`` with ``payload.outcome=system_error``;
* semantic validation failure remains a successful controller end whose
  ``payload.result.last_error`` is populated;
* callback exceptions are best-effort failures: they are warned about and
  cannot break canonical start/end recording;
* ``BaseException`` interruption classes are deliberately not caught;
* start/end carry complete U, action, timestamps, and the same dispatch_id;
* informative events need not carry U;
* queue delivery precedes callback delivery.

This is a safety guarantee, not crash liveness. Canonical sink failure, hard
process death, SystemExit, and KeyboardInterrupt may leave an open start.
"""

import re
from typing import Any, Dict, Mapping
from unittest.mock import patch

import pytest

from _thinkengine._engine_interactive_flow_controller import UserAction
from _thinkengine._engine_interactive_flow_controller.dispatch_UFU_automaton import (
    dispatch_page_flow_controller_automaton,
)


def _assert_timestamp(value: Any) -> None:
    assert re.match(r"^\d{4}-\d{2}-\d{2}T", str(value))


def _manual(
    *,
    marker: str,
    last_error: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "session_id": "S",
        "kind": "MANUALFILLNEEDEDSTEP",
        "session_metadata": {},
        "marker": marker,
        "cursor": {"index": 1, "total": 4},
        "current_frame_id": "frame",
        "current_span": "span",
        "datum_widgets_on_this_span": ["D"],
        "last_error": dict(last_error or {}) or None,
    }


def _complete(*, marker: str) -> Dict[str, Any]:
    return {
        "session_id": "S",
        "kind": "ATCOMPLETION",
        "session_metadata": {},
        "marker": marker,
        "cursor": {"index": 3, "total": 4},
        "current_frame_id": None,
        "current_span": None,
        "last_error": None,
    }


class FakeOps:
    def __init__(
        self,
        contexts: list[Mapping[str, Any]],
        *,
        expose_event_sink: bool = False,
    ) -> None:
        self.contexts = [dict(x) for x in contexts]
        self.index = 0
        self.get_context_calls = 0
        self.step_calls: list[Dict[str, Any]] = []
        self.undo_calls = 0
        self.redo_calls = 0
        self.session_event_queue: list[Dict[str, Any]] = []
        self.expose_event_sink = bool(expose_event_sink)

    def _current(self) -> Dict[str, Any]:
        return dict(self.contexts[min(self.index, len(self.contexts) - 1)])

    def get_session_context(self, _session_id: str) -> Dict[str, Any]:
        self.get_context_calls += 1
        return self._current()

    def step_session(
        self,
        _session_id: str,
        fill=None,
        signal=None,
        threaded_callbacks=None,
    ) -> Dict[str, Any]:
        self.step_calls.append(
            {
                "fill": fill,
                "signal": signal,
                "threaded_callbacks": threaded_callbacks,
            }
        )
        self.index = min(self.index + 1, len(self.contexts) - 1)
        return self._current()

    def undo_last_step(self, _session_id: str) -> Dict[str, Any]:
        self.undo_calls += 1
        self.index = max(0, self.index - 1)
        return self._current()

    def redo_last_step(self, _session_id: str) -> Dict[str, Any]:
        self.redo_calls += 1
        self.index = min(self.index + 1, len(self.contexts) - 1)
        return self._current()

    def get_outputs(self, _session_id: str) -> Dict[str, Any]:
        return {}

    def emit_controller_loop_event_to_session_v1(
        self,
        _session_id: str,
        event: Mapping[str, Any],
    ) -> Dict[str, Any]:
        if not self.expose_event_sink:
            raise AttributeError("queue sink disabled for this fake")
        ev = dict(event)
        self.session_event_queue.append(ev)
        return ev


class CallbackOnlyOps(FakeOps):
    emit_controller_loop_event_to_session_v1 = None


class RawEventContextOps(FakeOps):
    def __init__(self) -> None:
        super().__init__(
            [
                {
                    **_manual(marker="public-entry"),
                    "role_mismatch_modulation_info": {
                        "role_viewing": "reviewer",
                    },
                },
                {
                    **_complete(marker="public-exit"),
                    "role_mismatch_modulation_info": {
                        "role_viewing": "reviewer",
                    },
                },
            ],
            expose_event_sink=True,
        )
        self.raw_contexts = [
            _manual(marker="raw-entry"),
            _complete(marker="raw-exit"),
        ]

    def get_unmodulated_session_context_for_controller_event(
        self,
        _session_id: str,
    ) -> Dict[str, Any]:
        return dict(
            self.raw_contexts[min(self.index, len(self.raw_contexts) - 1)]
        )


class ExplodingOps(FakeOps):
    def __init__(
        self,
        *,
        action: UserAction,
        exc: BaseException,
    ) -> None:
        contexts = [_manual(marker="entry"), _manual(marker="recovery")]
        super().__init__(contexts, expose_event_sink=True)
        self.action = action
        self.exc = exc
        if action is UserAction.UNDO:
            self.index = 1

    def step_session(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise self.exc

    def undo_last_step(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise self.exc

    def redo_last_step(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise self.exc


class PreflightOrderingOps(FakeOps):
    def __init__(self) -> None:
        super().__init__(
            [_manual(marker="entry"), _complete(marker="exit")],
            expose_event_sink=True,
        )
        self.preflight_calls = 0

    def preflight_controller_dispatch_v1(
        self,
        _session_id: str,
        *,
        action: UserAction,
        submitted_fill: Mapping[str, Any],
        submitted_signal: Mapping[str, Any] | None,
    ) -> None:
        self.preflight_calls += 1
        assert action is UserAction.STEP
        assert submitted_fill == {"D": {"value": "blocked"}}
        assert submitted_signal is None
        assert self.get_context_calls == 0
        assert self.session_event_queue == []
        raise PermissionError("identity is not writable")


def _controller_events(
    events: list[Mapping[str, Any]],
) -> list[Dict[str, Any]]:
    return [
        dict(event)
        for event in events
        if event.get("kind") == "controller_loop_event_v1"
    ]


def _assert_one_closed_envelope(
    events: list[Mapping[str, Any]],
    *,
    action: UserAction,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    controller = _controller_events(events)
    assert [event["phase"] for event in controller] == ["start", "end"]

    start, end = controller
    assert start["name"] == "controller.loop.start"
    assert end["name"] == "controller.loop.end"
    assert start["dispatch_id"] == end["dispatch_id"]
    assert start["event_id"] != end["event_id"]
    assert start["action"] == end["action"] == action.name

    for event in controller:
        assert event["kind"] == "controller_loop_event_v1"
        assert event["source"] == "page_flow_controller"
        assert isinstance(event["payload"]["U"], dict)
        _assert_timestamp(event["emitted_at"])
        assert event["payload"]["timestamp"] == event["emitted_at"]

    return start, end


def test_step_emits_exact_start_and_success_end_with_U_and_U_prime() -> None:
    ops = FakeOps(
        [_manual(marker="U"), _complete(marker="U-prime")],
        expose_event_sink=True,
    )
    seen: list[Dict[str, Any]] = []

    packet = dispatch_page_flow_controller_automaton(
        "S",
        action=UserAction.STEP,
        user_fill={"D.value": "x"},
        user_signal={
            "datum_id": "D",
            "kind": "refresh_and_fill",
            "info": {"reason": "sheet-a"},
        },
        session_ops=ops,
        threaded_callbacks={
            "controller_events_callback": lambda event: seen.append(dict(event)),
        },
    )

    assert packet["system_error"] is None
    start, end = _assert_one_closed_envelope(seen, action=UserAction.STEP)

    assert start["payload"]["U"]["marker"] == "U"
    assert end["payload"]["U"]["marker"] == "U-prime"
    assert start["payload"]["fill"] == {"D": {"value": "x"}}
    assert end["payload"]["fill"] == {"D": {"value": "x"}}
    assert start["payload"]["signal"] == {
        "datum_id": "D",
        "kind": "refresh_and_fill",
        "info": {"reason": "sheet-a"},
    }
    assert end["payload"]["outcome"] == "success"
    assert end["payload"]["result"] == {
        "event_kind": "ATCOMPLETION",
        "ui_mode": "RUN_COMPLETED_SUMMARY",
        "finished": True,
        "last_error": None,
    }

    # Canonical queue first, callback second, same immutable event identities.
    assert [event["event_id"] for event in ops.session_event_queue] == [
        event["event_id"] for event in seen
    ]


def test_semantic_rejection_is_success_end_not_system_error() -> None:
    semantic_U = _manual(
        marker="semantic-error",
        last_error={"D": "value is required"},
    )
    ops = FakeOps(
        [_manual(marker="entry"), semantic_U],
        expose_event_sink=True,
    )

    packet = dispatch_page_flow_controller_automaton(
        "S",
        action=UserAction.STEP,
        user_fill={"D": {"value": ""}},
        session_ops=ops,
    )

    assert packet["system_error"] is None
    assert packet["last_error"] == {"D": "value is required"}

    _start, end = _assert_one_closed_envelope(
        ops.session_event_queue,
        action=UserAction.STEP,
    )
    assert end["payload"]["outcome"] == "success"
    assert end["payload"]["result"]["last_error"] == {
        "D": "value is required",
    }
    assert "system_error" not in end["payload"]


@pytest.mark.parametrize(
    "action",
    [UserAction.STEP, UserAction.UNDO, UserAction.REDO],
)
def test_every_public_action_gets_one_correlated_success_envelope(
    action: UserAction,
) -> None:
    if action is UserAction.UNDO:
        ops = FakeOps(
            [_manual(marker="after"), _complete(marker="before")],
            expose_event_sink=True,
        )
        ops.index = 1
    else:
        ops = FakeOps(
            [_manual(marker="before"), _complete(marker="after")],
            expose_event_sink=True,
        )

    packet = dispatch_page_flow_controller_automaton(
        "S",
        action=action,
        session_ops=ops,
    )

    assert packet["system_error"] is None
    _assert_one_closed_envelope(ops.session_event_queue, action=action)


@pytest.mark.parametrize(
    "action",
    [UserAction.STEP, UserAction.UNDO, UserAction.REDO],
)
def test_ordinary_operation_exception_is_caught_and_closes_system_error_envelope(
    action: UserAction,
) -> None:
    ops = ExplodingOps(
        action=action,
        exc=RuntimeError(f"{action.name.lower()} exploded"),
    )

    packet = dispatch_page_flow_controller_automaton(
        "S",
        action=action,
        session_ops=ops,
    )

    assert packet["event_kind"] == (
        "SYSTEM_ERRORED_WHEN_PROCESSING_ACTION_DISPATCH"
    )
    assert packet["finished"] is False
    assert packet["last_error"] is None
    assert packet["system_error"] == {
        "kind": "controller_dispatch_system_error_v1",
        "exception_type": "RuntimeError",
        "message": f"{action.name.lower()} exploded",
    }

    start, end = _assert_one_closed_envelope(
        ops.session_event_queue,
        action=action,
    )
    assert end["dispatch_id"] == start["dispatch_id"]
    assert end["payload"]["outcome"] == "system_error"
    assert end["payload"]["system_error"] == packet["system_error"]


@pytest.mark.parametrize(
    ("action", "exc"),
    [
        (UserAction.STEP, ValueError("step value failure")),
        (UserAction.UNDO, LookupError("undo lookup failure")),
        (UserAction.REDO, OSError("redo io failure")),
    ],
)
def test_system_error_preserves_original_exception_type(
    action: UserAction,
    exc: Exception,
) -> None:
    ops = ExplodingOps(action=action, exc=exc)

    packet = dispatch_page_flow_controller_automaton(
        "S",
        action=action,
        session_ops=ops,
    )

    assert packet["system_error"] == {
        "kind": "controller_dispatch_system_error_v1",
        "exception_type": type(exc).__name__,
        "message": str(exc),
    }
    _start, end = _assert_one_closed_envelope(
        ops.session_event_queue,
        action=action,
    )
    assert end["payload"]["system_error"] == packet["system_error"]


def test_routing_exception_after_start_is_caught_and_closes_system_error_envelope() -> None:
    ops = FakeOps(
        [_manual(marker="entry"), _complete(marker="after-step")],
        expose_event_sink=True,
    )

    with patch(
        "_thinkengine._engine_interactive_flow_controller."
        "dispatch_UFU_automaton.get_routing_map",
        side_effect=RuntimeError("routing table failed"),
    ):
        packet = dispatch_page_flow_controller_automaton(
            "S",
            action=UserAction.STEP,
            session_ops=ops,
        )

    assert packet["system_error"]["message"] == "routing table failed"
    _start, end = _assert_one_closed_envelope(
        ops.session_event_queue,
        action=UserAction.STEP,
    )
    assert end["payload"]["outcome"] == "system_error"


def test_unknown_context_kind_after_start_is_caught_and_closed() -> None:
    bad = _manual(marker="bad-kind")
    bad["kind"] = "UNKNOWN_RUNTIME_KIND"
    ops = FakeOps(
        [_manual(marker="entry"), bad],
        expose_event_sink=True,
    )

    packet = dispatch_page_flow_controller_automaton(
        "S",
        action=UserAction.STEP,
        session_ops=ops,
    )

    assert packet["system_error"]["exception_type"] == "RuntimeError"
    assert "Unknown event kind" in packet["system_error"]["message"]
    _start, end = _assert_one_closed_envelope(
        ops.session_event_queue,
        action=UserAction.STEP,
    )
    assert end["payload"]["outcome"] == "system_error"


def test_callback_exception_is_warned_and_cannot_break_canonical_envelope() -> None:
    ops = FakeOps(
        [_manual(marker="U"), _complete(marker="U-prime")],
        expose_event_sink=True,
    )

    def explode(_event: Mapping[str, Any]) -> None:
        raise RuntimeError("downstream unavailable")

    with pytest.warns(
        RuntimeWarning,
        match="controller event callback raised and was isolated",
    ):
        packet = dispatch_page_flow_controller_automaton(
            "S",
            action=UserAction.STEP,
            session_ops=ops,
            threaded_callbacks={"controller_events_callback": explode},
        )

    assert packet["system_error"] is None
    _assert_one_closed_envelope(
        ops.session_event_queue,
        action=UserAction.STEP,
    )


def test_callback_only_liaison_still_receives_start_and_end() -> None:
    ops = CallbackOnlyOps(
        [_manual(marker="U"), _complete(marker="U-prime")]
    )
    seen: list[Dict[str, Any]] = []

    packet = dispatch_page_flow_controller_automaton(
        "S",
        action=UserAction.STEP,
        session_ops=ops,
        threaded_callbacks={
            "controller_events_callback": lambda event: seen.append(dict(event)),
        },
    )

    assert packet["system_error"] is None
    _assert_one_closed_envelope(seen, action=UserAction.STEP)
    assert ops.session_event_queue == []


def test_controller_event_sink_alone_enables_canonical_recording() -> None:
    ops = FakeOps(
        [_manual(marker="U"), _complete(marker="U-prime")],
        expose_event_sink=True,
    )

    packet = dispatch_page_flow_controller_automaton(
        "S",
        action=UserAction.STEP,
        session_ops=ops,
        threaded_callbacks=None,
    )

    assert packet["system_error"] is None
    _assert_one_closed_envelope(
        ops.session_event_queue,
        action=UserAction.STEP,
    )


def test_controller_events_use_unmodulated_context_getter_when_available() -> None:
    ops = RawEventContextOps()

    packet = dispatch_page_flow_controller_automaton(
        "S",
        action=UserAction.STEP,
        session_ops=ops,
    )

    assert packet["ctx"]["marker"] == "public-exit"
    assert packet["ctx"]["role_mismatch_modulation_info"]["role_viewing"] == (
        "reviewer"
    )

    start, end = _assert_one_closed_envelope(
        ops.session_event_queue,
        action=UserAction.STEP,
    )
    assert start["payload"]["U"]["marker"] == "raw-entry"
    assert end["payload"]["U"]["marker"] == "raw-exit"
    assert "role_mismatch_modulation_info" not in start["payload"]["U"]
    assert "role_mismatch_modulation_info" not in end["payload"]["U"]


def test_non_step_fill_and_signal_are_ignored_in_both_boundary_events() -> None:
    ops = FakeOps(
        [_manual(marker="after"), _complete(marker="before")],
        expose_event_sink=True,
    )
    ops.index = 1

    with pytest.warns(UserWarning):
        packet = dispatch_page_flow_controller_automaton(
            "S",
            action=UserAction.UNDO,
            user_fill={"D": {"value": "ignored"}},
            user_signal={
                "datum_id": "D",
                "kind": "ignored",
                "info": {},
            },
            session_ops=ops,
        )

    assert packet["system_error"] is None
    start, end = _assert_one_closed_envelope(
        ops.session_event_queue,
        action=UserAction.UNDO,
    )
    assert start["payload"]["fill"] == {}
    assert end["payload"]["fill"] == {}
    assert start["payload"]["signal"] is None
    assert end["payload"]["signal"] is None


@pytest.mark.parametrize("exc", [KeyboardInterrupt(), SystemExit(7)])
def test_baseexception_interruptions_are_not_converted_to_system_error_end(
    exc: BaseException,
) -> None:
    ops = ExplodingOps(action=UserAction.STEP, exc=exc)

    with pytest.raises(type(exc)):
        dispatch_page_flow_controller_automaton(
            "S",
            action=UserAction.STEP,
            session_ops=ops,
        )

    # The open start is the precise allowed interruption shape.
    assert [event["phase"] for event in ops.session_event_queue] == ["start"]


def test_preflight_failure_occurs_before_start_and_emits_no_events() -> None:
    ops = PreflightOrderingOps()

    with pytest.raises(PermissionError, match="identity"):
        dispatch_page_flow_controller_automaton(
            "S",
            action=UserAction.STEP,
            user_fill={"D": {"value": "blocked"}},
            session_ops=ops,
        )

    assert ops.preflight_calls == 1
    assert ops.get_context_calls == 0
    assert ops.step_calls == []
    assert ops.session_event_queue == []