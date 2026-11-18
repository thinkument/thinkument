# tests/test_session_events_v1.py

from __future__ import annotations

"""
Session events v1
=================

These tests prove the live event model top-down without a payload-template
layer.

Core law
--------
Session events are general packets emitted onto one session. They can come
from:

- a datum lifecycle widget during fill/mount/reexplode work;
- returned widget event declarations;
- an external caller such as a webhook/frontend/server integration.

Delivery has two distinct surfaces:

1. A process-local callback receives the builder packet synchronously.
2. The session-owned bounded canonical queue retains a copied packet.

The retained queue copy:

- receives a positive monotonic ``event_seq``;
- is serialized with the engine snapshot;
- survives snapshot import and cold reload;
- remains isolated per session;
- is consumed explicitly through ``drain_session_events(...)``.

Events remain excluded from ordinary engine state, output values, lifecycle
memory, runtime indexes, and ordinary context payloads. Callback functions and
other live process-local receiver machinery remain transient.
"""

import copy
import re
from typing import Any, Dict, Mapping

import pytest

from __exceptions.engine import (
    DatumLifecycleContractError,
    FatalEngineError,
)

from __datomatonTM import (
    explode_datum_widget,
)

from _thinkengine._app_table_engine._engine_runtime_events_emission.engine_events_mixin import (
    set_session_event_callback,
)

from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    apply_q_reexplode_batch_v1,
)

from __datomatonTM import (
    Q_STATUS_DONE,
    Q_STATUS_REEXPLODE,
    register_datum_widget_v1,
)
from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
    hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory,
)

from _thinkengine.runme.runme_interactive_raw import (
    AppTableSessionAPI,
)

from _thinkengine._app_table_engine._engine_runtime_events_emission.engine_events_mixin import (
    SESSION_EVENT_QUEUE_MAXLEN_V1,
)


def _base_datum(
    *,
    widget: str,
    max_reexplosions: int = 2,
) -> Dict[str, Any]:
    return {
        "id": "D1",
        "micros": [
            {
                "name": "value",
                "type": "text",
                "required": True,
            }
        ],
        "lifecycle": {
            "widget": widget,
            "max_reexplosions": max_reexplosions,
            "max_messages": 8,
            "max_proc_notes": 8,
        },
    }


def _assert_session_event_packet(
    event: Mapping[str, Any],
    *,
    source: str,
    name: str,
    signal_kind: str,
    form_id: str = "F1",
    frame_id: str = "FR1",
    span_id: str = "S1",
    datum_id: str = "D1",
) -> None:
    assert event["kind"] == "datum_lifecycle_event_v1"
    assert isinstance(event["event_id"], str)
    assert event["event_id"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}T", str(event["emitted_at"]))

    assert event["source"] == source
    assert event["name"] == name
    assert event["signal_kind"] == signal_kind

    assert event["form_id"] == form_id
    assert event["frame_id"] == frame_id
    assert event["span_id"] == span_id
    assert event["datum_id"] == datum_id

    # Packet must remain JSON-compatible.
    import json

    json.dumps(event, sort_keys=True)


def _assert_queued_session_event_packet(
    event: Mapping[str, Any],
    *,
    source: str,
    name: str,
    signal_kind: str,
    form_id: str = "F1",
    frame_id: str = "FR1",
    span_id: str = "S1",
    datum_id: str = "D1",
) -> None:
    _assert_session_event_packet(
        event,
        source=source,
        name=name,
        signal_kind=signal_kind,
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        datum_id=datum_id,
    )

    event_seq = event.get("event_seq")
    assert (
        isinstance(event_seq, int)
        and not isinstance(event_seq, bool)
        and event_seq >= 1
    )


@pytest.fixture(autouse=True)
def _clean_session_event_callback():
    set_session_event_callback(None)
    yield
    set_session_event_callback(None)


def test_widget_inline_emit_delivers_to_session_sink_then_global_callback():
    sink_events: list[Dict[str, Any]] = []
    callback_events: list[Dict[str, Any]] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        ev = q["emit"](
            {
                "progress": 0.25,
                "label": "started",
            },
            name="widget.progress",
        )

        assert ev["source"] == "datum_widget"
        assert ev["payload"] == {
            "progress": 0.25,
            "label": "started",
        }

        return {
            "status": Q_STATUS_DONE,
            "state": {
                "seen_emit": True,
            },
            "message": {
                "level": "success",
                "text": "ok",
            },
        }

    register_datum_widget_v1(
        "tests.session_events.inline_emit",
        widget,
        overwrite=True,
    )
    set_session_event_callback(
        lambda ev: callback_events.append(dict(ev))
    )

    ev = explode_datum_widget(
        state={},
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        datum_id="D1",
        datum=_base_datum(widget="tests.session_events.inline_emit"),
        raw_fill={"value": "x"},
        partial_fill={"value": "x"},
        prefill=None,
        structurally_satisfied=True,
        event_sink=lambda event: sink_events.append(dict(event)),
    )

    assert ev.status == Q_STATUS_DONE
    assert len(ev.emitted_events) == 1
    assert len(sink_events) == 1
    assert len(callback_events) == 1

    delivered = sink_events[0]
    _assert_session_event_packet(
        delivered,
        source="datum_widget",
        name="widget.progress",
        signal_kind="fill",
    )
    assert delivered["payload"] == {
        "progress": 0.25,
        "label": "started",
    }

    assert callback_events[0]["event_id"] == delivered["event_id"]


def test_widget_inline_emit_accepts_general_dead_json_payload_shapes():
    sink_events: list[Dict[str, Any]] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"](
            {
                "free": {
                    "shape": [1, 2, 3],
                    "nested": {
                        "ok": True,
                        "value": None,
                    },
                }
            },
            name="free.shape",
        )
        return {
            "status": Q_STATUS_DONE,
            "state": {},
        }

    register_datum_widget_v1(
        "tests.session_events.free_shape",
        widget,
        overwrite=True,
    )

    ev = explode_datum_widget(
        state={},
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        datum_id="D1",
        datum=_base_datum(widget="tests.session_events.free_shape"),
        raw_fill={"value": "x"},
        partial_fill={"value": "x"},
        prefill=None,
        structurally_satisfied=True,
        event_sink=lambda event: sink_events.append(dict(event)),
    )

    assert ev.status == Q_STATUS_DONE
    assert len(sink_events) == 1

    _assert_session_event_packet(
        sink_events[0],
        source="datum_widget",
        name="free.shape",
        signal_kind="fill",
    )
    assert sink_events[0]["payload"] == {
        "free": {
            "shape": [1, 2, 3],
            "nested": {
                "ok": True,
                "value": None,
            },
        }
    }


def test_scalar_and_list_payloads_normalize_to_value_key():
    sink_events: list[Dict[str, Any]] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]("scalar-payload", name="event.scalar")
        q["emit"](["a", "b"], name="event.list")
        return {
            "status": Q_STATUS_DONE,
            "state": {},
        }

    register_datum_widget_v1(
        "tests.session_events.payload_normalization",
        widget,
        overwrite=True,
    )

    ev = explode_datum_widget(
        state={},
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        datum_id="D1",
        datum=_base_datum(
            widget="tests.session_events.payload_normalization"
        ),
        raw_fill={"value": "x"},
        partial_fill={"value": "x"},
        prefill=None,
        structurally_satisfied=True,
        event_sink=lambda event: sink_events.append(dict(event)),
    )

    assert ev.status == Q_STATUS_DONE
    assert [e["name"] for e in sink_events] == [
        "event.scalar",
        "event.list",
    ]
    assert sink_events[0]["payload"] == {"value": "scalar-payload"}
    assert sink_events[1]["payload"] == {"value": ["a", "b"]}


def test_non_json_event_payload_fails_before_delivery():
    sink_events: list[Dict[str, Any]] = []
    callback_events: list[Dict[str, Any]] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"](
            {"bad": object()},
            name="event.bad.payload",
        )
        return {"status": Q_STATUS_DONE}

    register_datum_widget_v1(
        "tests.session_events.bad_payload",
        widget,
        overwrite=True,
    )
    set_session_event_callback(
        lambda ev: callback_events.append(dict(ev))
    )

    with pytest.raises(DatumLifecycleContractError):
        explode_datum_widget(
            state={},
            form_id="F1",
            frame_id="FR1",
            span_id="S1",
            datum_id="D1",
            datum=_base_datum(widget="tests.session_events.bad_payload"),
            raw_fill={"value": "x"},
            partial_fill={"value": "x"},
            prefill=None,
            structurally_satisfied=True,
            event_sink=lambda event: sink_events.append(dict(event)),
        )

    assert sink_events == []
    assert callback_events == []


def test_widget_returned_events_are_delivered_after_inline_events_fifo():
    sink_events: list[Dict[str, Any]] = []
    callback_names: list[str] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"](
            {"n": 1},
            name="inline.one",
        )
        return {
            "status": Q_STATUS_DONE,
            "state": {},
            "events": [
                {
                    "name": "returned.two",
                    "payload": {
                        "n": 2,
                    },
                },
                {
                    "name": "returned.scalar",
                    "payload": 3,
                },
            ],
        }

    register_datum_widget_v1(
        "tests.session_events.returned_events",
        widget,
        overwrite=True,
    )
    set_session_event_callback(
        lambda ev: callback_names.append(str(ev["name"]))
    )

    ev = explode_datum_widget(
        state={},
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        datum_id="D1",
        datum=_base_datum(widget="tests.session_events.returned_events"),
        raw_fill={"value": "x"},
        partial_fill={"value": "x"},
        prefill=None,
        structurally_satisfied=True,
        event_sink=lambda event: sink_events.append(dict(event)),
    )

    assert ev.status == Q_STATUS_DONE

    assert [e["name"] for e in sink_events] == [
        "inline.one",
        "returned.two",
        "returned.scalar",
    ]
    assert callback_names == [
        "inline.one",
        "returned.two",
        "returned.scalar",
    ]

    _assert_session_event_packet(
        sink_events[0],
        source="datum_widget",
        name="inline.one",
        signal_kind="fill",
    )
    _assert_session_event_packet(
        sink_events[1],
        source="datum_widget_result",
        name="returned.two",
        signal_kind="fill",
    )
    _assert_session_event_packet(
        sink_events[2],
        source="datum_widget_result",
        name="returned.scalar",
        signal_kind="fill",
    )

    assert sink_events[1]["payload"] == {"n": 2}
    assert sink_events[2]["payload"] == {"value": 3}


def test_bad_returned_event_entry_fails_before_that_entry_delivery():
    sink_events: list[Dict[str, Any]] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]({"ok": True}, name="inline.before.bad")
        return {
            "status": Q_STATUS_DONE,
            "state": {},
            "events": [
                "not-a-mapping",
            ],
        }

    register_datum_widget_v1(
        "tests.session_events.bad_returned_event",
        widget,
        overwrite=True,
    )

    with pytest.raises(DatumLifecycleContractError, match="events entries"):
        explode_datum_widget(
            state={},
            form_id="F1",
            frame_id="FR1",
            span_id="S1",
            datum_id="D1",
            datum=_base_datum(
                widget="tests.session_events.bad_returned_event"
            ),
            raw_fill={"value": "x"},
            partial_fill={"value": "x"},
            prefill=None,
            structurally_satisfied=True,
            event_sink=lambda event: sink_events.append(dict(event)),
        )

    # Inline events are live side effects; the malformed returned event blocks
    # only its own delivery.
    assert [e["name"] for e in sink_events] == ["inline.before.bad"]


def test_callback_exception_is_visible_after_session_sink_delivery():
    sink_events: list[Dict[str, Any]] = []

    def callback(_ev: Mapping[str, Any]) -> None:
        raise RuntimeError("callback exploded")

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"](
            {"ok": True},
            name="callback.raises",
        )
        return {
            "status": Q_STATUS_DONE,
            "state": {},
        }

    register_datum_widget_v1(
        "tests.session_events.callback_raises",
        widget,
        overwrite=True,
    )
    set_session_event_callback(callback)

    with pytest.raises(RuntimeError, match="callback exploded"):
        explode_datum_widget(
            state={},
            form_id="F1",
            frame_id="FR1",
            span_id="S1",
            datum_id="D1",
            datum=_base_datum(
                widget="tests.session_events.callback_raises"
            ),
            raw_fill={"value": "x"},
            partial_fill={"value": "x"},
            prefill=None,
            structurally_satisfied=True,
            event_sink=lambda event: sink_events.append(dict(event)),
        )

    assert len(sink_events) == 1
    assert sink_events[0]["name"] == "callback.raises"


def test_q_input_exposes_prior_state_messages_and_proc_notes_on_next_eval():
    seen_inputs: list[Dict[str, Any]] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        seen_inputs.append(
            {
                "state": copy.deepcopy(q.get("state")),
                "messages": copy.deepcopy(q.get("messages")),
                "proc_notes": copy.deepcopy(q.get("proc_notes")),
                "reexplode_count": q.get("reexplode_count"),
            }
        )

        if int(q.get("reexplode_count") or 0) == 0:
            return {
                "status": Q_STATUS_REEXPLODE,
                "datum": _base_datum(
                    widget="tests.session_events.state_messages_proc_notes",
                    max_reexplosions=2,
                ),
                "state": {"phase": "after_first"},
                "message": {"level": "info", "text": "first"},
                "proc_notes": {"why": "first reexplode"},
                "fill": q.get("partial_fill"),
            }

        return {
            "status": Q_STATUS_DONE,
            "state": {"phase": "done"},
            "message": {"level": "success", "text": "done"},
        }

    register_datum_widget_v1(
        "tests.session_events.state_messages_proc_notes",
        widget,
        overwrite=True,
    )

    state: Dict[str, Any] = {}
    datum = _base_datum(
        widget="tests.session_events.state_messages_proc_notes",
        max_reexplosions=2,
    )

    first = explode_datum_widget(
        state=state,
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        datum_id="D1",
        datum=datum,
        raw_fill={"value": "x"},
        partial_fill={"value": "x"},
        prefill=None,
        structurally_satisfied=True,
    )

    assert first.status == Q_STATUS_REEXPLODE

    apply_q_reexplode_batch_v1(
        state=state,
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        evaluations=[first],
        working_fills={"D1": {"value": "x"}},
    )

    effective = hydrate_multiframespec_static_shell_w_its_latest_fills_from_memory(
        multiframespec={"datums": [datum]},
        state=state,
        form_id="F1",
    )
    next_datum = dict(effective["datums"][0])

    second = explode_datum_widget(
        state=state,
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        datum_id="D1",
        datum=next_datum,
        raw_fill={"value": "x"},
        partial_fill={"value": "x"},
        prefill=None,
        structurally_satisfied=True,
    )

    assert second.status == Q_STATUS_DONE

    assert seen_inputs[0]["state"] == {}
    assert seen_inputs[0]["messages"] == []
    assert seen_inputs[0]["proc_notes"] == []
    assert seen_inputs[0]["reexplode_count"] == 0

    assert seen_inputs[1]["state"] == {"phase": "after_first"}
    assert seen_inputs[1]["messages"] == [
        {"level": "info", "text": "first"}
    ]
    assert seen_inputs[1]["proc_notes"] == [
        {"why": "first reexplode"}
    ]
    assert seen_inputs[1]["reexplode_count"] == 1


def test_external_session_event_can_be_emitted_like_a_webhook_and_drained():
    callback_events: list[Dict[str, Any]] = []
    set_session_event_callback(
        lambda ev: callback_events.append(dict(ev))
    )

    api = AppTableSessionAPI(enable_persistence=False)

    created = api.create_VM_session(
        manifest=[],
        initial_parameter_overrides={},
        session_metadata={},
    )
    session_id = created["session_id"]

    ev = api.emit_session_event(
        session_id,
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        datum_id="D1",
        name="webhook.payment.succeeded",
        payload={
            "provider": "stripe",
            "amount": 2500,
            "currency": "usd",
        },
    )

    _assert_session_event_packet(
        ev,
        source="external",
        name="webhook.payment.succeeded",
        signal_kind="external",
    )
    assert ev["payload"] == {
        "provider": "stripe",
        "amount": 2500,
        "currency": "usd",
    }

    assert len(callback_events) == 1
    assert callback_events[0]["event_id"] == ev["event_id"]

    drained = api.drain_session_events(session_id)
    assert len(drained) == 1
    assert drained[0]["event_id"] == ev["event_id"]

    assert api.drain_session_events(session_id) == []


def test_external_session_event_rejects_non_json_payload_without_queueing():
    api = AppTableSessionAPI(enable_persistence=False)
    created = api.create_VM_session(
        manifest=[],
        initial_parameter_overrides={},
        session_metadata={},
    )
    session_id = created["session_id"]

    with pytest.raises(DatumLifecycleContractError):
        api.emit_session_event(
            session_id,
            form_id="F1",
            frame_id="FR1",
            span_id="S1",
            datum_id="D1",
            name="webhook.bad.payload",
            payload={
                "bad": object(),
            },
        )

    assert api.drain_session_events(session_id) == []


def test_external_session_event_requires_explicit_location_when_not_on_manual_step():
    api = AppTableSessionAPI(enable_persistence=False)
    created = api.create_VM_session(
        manifest=[],
        initial_parameter_overrides={},
        session_metadata={},
    )
    session_id = created["session_id"]

    with pytest.raises(ValueError, match="form_id/frame_id/span_id"):
        api.emit_session_event(
            session_id,
            datum_id="D1",
            name="external.no.location",
            payload={},
        )

    assert api.drain_session_events(session_id) == []


def test_events_are_persisted_only_in_the_bounded_snapshot_queue_not_outputs():
    api = AppTableSessionAPI(enable_persistence=False)
    created = api.create_VM_session(
        manifest=[],
        initial_parameter_overrides={},
        session_metadata={},
    )
    session_id = created["session_id"]

    emitted = api.emit_session_event(
        session_id,
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        datum_id="D1",
        name="external.progress",
        payload={"progress": 1},
    )

    # The builder/callback-facing packet is not required to carry the
    # queue-owned cursor field.
    assert emitted["name"] == "external.progress"
    assert "event_seq" not in emitted

    eng = api._get(session_id)
    state_text = repr(eng.state)
    outputs_text = repr(api.get_outputs(session_id))
    snapshot = api.export_session_snapshot(session_id)
    snapshot_text = repr(snapshot)

    # Events remain absent from domain state and ordinary outputs.
    assert "datum_lifecycle_event_v1" not in state_text
    assert "external.progress" not in state_text
    assert "datum_lifecycle_event_v1" not in outputs_text
    assert "external.progress" not in outputs_text

    # The bounded canonical queue is now intentionally snapshot-durable.
    assert "datum_lifecycle_event_v1" in snapshot_text
    assert "external.progress" in snapshot_text
    assert "session_events_v1" in snapshot
    assert "next_session_event_seq_v1" in snapshot

    retained = snapshot["session_events_v1"]
    assert len(retained) == 1

    queued = retained[0]
    _assert_queued_session_event_packet(
        queued,
        source="external",
        name="external.progress",
        signal_kind="external",
    )
    assert queued["event_id"] == emitted["event_id"]
    assert queued["payload"] == {"progress": 1}
    assert snapshot["next_session_event_seq_v1"] == queued["event_seq"] + 1

    drained = api.drain_session_events(session_id)
    assert len(drained) == 1
    assert drained[0] == queued
    assert api.drain_session_events(session_id) == []


def test_snapshot_import_restores_undrained_session_events_and_sequence():
    api = AppTableSessionAPI(enable_persistence=False)
    created = api.create_VM_session(
        manifest=[],
        initial_parameter_overrides={},
        session_metadata={},
    )
    session_id = created["session_id"]

    first = api.emit_session_event(
        session_id,
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        datum_id="D1",
        name="external.before.snapshot",
        payload={"n": 1},
    )

    eng_before = api._get(session_id)
    assert len(eng_before._session_events_v1) == 1

    queued_before = dict(eng_before._session_events_v1[0])
    assert queued_before["event_id"] == first["event_id"]
    assert queued_before["event_seq"] == 1

    snapshot = api.export_session_snapshot(session_id)

    # Mutate the current in-memory queue after export so the import proves
    # restoration from the snapshot rather than continued object identity.
    assert len(api.drain_session_events(session_id)) == 1
    assert api.drain_session_events(session_id) == []

    api.import_session_snapshot(
        session_id,
        snapshot=snapshot,
    )

    eng_after = api._get(session_id)
    assert len(eng_after._session_events_v1) == 1

    restored = api.drain_session_events(session_id)
    assert restored == [queued_before]
    assert api.drain_session_events(session_id) == []

    # Sequence continuity is also snapshot state. A newly queued event must not
    # reuse the restored packet's cursor.
    second = api.emit_session_event(
        session_id,
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        datum_id="D1",
        name="external.after.snapshot",
        payload={"n": 2},
    )
    assert "event_seq" not in second

    queued_after = api.drain_session_events(session_id)
    assert len(queued_after) == 1
    assert queued_after[0]["event_id"] == second["event_id"]
    assert queued_after[0]["event_seq"] == queued_before["event_seq"] + 1


def test_session_event_queues_are_isolated_per_session():
    api = AppTableSessionAPI(enable_persistence=False)

    sid1 = api.create_VM_session(
        manifest=[],
        initial_parameter_overrides={},
        session_metadata={},
    )["session_id"]
    sid2 = api.create_VM_session(
        manifest=[],
        initial_parameter_overrides={},
        session_metadata={},
    )["session_id"]

    ev1 = api.emit_session_event(
        sid1,
        form_id="F1",
        frame_id="FR1",
        span_id="S1",
        datum_id="D1",
        name="session.one",
        payload={"session": 1},
    )
    ev2 = api.emit_session_event(
        sid2,
        form_id="F2",
        frame_id="FR2",
        span_id="S2",
        datum_id="D2",
        name="session.two",
        payload={"session": 2},
    )

    drained1 = api.drain_session_events(sid1)
    drained2 = api.drain_session_events(sid2)

    assert [e["event_id"] for e in drained1] == [ev1["event_id"]]
    assert [e["event_id"] for e in drained2] == [ev2["event_id"]]

    assert drained1[0]["payload"] == {"session": 1}
    assert drained2[0]["payload"] == {"session": 2}

    assert api.drain_session_events(sid1) == []
    assert api.drain_session_events(sid2) == []


def test_event_queue_is_bounded_to_latest_SESSION_EVENT_QUEUE_MAXLEN_V1_qty_of_events():
    api = AppTableSessionAPI(enable_persistence=False)
    session_id = api.create_VM_session(
        manifest=[],
        initial_parameter_overrides={},
        session_metadata={},
    )["session_id"]

    delt = 6
    total = SESSION_EVENT_QUEUE_MAXLEN_V1 + delt

    for i in range(total):
        api.emit_session_event(
            session_id,
            form_id="F1",
            frame_id="FR1",
            span_id="S1",
            datum_id="D1",
            name=f"external.{i}",
            payload={"i": i},
        )

    drained = api.drain_session_events(session_id)

    assert len(drained) == SESSION_EVENT_QUEUE_MAXLEN_V1
    assert drained[0]["payload"] == {"i": delt}
    assert drained[-1]["payload"] == {"i": total - 1}

    # Queue truncation does not renumber retained packets.
    assert drained[0]["event_seq"] == delt + 1
    assert drained[-1]["event_seq"] == total
    assert [event["event_seq"] for event in drained] == list(
        range(delt + 1, total + 1)
    )

    assert api.drain_session_events(session_id) == []


def test_lifecycle_inflight_rejects_overlapping_same_datum_processing():
    api = AppTableSessionAPI(enable_persistence=False)
    created = api.create_VM_session(
        manifest=[],
        initial_parameter_overrides={},
        session_metadata={},
    )
    session_id = created["session_id"]
    eng = api._get(session_id)

    token = eng._begin_datum_lifecycle_processing_v1(["D1"])

    try:
        with pytest.raises(FatalEngineError):
            eng._begin_datum_lifecycle_processing_v1(["D1", "D2"])
    finally:
        eng._end_datum_lifecycle_processing_v1(token)

    token2 = eng._begin_datum_lifecycle_processing_v1(["D1"])
    eng._end_datum_lifecycle_processing_v1(token2)


def test_lifecycle_inflight_allows_disjoint_datums():
    api = AppTableSessionAPI(enable_persistence=False)
    created = api.create_VM_session(
        manifest=[],
        initial_parameter_overrides={},
        session_metadata={},
    )
    session_id = created["session_id"]
    eng = api._get(session_id)

    token1 = eng._begin_datum_lifecycle_processing_v1(["D1"])
    token2 = eng._begin_datum_lifecycle_processing_v1(["D2"])

    eng._end_datum_lifecycle_processing_v1(token2)
    eng._end_datum_lifecycle_processing_v1(token1)

    assert eng.engine_datums_on_span_inflight == set()