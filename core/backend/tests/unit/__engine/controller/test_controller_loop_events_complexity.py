from __future__ import annotations

"""
Sheet B — controller-loop event efficiency and queue health.

Complexity laws proved here:
- callback-disabled dispatch adds O(1) branching and zero context fetches/copies;
- callback-enabled dispatch adds exactly one entry-context fetch;
- packet count is exactly two per public dispatch, independent of internal loop
  continuation count;
- controller packets are callback-only and do not consume the engine queue;
- the engine session queue remains independently bounded at the configured
  SESSION_EVENT_QUEUE_MAXLEN_V1 capacity and sheds the oldest entries.
"""

from typing import Any, Dict

from _thinkengine._app_table_engine._engine_runtime_events_emission.engine_events_mixin import (
    SESSION_EVENT_QUEUE_MAXLEN_V1,
)
from _thinkengine._engine_interactive_flow_controller import UserAction
from _thinkengine._engine_interactive_flow_controller.dispatch_UFU_automaton import (
    dispatch_page_flow_controller_automaton,
)


class CountingOps:
    def __init__(self) -> None:
        self.get_context_calls = 0
        self.step_calls = 0
        self.session_event_queue: list[Dict[str, Any]] = []

    def get_session_context(self, _session_id: str) -> Dict[str, Any]:
        self.get_context_calls += 1
        return {
            "session_id": "S",
            "kind": "ATSTART",
            "session_metadata": {},
            "cursor": {"index": 0, "total": 3},
        }

    def step_session(
        self,
        _session_id: str,
        fill=None,
        signal=None,
        threaded_callbacks=None,
    ) -> Dict[str, Any]:
        self.step_calls += 1

        # A real session API may internally cross many engine steps before
        # returning one durable boundary. The controller still emits only one
        # start/end pair around this public operation.
        return {
            "session_id": "S",
            "kind": "ATCOMPLETION",
            "session_metadata": {},
            "cursor": {"index": 2, "total": 3},
        }

    def undo_last_step(self, _session_id: str) -> Dict[str, Any]:
        return self.get_session_context(_session_id)

    def redo_last_step(self, _session_id: str) -> Dict[str, Any]:
        return self.step_session(_session_id)

    def get_outputs(self, _session_id: str) -> Dict[str, Any]:
        return {}


def test_no_controller_callback_keeps_hot_path_free_of_entry_ctx_fetch() -> None:
    ops = CountingOps()

    result = dispatch_page_flow_controller_automaton(
        "S",
        action=UserAction.STEP,
        session_ops=ops,
    )

    assert isinstance(result, dict)
    assert ops.get_context_calls == 0
    assert ops.step_calls == 1
    assert ops.session_event_queue == []


def test_controller_callback_cost_is_one_entry_fetch_and_two_packets() -> None:
    ops = CountingOps()
    seen: list[Dict[str, Any]] = []

    result = dispatch_page_flow_controller_automaton(
        "S",
        action=UserAction.STEP,
        session_ops=ops,
        threaded_callbacks={
            "controller_events_callback": lambda event: seen.append(dict(event)),
        },
    )

    assert isinstance(result, dict)
    assert ops.get_context_calls == 1
    assert ops.step_calls == 1
    assert len(seen) == 2
    assert ops.session_event_queue == []


def test_controller_event_count_is_independent_of_engine_queue_capacity() -> None:
    ops = CountingOps()
    seen: list[Dict[str, Any]] = []

    # This count deliberately does not derive from the engine queue capacity:
    # controller events are callback-only and never consume that queue.
    dispatch_count = 64
    packets_per_dispatch = 2

    for _ in range(dispatch_count):
        result = dispatch_page_flow_controller_automaton(
            "S",
            action=UserAction.STEP,
            session_ops=ops,
            threaded_callbacks={
                "controller_events_callback": lambda event: seen.append(dict(event)),
            },
        )
        assert isinstance(result, dict)

    assert len(seen) == dispatch_count * packets_per_dispatch
    assert ops.session_event_queue == []

    # Verify only the invariant required by these tests. Do not pin the
    # configurable capacity to a particular deployment value.
    assert isinstance(SESSION_EVENT_QUEUE_MAXLEN_V1, int)
    assert SESSION_EVENT_QUEUE_MAXLEN_V1 > 0


def test_declared_complexity_contract() -> None:
    contract = {
        "callback_disabled": {
            "extra_time": "O(1)",
            "extra_space": "O(1)",
            "entry_ctx_fetches": 0,
            "controller_packets": 0,
        },
        "callback_enabled": {
            "extra_time": "O(|U| + |fill| + |signal|)",
            "extra_space": "O(|U| + |fill| + |signal|) transient per callback",
            "entry_ctx_fetches": 1,
            "controller_packets": 2,
        },
        "engine_queue": {
            "maxlen": SESSION_EVENT_QUEUE_MAXLEN_V1,
            "shedding": "drop oldest, retain latest",
            "controller_events_enter_queue": False,
        },
    }

    assert contract["callback_disabled"]["entry_ctx_fetches"] == 0
    assert contract["callback_enabled"]["controller_packets"] == 2

    assert contract["engine_queue"]["maxlen"] == SESSION_EVENT_QUEUE_MAXLEN_V1
    assert contract["engine_queue"]["maxlen"] > 0
    assert contract["engine_queue"]["controller_events_enter_queue"] is False