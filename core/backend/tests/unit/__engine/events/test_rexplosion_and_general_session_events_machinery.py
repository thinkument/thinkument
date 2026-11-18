from __future__ import annotations

import json
import re
from typing import Any, Dict, Mapping

import pytest
from __exceptions.engine import DatumLifecycleContractError

from _thinkengine._app_table_engine._engine_runtime_events_emission.engine_events_mixin import (
    set_session_event_callback,
    SESSION_EVENT_QUEUE_MAXLEN_V1,
)

from __datomatonTM import (
    register_datum_widget_v1,
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
    KEY_DATUM_LIFECYCLE,
    KEY_RUNTIME_WRITE_INDEX,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    drain_session_events as ui_drain_session_events,
    emit_session_event as ui_emit_session_event,
    get_concrete_session_api,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {
        "name": name,
        "type": "text",
        "required": required,
    }


def _multiframespec(
    *,
    datums: list[Mapping[str, Any]],
    spans: list[Mapping[str, Any]] | None = None,
    app_form_id: str = "tomorrow.events.form",
) -> Dict[str, Any]:
    if spans is None:
        spans = [
            {
                "id": "S",
                "owns": [str(d["id"]) for d in datums],
            }
        ]

    return {
        "app_form_id": app_form_id,
        "datums": [dict(d) for d in datums],
        "frames": [
            {
                "id": "F",
                "spans": [dict(s) for s in spans],
            }
        ],
    }


def _register_step(name: str, multiframespec: Mapping[str, Any]) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "multiframespec": dict(multiframespec),
        }

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _api() -> Any:
    api = get_concrete_session_api()
    install_repo = getattr(api, "install_session_repo", None)
    if callable(install_repo):
        install_repo(None)
    return api


def _start(api: Any, step_name: str) -> tuple[str, Dict[str, Any]]:
    st = api.create_VM_session(
        manifest=[
            {
                "public_step_name": "tomorrow_events_step",
                "step_fn": step_name,
                "fn_args": {},
            }
        ],
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
    return sid, ctx


def _q_datum(
    widget: str,
    *,
    datum_id: str = "D",
    max_reexplosions: int = 2,
    mount_explode: bool = False,
) -> Dict[str, Any]:
    return {
        "id": datum_id,
        "title": datum_id,
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": widget,
            "max_reexplosions": max_reexplosions,
            "mount_explode": mount_explode,
            "max_proc_notes": 4,
            "max_messages": 8,
        },
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=repr)


def _names(events: list[Mapping[str, Any]]) -> list[str]:
    return [str(ev["name"]) for ev in events]


def _assert_event_packet(
    event: Mapping[str, Any],
    *,
    datum_id: str,
    name: str,
    source: str,
    signal_kind: str,
    frame_id: str = "F",
    span_id: str = "S",
) -> None:
    assert event["kind"] == "datum_lifecycle_event_v1"
    assert isinstance(event["event_id"], str)
    assert event["event_id"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}T", str(event["emitted_at"]))
    assert event["source"] == source
    assert event["name"] == name
    assert event["form_id"]
    assert event["frame_id"] == frame_id
    assert event["span_id"] == span_id
    assert event["datum_id"] == datum_id
    assert event["signal_kind"] == signal_kind
    json.dumps(event, sort_keys=True)


def _assert_event_is_only_in_snapshot_queue(
    api: Any,
    sid: str,
    event_name: str,
    *,
    expected_payload_fragment: str | None = None,
) -> None:
    eng = api._get(sid)

    state_text = _json_text(eng.state)
    outputs_text = _json_text(api.get_outputs(sid))
    snapshot = api.export_session_snapshot(sid)
    snapshot_text = _json_text(snapshot)
    runtime_index_text = _json_text(eng.state.get(KEY_RUNTIME_WRITE_INDEX))
    lifecycle_text = _json_text(eng.state.get(KEY_DATUM_LIFECYCLE))

    # Events are not part of domain state, public outputs, write indexes, or
    # datum lifecycle memory.
    assert event_name not in state_text
    assert event_name not in outputs_text
    assert event_name not in runtime_index_text
    assert event_name not in lifecycle_text

    # The bounded canonical queue is intentionally persisted in the snapshot.
    assert event_name in snapshot_text
    assert isinstance(snapshot.get("session_events_v1"), list)
    assert isinstance(snapshot.get("next_session_event_seq_v1"), int)

    matching = [
        event
        for event in snapshot["session_events_v1"]
        if isinstance(event, Mapping)
        and event.get("name") == event_name
    ]
    assert matching

    for event in matching:
        assert isinstance(event.get("event_seq"), int)
        assert event["event_seq"] >= 1

    if expected_payload_fragment is not None:
        assert expected_payload_fragment not in state_text
        assert expected_payload_fragment not in outputs_text
        assert expected_payload_fragment not in runtime_index_text
        assert expected_payload_fragment not in lifecycle_text
        assert expected_payload_fragment in snapshot_text


@pytest.fixture(autouse=True)
def _reset_event_callback() -> None:
    set_session_event_callback(None)
    yield
    set_session_event_callback(None)


# ---------------------------------------------------------------------------
# Event packet, payload, transient queue, and drain contract
# ---------------------------------------------------------------------------


def test_widget_emit_packet_schema_defaults_payload_normalization_and_drain() -> None:
    seen: list[Dict[str, Any]] = []
    set_session_event_callback(lambda ev: seen.append(dict(ev)))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]("scalar-payload", name="test.scalar")
        q["emit"](["a", "b"], name="test.list")
        q["emit"]({"k": "v"}, name="test.mapping")
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
        }

    register_datum_widget_v1("test.tomorrow.schema", widget, overwrite=True)
    step_name = "test.tomorrow.schema.step"
    _register_step(
        step_name,
        _multiframespec(datums=[_q_datum("test.tomorrow.schema")]),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)
    ctx = api.step_session(sid, fill={"D": {"value": "x"}})

    assert ctx["kind"] == "ATCOMPLETION"

    # The platform callback sees live events immediately, in emission order.
    assert _names(seen) == ["test.scalar", "test.list", "test.mapping"]

    # Ordinary context must not expose the transient live-event queue.
    #
    # This is intentional: event packets can be frequent/large, and copying them
    # into every get_context/read-context path makes unrelated public-tape work
    # pay for lifecycle events.
    ctx_without_events = api.get_session_context(sid)
    assert "events" not in ctx_without_events or ctx_without_events["events"] == []

    # The explicit drain API is the live queue consumer.
    drained = api.drain_session_events(sid)
    assert _names(drained) == ["test.scalar", "test.list", "test.mapping"]

    scalar, list_ev, mapping = drained

    _assert_event_packet(
        scalar,
        datum_id="D",
        name="test.scalar",
        source="datum_widget",
        signal_kind="fill",
    )
    assert scalar["payload"] == {"value": "scalar-payload"}

    _assert_event_packet(
        list_ev,
        datum_id="D",
        name="test.list",
        source="datum_widget",
        signal_kind="fill",
    )
    assert list_ev["payload"] == {"value": ["a", "b"]}

    _assert_event_packet(
        mapping,
        datum_id="D",
        name="test.mapping",
        source="datum_widget",
        signal_kind="fill",
    )
    assert mapping["payload"] == {"k": "v"}

    # Drain is destructive/idempotent.
    assert api.drain_session_events(sid) == []

    ctx_after_drain = api.get_session_context(sid)
    assert "events" not in ctx_after_drain or ctx_after_drain["events"] == []


def test_inline_and_returned_events_are_fifo_unique_and_returned_payloads_normalize() -> None:
    seen: list[str] = []
    set_session_event_callback(lambda ev: seen.append(str(ev["name"])))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]({"n": 1}, name="test.one")
        q["emit"]({"n": 2}, name="test.two")
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
            "events": [
                {
                    "name": "test.three",
                    "payload": 3,
                },
                {
                    "name": "test.four",
                    "payload": {"n": 4},
                },
            ],
        }

    register_datum_widget_v1("test.tomorrow.fifo", widget, overwrite=True)
    step_name = "test.tomorrow.fifo.step"
    _register_step(
        step_name,
        _multiframespec(datums=[_q_datum("test.tomorrow.fifo")]),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)
    ctx = api.step_session(sid, fill={"D": {"value": "x"}})

    expected = ["test.one", "test.two", "test.three", "test.four"]
    assert ctx["kind"] == "ATCOMPLETION"
    assert seen == expected

    drained = api.drain_session_events(sid)
    assert _names(drained) == expected
    assert len({ev["event_id"] for ev in drained}) == 4

    _assert_event_packet(
        drained[2],
        datum_id="D",
        name="test.three",
        source="datum_widget_result",
        signal_kind="fill",
    )
    assert drained[2]["payload"] == {"value": 3}

    _assert_event_packet(
        drained[3],
        datum_id="D",
        name="test.four",
        source="datum_widget_result",
        signal_kind="fill",
    )
    assert drained[3]["payload"] == {"n": 4}
    assert api.drain_session_events(sid) == []


def test_no_callback_compatibility_and_drain_idempotence() -> None:
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]({"ok": True}, name="test.no.callback")
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
        }

    register_datum_widget_v1(
        "test.tomorrow.no.callback",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.no.callback.step"
    _register_step(
        step_name,
        _multiframespec(datums=[_q_datum("test.tomorrow.no.callback")]),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)
    ctx = api.step_session(sid, fill={"D": {"value": "x"}})

    assert ctx["kind"] == "ATCOMPLETION"
    drained = api.drain_session_events(sid)
    assert len(drained) == 1
    assert drained[0]["name"] == "test.no.callback"
    assert api.drain_session_events(sid) == []


def test_step_session_threaded_explosion_callback_receives_inline_and_returned_events() -> None:
    global_seen: list[str] = []
    threaded_seen: list[Dict[str, Any]] = []
    set_session_event_callback(lambda ev: global_seen.append(str(ev["name"])))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]({"n": 1}, name="test.threaded.inline")
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
            "events": [
                {
                    "name": "test.threaded.returned",
                    "payload": {"n": 2},
                }
            ],
        }

    register_datum_widget_v1(
        "test.tomorrow.threaded.callback",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.threaded.callback.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[_q_datum("test.tomorrow.threaded.callback")]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(
        sid,
        fill={"D": {"value": "x"}},
        threaded_callbacks={
            "explosion_events_callback": lambda ev: threaded_seen.append(
                dict(ev)
            ),
        },
    )

    assert ctx["kind"] == "ATCOMPLETION"
    assert _names(threaded_seen) == [
        "test.threaded.inline",
        "test.threaded.returned",
    ]

    # Per-dispatch callback replaces the legacy process-wide callback for that
    # dispatch. This prevents a controller request-specific observer from also
    # leaking into the global event observer.
    assert global_seen == []

    drained = api.drain_session_events(sid)
    assert [ev["event_id"] for ev in drained] == [
        ev["event_id"] for ev in threaded_seen
    ]
    assert _names(drained) == [
        "test.threaded.inline",
        "test.threaded.returned",
    ]

    _assert_event_packet(
        threaded_seen[0],
        datum_id="D",
        name="test.threaded.inline",
        source="datum_widget",
        signal_kind="fill",
    )
    _assert_event_packet(
        threaded_seen[1],
        datum_id="D",
        name="test.threaded.returned",
        source="datum_widget_result",
        signal_kind="fill",
    )


def test_threaded_explosion_callback_is_per_dispatch_and_does_not_persist() -> None:
    global_seen: list[str] = []
    threaded_seen: list[str] = []
    set_session_event_callback(lambda ev: global_seen.append(str(ev["name"])))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"](
            {"fill": dict(q.get("partial_fill") or {})},
            name="test.threaded.scope",
        )
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
        }

    register_datum_widget_v1(
        "test.tomorrow.threaded.scope",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.threaded.scope.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[
                _q_datum(
                    "test.tomorrow.threaded.scope",
                    datum_id="A",
                    max_reexplosions=0,
                ),
                _q_datum(
                    "test.tomorrow.threaded.scope",
                    datum_id="B",
                    max_reexplosions=0,
                ),
            ]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(
        sid,
        fill={"A": {"value": "a"}},
        threaded_callbacks={
            "explosion_events_callback": lambda ev: threaded_seen.append(
                str(ev["name"])
            ),
        },
    )
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = api.step_session(
        sid,
        fill={"B": {"value": "b"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"

    assert threaded_seen == ["test.threaded.scope"]
    assert global_seen == ["test.threaded.scope"]

    drained = api.drain_session_events(sid)
    assert _names(drained) == [
        "test.threaded.scope",
        "test.threaded.scope",
    ]
    assert drained[0]["datum_id"] == "A"
    assert drained[1]["datum_id"] == "B"


def test_threaded_explosion_callback_precedence_over_global_callback() -> None:
    global_seen: list[str] = []
    threaded_seen: list[str] = []
    set_session_event_callback(lambda ev: global_seen.append(str(ev["name"])))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]({"ok": True}, name="test.threaded.precedence")
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
        }

    register_datum_widget_v1(
        "test.tomorrow.threaded.precedence",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.threaded.precedence.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[_q_datum("test.tomorrow.threaded.precedence")]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(
        sid,
        fill={"D": {"value": "x"}},
        threaded_callbacks={
            "explosion_events_callback": lambda ev: threaded_seen.append(
                str(ev["name"])
            ),
        },
    )

    assert ctx["kind"] == "ATCOMPLETION"
    assert threaded_seen == ["test.threaded.precedence"]
    assert global_seen == []
    assert _names(api.drain_session_events(sid)) == [
        "test.threaded.precedence"
    ]


def test_empty_threaded_callbacks_keeps_legacy_global_callback_behavior() -> None:
    global_seen: list[str] = []

    set_session_event_callback(lambda ev: global_seen.append(str(ev["name"])))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]({"ok": True}, name="test.threaded.empty.bag")
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
        }

    register_datum_widget_v1(
        "test.tomorrow.threaded.empty.bag",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.threaded.empty.bag.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[_q_datum("test.tomorrow.threaded.empty.bag")]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(
        sid,
        fill={"D": {"value": "x"}},
        threaded_callbacks={},
    )

    assert ctx["kind"] == "ATCOMPLETION"
    assert global_seen == ["test.threaded.empty.bag"]
    assert _names(api.drain_session_events(sid)) == [
        "test.threaded.empty.bag"
    ]


# ---------------------------------------------------------------------------
# Artificial / external event API
# ---------------------------------------------------------------------------


def test_external_event_infers_current_manual_ids_scalar_payload_and_does_not_mutate_state() -> None:
    seen: list[Dict[str, Any]] = []
    set_session_event_callback(lambda ev: seen.append(dict(ev)))

    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    step_name = "test.tomorrow.external.infer.step"
    _register_step(step_name, _multiframespec(datums=[datum]))

    api = _api()
    sid, ctx = _start(api, step_name)
    assert ctx["current_frame_id"] == "F"
    assert ctx["current_span"] == "S"

    before_state = _json_text(api._get(sid).state)
    ev = api.emit_session_event(
        sid,
        datum_id="D",
        payload="hello",
        name="test.external.scalar",
    )
    after_state = _json_text(api._get(sid).state)

    _assert_event_packet(
        ev,
        datum_id="D",
        name="test.external.scalar",
        source="external",
        signal_kind="external",
    )
    assert ev["payload"] == {"value": "hello"}
    assert seen[-1]["event_id"] == ev["event_id"]
    assert api.drain_session_events(sid)[-1]["event_id"] == ev["event_id"]
    assert before_state == after_state

    ctx = api.step_session(sid, fill={"D": {"value": "done"}})
    assert ctx["kind"] == "ATCOMPLETION"


def test_external_event_accepts_explicit_ids_after_completion_and_ui_reexports() -> None:
    seen: list[str] = []
    set_session_event_callback(lambda ev: seen.append(str(ev["name"])))

    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    step_name = "test.tomorrow.external.explicit.step"
    _register_step(
        step_name,
        _multiframespec(datums=[datum], app_form_id="explicit.form"),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"

    ev = ui_emit_session_event(
        sid,
        form_id="explicit.form",
        frame_id="F",
        span_id="S",
        datum_id="D",
        payload=123,
        name="test.external.explicit",
    )

    _assert_event_packet(
        ev,
        datum_id="D",
        name="test.external.explicit",
        source="external",
        signal_kind="external",
    )
    assert ev["form_id"] == "explicit.form"
    assert ev["payload"] == {"value": 123}
    assert seen == ["test.external.explicit"]

    drained = ui_drain_session_events(sid)
    assert len(drained) == 1
    assert drained[0]["event_id"] == ev["event_id"]
    assert ui_drain_session_events(sid) == []


def test_external_event_requires_resolvable_location_after_completion_without_explicit_ids() -> None:
    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    step_name = "test.tomorrow.external.no.location.step"
    _register_step(step_name, _multiframespec(datums=[datum]))

    api = _api()
    sid, _ctx = _start(api, step_name)
    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"

    with pytest.raises(ValueError, match="form_id/frame_id/span_id"):
        api.emit_session_event(
            sid,
            datum_id="D",
            payload={},
            name="test.external.no.location",
        )

    ev = api.emit_session_event(
        sid,
        form_id="tomorrow.events.form",
        frame_id="F",
        span_id="S",
        datum_id="D",
        payload={},
        name="test.external.explicit.after.error",
    )
    assert ev["name"] == "test.external.explicit.after.error"
    assert api.drain_session_events(sid)[0]["event_id"] == ev["event_id"]


def test_external_event_per_call_callback_is_sink_after_queue_and_precedes_global() -> None:
    global_seen: list[str] = []
    per_call_seen: list[Dict[str, Any]] = []
    set_session_event_callback(lambda ev: global_seen.append(str(ev["name"])))

    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    step_name = "test.tomorrow.external.per.call.callback.step"
    _register_step(step_name, _multiframespec(datums=[datum]))

    api = _api()
    sid, _ctx = _start(api, step_name)

    ev = api.emit_session_event(
        sid,
        datum_id="D",
        payload={"ok": True},
        name="test.external.per.call.callback",
        event_callback=lambda event: per_call_seen.append(dict(event)),
    )

    assert _names(per_call_seen) == ["test.external.per.call.callback"]
    assert global_seen == []

    drained = api.drain_session_events(sid)
    assert len(drained) == 1
    assert drained[0]["event_id"] == ev["event_id"]
    assert per_call_seen[0]["event_id"] == ev["event_id"]


def test_external_event_callback_exception_still_leaves_event_queued() -> None:
    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    step_name = "test.tomorrow.external.callback.exception.step"
    _register_step(step_name, _multiframespec(datums=[datum]))

    api = _api()
    sid, _ctx = _start(api, step_name)

    def callback(_ev: Mapping[str, Any]) -> None:
        raise RuntimeError("external callback exploded")

    with pytest.raises(RuntimeError, match="external callback exploded"):
        api.emit_session_event(
            sid,
            datum_id="D",
            payload={"ok": True},
            name="test.external.callback.exception",
            event_callback=callback,
        )

    drained = api.drain_session_events(sid)
    assert len(drained) == 1
    assert drained[0]["name"] == "test.external.callback.exception"


def test_cross_session_event_queues_are_isolated() -> None:
    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    step_name = "test.tomorrow.cross.session.step"
    _register_step(step_name, _multiframespec(datums=[datum]))

    api = _api()
    sid1, _ctx1 = _start(api, step_name)
    sid2, _ctx2 = _start(api, step_name)

    ev1 = api.emit_session_event(
        sid1,
        datum_id="D",
        payload={"session": 1},
        name="test.cross.session.one",
    )
    ev2 = api.emit_session_event(
        sid2,
        datum_id="D",
        payload={"session": 2},
        name="test.cross.session.two",
    )

    drained1 = api.drain_session_events(sid1)
    drained2 = api.drain_session_events(sid2)

    assert [ev["event_id"] for ev in drained1] == [ev1["event_id"]]
    assert [ev["event_id"] for ev in drained2] == [ev2["event_id"]]
    assert drained1[0]["payload"] == {"session": 1}
    assert drained2[0]["payload"] == {"session": 2}
    assert api.drain_session_events(sid1) == []
    assert api.drain_session_events(sid2) == []


# ---------------------------------------------------------------------------
# Snapshot durability and non-domain-state laws
# ---------------------------------------------------------------------------


def test_events_are_snapshot_queued_but_not_written_to_domain_state_or_outputs() -> None:
    payload = {
        "large": "X" * 16_000,
        "nested": {"ok": True},
    }

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"](payload, name="test.snapshot.queue.large")
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {"small": "state"},
        }

    register_datum_widget_v1(
        "test.tomorrow.snapshot.queue",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.snapshot.queue.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[_q_datum("test.tomorrow.snapshot.queue")]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)
    ctx = api.step_session(sid, fill={"D": {"value": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"

    snapshot = api.export_session_snapshot(sid)
    retained = [
        event
        for event in snapshot["session_events_v1"]
        if event.get("name") == "test.snapshot.queue.large"
    ]
    assert len(retained) == 1
    assert retained[0]["payload"] == payload
    assert retained[0]["event_seq"] >= 1

    _assert_event_is_only_in_snapshot_queue(
        api,
        sid,
        "test.snapshot.queue.large",
        expected_payload_fragment="X" * 1000,
    )

    drained = api.drain_session_events(sid)
    assert len(drained) == 1
    assert drained[0] == retained[0]
    assert api.drain_session_events(sid) == []


def test_snapshot_import_restores_undrained_events_and_continues_sequence() -> None:
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]({"n": 1}, name="test.before.snapshot")
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
        }

    register_datum_widget_v1(
        "test.tomorrow.snapshot.restore",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.snapshot.restore.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[_q_datum("test.tomorrow.snapshot.restore")]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)
    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"

    eng_before = api._get(sid)
    assert len(eng_before._session_events_v1) == 1

    retained_before = dict(eng_before._session_events_v1[0])
    assert retained_before["name"] == "test.before.snapshot"
    assert retained_before["event_seq"] >= 1

    snapshot = api.export_session_snapshot(sid)
    expected_next_seq = snapshot["next_session_event_seq_v1"]
    assert expected_next_seq == retained_before["event_seq"] + 1

    # Destroy current queue contents before import.
    assert api.drain_session_events(sid) == [retained_before]
    assert api.drain_session_events(sid) == []

    api.import_session_snapshot(sid, snapshot=snapshot)

    restored = api.drain_session_events(sid)
    assert restored == [retained_before]
    assert api.drain_session_events(sid) == []

    emitted_after = api.emit_session_event(
        sid,
        form_id="tomorrow.events.form",
        frame_id="F",
        span_id="S",
        datum_id="D",
        payload={"n": 2},
        name="test.after.snapshot",
    )
    assert "event_seq" not in emitted_after

    queued_after = api.drain_session_events(sid)
    assert len(queued_after) == 1
    assert queued_after[0]["event_id"] == emitted_after["event_id"]
    assert queued_after[0]["event_seq"] == expected_next_seq


def test_event_queue_is_bounded_and_preserves_monotonic_event_sequence() -> None:
    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    step_name = "test.tomorrow.queue.bound.step"
    _register_step(step_name, _multiframespec(datums=[datum]))

    api = _api()
    sid, _ctx = _start(api, step_name)

    delt = 6
    total = SESSION_EVENT_QUEUE_MAXLEN_V1 + delt

    for i in range(total):
        api.emit_session_event(
            sid,
            datum_id="D",
            payload={"i": i},
            name=f"test.external.{i}",
        )

    snapshot = api.export_session_snapshot(sid)
    retained_snapshot = snapshot["session_events_v1"]

    assert len(retained_snapshot) == SESSION_EVENT_QUEUE_MAXLEN_V1
    assert retained_snapshot[0]["payload"] == {"i": delt}
    assert retained_snapshot[-1]["payload"] == {"i": total - 1}
    assert retained_snapshot[0]["event_seq"] == delt + 1
    assert retained_snapshot[-1]["event_seq"] == total
    assert snapshot["next_session_event_seq_v1"] == total + 1

    drained = api.drain_session_events(sid)
    assert drained == retained_snapshot
    assert api.drain_session_events(sid) == []


def test_latest_event_seq_is_o1_high_water_and_cannot_be_forged_by_producer() -> None:
    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    step_name = "test.tomorrow.latest.seq.step"
    _register_step(step_name, _multiframespec(datums=[datum]))

    api = _api()
    sid, _ctx = _start(api, step_name)

    assert api.get_latest_session_event_seq(sid) == 0

    first = api.record_session_event(
        sid,
        {
            "kind": "test_event_v1",
            "event_id": "producer-one",
            "event_seq": 999_999,
        },
    )
    second = api.record_session_event(
        sid,
        {
            "kind": "test_event_v1",
            "event_id": "producer-two",
            "event_seq": 1,
        },
    )

    assert first["event_seq"] == 1
    assert second["event_seq"] == 2
    assert api.get_latest_session_event_seq(sid) == 2
    assert [event["event_seq"] for event in api.get_session_events(sid)] == [1, 2]


# ---------------------------------------------------------------------------
# Contract errors / sad paths
# ---------------------------------------------------------------------------


def test_non_json_emit_payload_blocks_submit_without_silent_delivery() -> None:
    seen: list[Dict[str, Any]] = []
    set_session_event_callback(lambda ev: seen.append(dict(ev)))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]({"bad": object()}, name="test.bad.payload")
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
        }

    register_datum_widget_v1(
        "test.tomorrow.bad.payload",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.bad.payload.step"
    _register_step(
        step_name,
        _multiframespec(datums=[_q_datum("test.tomorrow.bad.payload")]),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    with pytest.raises(DatumLifecycleContractError):
        api.step_session(sid, fill={"D": {"value": "x"}})


def test_bad_returned_event_entry_from_widget_lifecycle_fn_is_fatal() -> None:
    def widget(_q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
            "events": ["not-a-mapping"],
        }

    register_datum_widget_v1(
        "test.tomorrow.bad.returned.event",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.bad.returned.event.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[_q_datum("test.tomorrow.bad.returned.event")]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    with pytest.raises(DatumLifecycleContractError):
        api.step_session(sid, fill={"D": {"value": "x"}})


def test_callback_exception_is_fatal() -> None:
    def callback(_ev: Mapping[str, Any]) -> None:
        raise RuntimeError("callback exploded")

    set_session_event_callback(callback)

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]({"ok": True}, name="test.callback.raises")
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
        }

    register_datum_widget_v1(
        "test.tomorrow.callback.raises",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.callback.raises.step"
    _register_step(
        step_name,
        _multiframespec(datums=[_q_datum("test.tomorrow.callback.raises")]),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    with pytest.raises(Exception):
        ctx = api.step_session(sid, fill={"D": {"value": "x"}})
        assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
        assert "callback exploded" in ctx["last_error"]["D"]
        assert api._get(sid).engine_datums_on_span_inflight == set()

    drained = api.drain_session_events(sid)
    assert len(drained) == 1
    assert drained[0]["name"] == "test.callback.raises"

    set_session_event_callback(None)
    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert api._get(sid).engine_datums_on_span_inflight == set()


# ---------------------------------------------------------------------------
# Mount/reexplode/block/done/forced lifecycle paths
# ---------------------------------------------------------------------------


def test_mount_explode_emits_before_first_public_render_and_is_idempotent_on_context_reads() -> None:
    seen: list[Dict[str, Any]] = []
    set_session_event_callback(lambda ev: seen.append(dict(ev)))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        signal = dict(q.get("signal") or {})
        if signal.get("kind") == "mount":
            q["emit"](
                {
                    "span": q.get("span_id"),
                    "info": dict(signal.get("info") or {}),
                },
                name="test.mount.before.render",
            )
            datum = dict(q["datum"])
            lifecycle = dict(datum.get("lifecycle") or {})
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "micros": [_text_micro("mounted")],
                    "lifecycle": {
                        **lifecycle,
                        "widget": "test.tomorrow.mount.before.render",
                        "mount_explode": True,
                        "max_reexplosions": 2,
                    },
                },
                "fill": {"mounted": ""},
                "state": {"mounted": True},
                "message": {"level": "info", "text": "mounted"},
            }

        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {"done": True},
        }

    register_datum_widget_v1(
        "test.tomorrow.mount.before.render",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.mount.before.render.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[
                _q_datum(
                    "test.tomorrow.mount.before.render",
                    mount_explode=True,
                    max_reexplosions=2,
                )
            ]
        ),
    )

    api = _api()
    sid, ctx = _start(api, step_name)

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "mounted" in _json_text(ctx["datum_widget_decls"]["D"])
    assert len(seen) == 1
    assert seen[0]["name"] == "test.mount.before.render"
    assert seen[0]["signal_kind"] == "mount"

    api.get_session_context(sid)
    api.get_session_context(sid)
    assert len(seen) == 1

    drained = api.drain_session_events(sid)
    assert len(drained) == 1
    assert drained[0]["name"] == "test.mount.before.render"

    ctx = api.step_session(sid, fill={"D": {"mounted": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"


def test_mount_explode_reused_datum_emits_once_per_span_not_per_context_read() -> None:
    seen: list[str] = []
    set_session_event_callback(lambda ev: seen.append(str(ev["name"])))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        signal = dict(q.get("signal") or {})
        span_id = str(q.get("span_id"))
        if signal.get("kind") == "mount":
            q["emit"](
                {"span": span_id},
                name=f"test.mount.{span_id}",
            )
            datum = dict(q["datum"])
            lifecycle = dict(datum.get("lifecycle") or {})
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "micros": [_text_micro(f"mounted_{span_id}")],
                    "lifecycle": {
                        **lifecycle,
                        "widget": "test.tomorrow.mount.reused",
                        "mount_explode": True,
                        "max_reexplosions": 2,
                    },
                },
                "fill": {f"mounted_{span_id}": ""},
                "state": {"mounted_span": span_id},
                "message": {"level": "info", "text": f"mounted {span_id}"},
            }

        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {"done": span_id},
        }

    register_datum_widget_v1(
        "test.tomorrow.mount.reused",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.mount.reused.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[
                _q_datum(
                    "test.tomorrow.mount.reused",
                    mount_explode=True,
                    max_reexplosions=2,
                )
            ],
            spans=[
                {"id": "S1", "owns": ["D"]},
                {"id": "S2", "owns": ["D"]},
            ],
        ),
    )

    api = _api()
    sid, ctx = _start(api, step_name)

    assert ctx["current_span"] == "S1"
    assert "mounted_S1" in _json_text(ctx["datum_widget_decls"]["D"])
    assert seen == ["test.mount.S1"]

    api.get_session_context(sid)
    api.get_session_context(sid)
    assert seen == ["test.mount.S1"]
    assert _names(api.drain_session_events(sid)) == ["test.mount.S1"]

    ctx = api.step_session(sid, fill={"D": {"mounted_S1": "one"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S2"
    assert "mounted_S2" in _json_text(ctx["datum_widget_decls"]["D"])
    assert seen == ["test.mount.S1", "test.mount.S2"]

    api.get_session_context(sid)
    assert seen == ["test.mount.S1", "test.mount.S2"]
    assert _names(api.drain_session_events(sid)) == ["test.mount.S2"]

    ctx = api.step_session(sid, fill={"D": {"mounted_S2": "two"}})
    assert ctx["kind"] == "ATCOMPLETION"


def test_blocked_reexplode_done_and_forced_done_paths_all_deliver_events() -> None:
    seen: list[str] = []
    set_session_event_callback(lambda ev: seen.append(str(ev["name"])))

    def blocked(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]({"path": "blocked"}, name="test.blocked")
        return {
            "status": "blocked",
            "message": {"level": "error", "text": "blocked"},
            "state": {},
        }

    def reexplode_then_done(q: Mapping[str, Any]) -> Mapping[str, Any]:
        partial = dict(q.get("partial_fill") or {})
        q["emit"]({"partial": partial}, name="test.re_or_done")
        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": "done"},
                "state": {},
            }

        datum = dict(q["datum"])
        lifecycle = dict(datum.get("lifecycle") or {})
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    **lifecycle,
                    "widget": "test.tomorrow.re_done",
                    "max_reexplosions": 1,
                },
            },
            "fill": {"confirm": ""},
            "state": {},
            "message": {"level": "info", "text": "confirm"},
        }

    def forced(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"]({"path": "forced"}, name="test.forced")
        datum = dict(q["datum"])
        lifecycle = dict(datum.get("lifecycle") or {})
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("again")],
                "lifecycle": {
                    **lifecycle,
                    "widget": "test.tomorrow.forced",
                    "max_reexplosions": 0,
                },
            },
            "state": {},
            "message": {"level": "warning", "text": "again"},
        }

    register_datum_widget_v1(
        "test.tomorrow.blocked",
        blocked,
        overwrite=True,
    )
    register_datum_widget_v1(
        "test.tomorrow.re_done",
        reexplode_then_done,
        overwrite=True,
    )
    register_datum_widget_v1(
        "test.tomorrow.forced",
        forced,
        overwrite=True,
    )

    api = _api()

    step_blocked = "test.tomorrow.blocked.step"
    _register_step(
        step_blocked,
        _multiframespec(datums=[_q_datum("test.tomorrow.blocked")]),
    )
    sid_blocked, _ = _start(api, step_blocked)
    ctx = api.step_session(sid_blocked, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "blocked" in ctx["last_error"]["D"]
    assert api.drain_session_events(sid_blocked)[0]["name"] == "test.blocked"

    step_re_done = "test.tomorrow.re_done.step"
    _register_step(
        step_re_done,
        _multiframespec(datums=[_q_datum("test.tomorrow.re_done")]),
    )
    sid_re_done, _ = _start(api, step_re_done)
    ctx = api.step_session(sid_re_done, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert api.drain_session_events(sid_re_done)[0]["name"] == (
        "test.re_or_done"
    )

    ctx = api.step_session(sid_re_done, fill={"D": {"confirm": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert api.drain_session_events(sid_re_done)[0]["name"] == (
        "test.re_or_done"
    )

    step_forced = "test.tomorrow.forced.step"
    _register_step(
        step_forced,
        _multiframespec(
            datums=[
                _q_datum(
                    "test.tomorrow.forced",
                    max_reexplosions=0,
                )
            ]
        ),
    )
    sid_forced, _ = _start(api, step_forced)
    ctx = api.step_session(sid_forced, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert api.drain_session_events(sid_forced)[0]["name"] == "test.forced"

    assert "test.blocked" in seen
    assert "test.re_or_done" in seen
    assert "test.forced" in seen


# ---------------------------------------------------------------------------
# Dirty-set combinatorics, vector submits, and inflight guard laws
# ---------------------------------------------------------------------------


def test_disjoint_dirty_sets_same_span_emit_independently_and_do_not_cross_invoke() -> None:
    calls: Dict[str, int] = {"A": 0, "B": 0, "C": 0}
    seen: list[str] = []
    set_session_event_callback(lambda ev: seen.append(str(ev["name"])))

    def make_widget(datum_id: str):
        def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
            calls[datum_id] += 1
            q["emit"]({"datum": datum_id}, name=f"test.{datum_id}.emit")
            return {
                "status": "done",
                "message": {"level": "success", "text": f"{datum_id} done"},
                "state": {"done": datum_id},
            }

        return widget

    for datum_id in ("A", "B", "C"):
        register_datum_widget_v1(
            f"test.tomorrow.disjoint.{datum_id}",
            make_widget(datum_id),
            overwrite=True,
        )

    datums = [
        _q_datum(
            "test.tomorrow.disjoint.A",
            datum_id="A",
            max_reexplosions=0,
        ),
        _q_datum(
            "test.tomorrow.disjoint.B",
            datum_id="B",
            max_reexplosions=0,
        ),
        _q_datum(
            "test.tomorrow.disjoint.C",
            datum_id="C",
            max_reexplosions=0,
        ),
    ]
    step_name = "test.tomorrow.disjoint.three.step"
    _register_step(step_name, _multiframespec(datums=datums))

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"A": {"value": "a"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1, "B": 0, "C": 0}
    assert seen == ["test.A.emit"]

    ctx = api.step_session(sid, fill={"B": {"value": "b"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1, "B": 1, "C": 0}
    assert seen == ["test.A.emit", "test.B.emit"]

    ctx = api.step_session(sid, fill={"C": {"value": "c"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"A": 1, "B": 1, "C": 1}
    assert seen == ["test.A.emit", "test.B.emit", "test.C.emit"]

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "a"
    assert out["form_fills"]["B"]["value"] == "b"
    assert out["form_fills"]["C"]["value"] == "c"


def test_multi_datum_vector_submit_evaluates_each_touched_lifecycle_once_and_emits_in_declaration_order() -> None:
    calls: Dict[str, int] = {"A": 0, "B": 0}
    seen: list[str] = []
    set_session_event_callback(lambda ev: seen.append(str(ev["name"])))

    def make_widget(datum_id: str):
        def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
            calls[datum_id] += 1
            q["emit"]({"datum": datum_id}, name=f"test.vector.{datum_id}")
            return {
                "status": "done",
                "message": {"level": "success", "text": "done"},
                "state": {},
            }

        return widget

    register_datum_widget_v1(
        "test.tomorrow.vector.A",
        make_widget("A"),
        overwrite=True,
    )
    register_datum_widget_v1(
        "test.tomorrow.vector.B",
        make_widget("B"),
        overwrite=True,
    )

    step_name = "test.tomorrow.vector.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[
                _q_datum(
                    "test.tomorrow.vector.A",
                    datum_id="A",
                    max_reexplosions=0,
                ),
                _q_datum(
                    "test.tomorrow.vector.B",
                    datum_id="B",
                    max_reexplosions=0,
                ),
            ]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(
        sid,
        fill={
            "A": {"value": "a"},
            "B": {"value": "b"},
        },
    )

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"A": 1, "B": 1}
    assert seen == ["test.vector.A", "test.vector.B"]
    assert _names(api.drain_session_events(sid)) == seen


def test_multi_datum_vector_submit_threads_explosion_callback_in_declaration_order() -> None:
    global_seen: list[str] = []
    threaded_seen: list[str] = []
    set_session_event_callback(lambda ev: global_seen.append(str(ev["name"])))

    def make_widget(datum_id: str):
        def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
            q["emit"](
                {"datum": datum_id},
                name=f"test.threaded.vector.{datum_id}",
            )
            return {
                "status": "done",
                "message": {"level": "success", "text": "done"},
                "state": {},
            }

        return widget

    register_datum_widget_v1(
        "test.tomorrow.threaded.vector.A",
        make_widget("A"),
        overwrite=True,
    )
    register_datum_widget_v1(
        "test.tomorrow.threaded.vector.B",
        make_widget("B"),
        overwrite=True,
    )

    step_name = "test.tomorrow.threaded.vector.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[
                _q_datum(
                    "test.tomorrow.threaded.vector.A",
                    datum_id="A",
                    max_reexplosions=0,
                ),
                _q_datum(
                    "test.tomorrow.threaded.vector.B",
                    datum_id="B",
                    max_reexplosions=0,
                ),
            ]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(
        sid,
        fill={
            "A": {"value": "a"},
            "B": {"value": "b"},
        },
        threaded_callbacks={
            "explosion_events_callback": lambda ev: threaded_seen.append(
                str(ev["name"])
            ),
        },
    )

    assert ctx["kind"] == "ATCOMPLETION"
    assert threaded_seen == [
        "test.threaded.vector.A",
        "test.threaded.vector.B",
    ]
    assert global_seen == []
    assert _names(api.drain_session_events(sid)) == threaded_seen


def test_inflight_lifecycle_guard_allows_disjoint_sets_rejects_overlap_and_releases() -> None:
    datums = [
        {"id": "A", "title": "A", "micros": [_text_micro()]},
        {"id": "B", "title": "B", "micros": [_text_micro()]},
        {"id": "C", "title": "C", "micros": [_text_micro()]},
    ]
    step_name = "test.tomorrow.inflight.direct.step"
    _register_step(step_name, _multiframespec(datums=datums))

    api = _api()
    sid, _ctx = _start(api, step_name)
    eng = api._get(sid)

    token_a = eng._begin_datum_lifecycle_processing_v1(["A"])
    token_b = eng._begin_datum_lifecycle_processing_v1(["B", "C"])

    with pytest.raises(Exception, match="already in progress"):
        eng._begin_datum_lifecycle_processing_v1(["C"])

    eng._end_datum_lifecycle_processing_v1(token_b)
    token_c = eng._begin_datum_lifecycle_processing_v1(["C"])
    eng._end_datum_lifecycle_processing_v1(token_c)
    eng._end_datum_lifecycle_processing_v1(token_a)

    assert eng.engine_datums_on_span_inflight == set()


def test_combined_fill_with_overlapping_inflight_set_rejects_before_widget_execution() -> None:
    calls: Dict[str, int] = {"A": 0, "B": 0}

    def make_widget(datum_id: str):
        def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
            calls[datum_id] += 1
            q["emit"]({"datum": datum_id}, name=f"test.overlap.{datum_id}")
            return {
                "status": "done",
                "message": {"level": "success", "text": "done"},
                "state": {},
            }

        return widget

    register_datum_widget_v1(
        "test.tomorrow.overlap.A",
        make_widget("A"),
        overwrite=True,
    )
    register_datum_widget_v1(
        "test.tomorrow.overlap.B",
        make_widget("B"),
        overwrite=True,
    )

    step_name = "test.tomorrow.overlap.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[
                _q_datum(
                    "test.tomorrow.overlap.A",
                    datum_id="A",
                    max_reexplosions=0,
                ),
                _q_datum(
                    "test.tomorrow.overlap.B",
                    datum_id="B",
                    max_reexplosions=0,
                ),
            ]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)
    eng = api._get(sid)

    token = eng._begin_datum_lifecycle_processing_v1(["A"])
    try:
        with pytest.raises(Exception, match="already in progress"):
            api.step_session(
                sid,
                fill={
                    "A": {"value": "a"},
                    "B": {"value": "b"},
                },
            )
        assert calls == {"A": 0, "B": 0}
        assert api.drain_session_events(sid) == []
    finally:
        eng._end_datum_lifecycle_processing_v1(token)

    ctx = api.step_session(
        sid,
        fill={
            "A": {"value": "a"},
            "B": {"value": "b"},
        },
    )
    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"A": 1, "B": 1}
    assert _names(api.drain_session_events(sid)) == [
        "test.overlap.A",
        "test.overlap.B",
    ]


def test_disjoint_reexplode_surfaces_interleave_without_cross_eval() -> None:
    calls: Dict[str, int] = {"A": 0, "B": 0}
    seen: list[str] = []
    set_session_event_callback(lambda ev: seen.append(str(ev["name"])))

    def make_widget(datum_id: str):
        def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
            calls[datum_id] += 1
            partial = dict(q.get("partial_fill") or {})

            if "confirm" not in partial:
                q["emit"](
                    {"phase": "reexplode"},
                    name=f"test.{datum_id}.reexplode",
                )
                datum = dict(q["datum"])
                lifecycle = dict(datum.get("lifecycle") or {})
                return {
                    "status": "reexplode",
                    "datum": {
                        **datum,
                        "micros": [_text_micro("confirm")],
                        "lifecycle": {
                            **lifecycle,
                            "widget": f"test.tomorrow.interleave.{datum_id}",
                            "max_reexplosions": 2,
                        },
                    },
                    "fill": {"confirm": ""},
                    "state": {"phase": "confirm"},
                    "message": {"level": "info", "text": "confirm"},
                }

            q["emit"](
                {"phase": "done"},
                name=f"test.{datum_id}.done",
            )
            return {
                "status": "done",
                "message": {"level": "success", "text": "done"},
                "state": {"phase": "done"},
            }

        return widget

    register_datum_widget_v1(
        "test.tomorrow.interleave.A",
        make_widget("A"),
        overwrite=True,
    )
    register_datum_widget_v1(
        "test.tomorrow.interleave.B",
        make_widget("B"),
        overwrite=True,
    )

    step_name = "test.tomorrow.interleave.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[
                _q_datum(
                    "test.tomorrow.interleave.A",
                    datum_id="A",
                ),
                _q_datum(
                    "test.tomorrow.interleave.B",
                    datum_id="B",
                ),
            ]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"A": {"value": "a"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1, "B": 0}

    ctx = api.step_session(sid, fill={"B": {"value": "b"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1, "B": 1}

    ctx = api.step_session(sid, fill={"A": {"confirm": "yes-a"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 2, "B": 1}

    ctx = api.step_session(sid, fill={"B": {"confirm": "yes-b"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"A": 2, "B": 2}

    assert seen == [
        "test.A.reexplode",
        "test.B.reexplode",
        "test.A.done",
        "test.B.done",
    ]
    assert _names(api.drain_session_events(sid)) == seen

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["confirm"] == "yes-a"
    assert out["form_fills"]["B"]["confirm"] == "yes-b"


# ---------------------------------------------------------------------------
# Undo/redo live-event behavior
# ---------------------------------------------------------------------------


def test_undo_does_not_restore_drained_datum_event_and_redo_reemits_fresh_event() -> None:
    seen: list[str] = []
    set_session_event_callback(lambda ev: seen.append(str(ev["event_id"])))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        q["emit"](
            {"fill": dict(q.get("partial_fill") or {})},
            name="test.redo.reemit",
        )
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
        }

    register_datum_widget_v1(
        "test.tomorrow.redo.reemit",
        widget,
        overwrite=True,
    )
    step_name = "test.tomorrow.redo.reemit.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[_q_datum("test.tomorrow.redo.reemit")]
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "one"}})
    assert ctx["kind"] == "ATCOMPLETION"

    first_events = api.drain_session_events(sid)
    assert len(first_events) == 1
    first = first_events[0]
    assert first["name"] == "test.redo.reemit"

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    after_undo = api.drain_session_events(sid)
    assert not any(
        event.get("event_id") == first["event_id"]
        for event in after_undo
    )
    assert not any(
        event.get("name") == "test.redo.reemit"
        for event in after_undo
    )

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "ATCOMPLETION"

    second_events = api.drain_session_events(sid)
    matching = [
        event
        for event in second_events
        if event.get("name") == "test.redo.reemit"
    ]
    assert len(matching) == 1

    second = matching[0]
    assert second["event_id"] != first["event_id"]
    assert second["event_seq"] > first["event_seq"]
    assert seen == [
        first["event_id"],
        second["event_id"],
    ]