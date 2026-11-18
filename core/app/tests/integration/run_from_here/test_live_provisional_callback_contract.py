from __future__ import annotations

from _thinksessions.run.run_from_here import (
    _threaded_callbacks_for_live_delivery_v1,
)
from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    CONTROLLER_EVENTS_CALLBACK_KEY,
    EXPLOSION_EVENTS_CALLBACK_KEY,
    provisional_event_copy_v1,
)


def _canonical_datum_message() -> dict:
    return {
        "kind": "datum_lifecycle_event_v1",
        "event_id": "event-1",
        "emitted_at": "2026-10-01T18:21:07Z",
        "source": "datum_widget",
        "name": "datum.message",
        "form_id": "form",
        "frame_id": "frame",
        "span_id": "span",
        "datum_id": "board",
        "signal_kind": "fill",
        "payload": {
            "message": {
                "level": "info",
                "text": "progress",
            }
        },
        "event_seq": 4,
    }


def test_provisional_event_copy_removes_only_queue_cursor_and_is_defensive():
    canonical = _canonical_datum_message()

    live = provisional_event_copy_v1(canonical)

    assert "event_seq" not in live
    assert canonical["event_seq"] == 4
    assert live["event_id"] == canonical["event_id"]
    assert live["payload"] == canonical["payload"]

    live["payload"]["message"]["text"] = "changed by observer"
    assert canonical["payload"]["message"]["text"] == "progress"


def test_run_from_here_adapts_only_explosion_callback_and_forwards_context_hook():
    explosion_seen: list[dict] = []
    controller_seen: list[dict] = []
    contexts_seen: list[dict] = []

    class ExplosionObserver:
        def __call__(self, event):
            explosion_seen.append(dict(event))

        def observe_unmodulated_context_v1(self, U):
            contexts_seen.append(dict(U))

    explosion_observer = ExplosionObserver()

    def controller_observer(event):
        controller_seen.append(dict(event))

    prepared = _threaded_callbacks_for_live_delivery_v1(
        {
            EXPLOSION_EVENTS_CALLBACK_KEY: explosion_observer,
            CONTROLLER_EVENTS_CALLBACK_KEY: controller_observer,
            "unrelated": "preserved",
        }
    )

    assert prepared is not None
    assert prepared["unrelated"] == "preserved"
    assert prepared[CONTROLLER_EVENTS_CALLBACK_KEY] is controller_observer

    canonical = _canonical_datum_message()
    prepared[EXPLOSION_EVENTS_CALLBACK_KEY](canonical)

    assert len(explosion_seen) == 1
    assert "event_seq" not in explosion_seen[0]
    assert explosion_seen[0]["event_id"] == canonical["event_id"]
    assert canonical["event_seq"] == 4

    prepared[EXPLOSION_EVENTS_CALLBACK_KEY].observe_unmodulated_context_v1(
        {"kind": "MANUALFILLNEEDEDSTEP"}
    )
    assert contexts_seen == [{"kind": "MANUALFILLNEEDEDSTEP"}]

    controller = {
        "kind": "controller_loop_event_v1",
        "name": "controller.loop.end",
        "phase": "end",
        "event_seq": 5,
    }
    prepared[CONTROLLER_EVENTS_CALLBACK_KEY](controller)
    assert controller_seen == [controller]


def test_run_from_here_live_callback_adapter_is_idempotent():
    seen: list[dict] = []

    prepared_once = _threaded_callbacks_for_live_delivery_v1(
        {EXPLOSION_EVENTS_CALLBACK_KEY: seen.append}
    )
    prepared_twice = _threaded_callbacks_for_live_delivery_v1(prepared_once)

    assert prepared_once is not None
    assert prepared_twice is not None
    assert (
        prepared_once[EXPLOSION_EVENTS_CALLBACK_KEY]
        is prepared_twice[EXPLOSION_EVENTS_CALLBACK_KEY]
    )

    prepared_twice[EXPLOSION_EVENTS_CALLBACK_KEY](_canonical_datum_message())
    assert len(seen) == 1
    assert "event_seq" not in seen[0]
