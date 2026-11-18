# think-backend/src/thinkengine/_engine/app_table_engine/engine/_engine_runtime_events_emission/__engine_event_packets.py

from __future__ import annotations

"""
Session event packet v1.

This file is the permanent compact reference for the live session event packet.

A session event is a dead-JSON packet emitted onto exactly one live engine
session. It is general-purpose:

- a datum lifecycle widget may emit one while evaluating fill/mount/reexplode;
- a widget may return event declarations that become packets;
- an external caller may emit one explicitly, for example from a webhook,
  frontend action, integration bridge, or server-side orchestration hook.

Packet law
----------

A datum/session event has three closely-related representations:

1. the source packet built by ``build_session_event(...)``;
2. the canonical queued packet produced when the concrete session event sink
   records that source packet and assigns ``event_seq``;
3. a live/provisional callback copy produced with
   ``provisional_event_copy_v1(...)``.

Only the canonical queue owns ``event_seq``.  The live/provisional callback
surface deliberately does not.  A hosting/runtime layer may internally record
an event before invoking its per-dispatch callback, but the callback contract
still exposes a source-shaped copy with ``event_seq`` removed.  This preserves
one clean distinction:

- epsilon/live delivery says "this happened now" and is not a canonical cursor;
- theta/canonical polling says "this was committed at event_seq N".

The highest ``run_from_here`` façade enforces this live/provisional projection
for datum explosion callbacks.  Direct lower-engine integrations that expose a
live/provisional callback should use the same helper rather than forwarding the
canonical queued packet verbatim.

A custom delivery path with no canonical sink may naturally callback-deliver an
unsequenced source packet. Higher contracts that require canonical ordering must
read the canonical queue instead of treating callback delivery as a queue
cursor.

Session event packets are:

- drainable;
- session-local;
- JSON-compatible;
- retained in a bounded canonical queue that is durable through snapshots.

Role-aware release law
----------------------

Datum lifecycle packets are atomic visibility vectors. A named viewer receives
the entire canonical packet iff that viewer can read ``datum_id``; otherwise
the packet is omitted. The packet is never field-redacted. Controller-loop
packets use their own U/A projection law in the controller event surface.

They are not written to:

- engine.state;
- outputs;
- datum lifecycle rows;
- runtime write indexes.

The canonical queue copy receives ``event_seq`` when it is recorded. The
builder output and live/provisional callback copy do not.

Canonical source packet shape
-----------------------------

    {
        "kind": "datum_lifecycle_event_v1",
        "event_id": str,
        "emitted_at": str,
        "source": str,
        "name": str,
        "form_id": str,
        "frame_id": str,
        "span_id": str,
        "datum_id": str,
        "signal_kind": str,
        "payload": dict,
    }

The canonical queued form adds:

    "event_seq": positive session-local integer

The live/provisional callback form is a defensive deep copy of the event with
``event_seq`` absent, regardless of whether the input happened to be source or
canonical form.

Payload normalization
---------------------

Payloads are normalized into a mapping:

    None          -> {}
    Mapping       -> dict(payload)
    any other     -> {"value": payload}

The normalized payload and final packet must pass dead-JSON validation.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping
from uuid import uuid4

from _thinkprogram._iomicrosTM.tiny_helpers import (
    DeadJSONError,
    _utc_now_iso_v1,
    assert_dead_json,
)
from __exceptions.engine import (
    DatumLifecycleContractError,
)

EXPLOSION_EVENTS_CALLBACK_KEY = "explosion_events_callback"

CONTROLLER_EVENTS_CALLBACK_KEY = "controller_events_callback"

Q_SIGNAL_FILL = "fill"

SESSION_EVENT_KIND_V1 = "datum_lifecycle_event_v1"

SESSION_EVENT_SOURCES_V1 = {
    "datum_widget",
    "datum_widget_result",
    "external",
}

SESSION_EVENT_REQUIRED_KEYS_V1 = (
    "kind",
    "event_id",
    "emitted_at",
    "source",
    "name",
    "form_id",
    "frame_id",
    "span_id",
    "datum_id",
    "signal_kind",
    "payload",
)

SESSION_EVENT_PACKET_SHAPE_V1 = {
    "kind": SESSION_EVENT_KIND_V1,
    "event_id": "str uuid",
    "emitted_at": "str utc iso timestamp",
    "source": "datum_widget | datum_widget_result | external | str",
    "name": "str",
    "form_id": "str",
    "frame_id": "str",
    "span_id": "str",
    "datum_id": "str",
    "signal_kind": "fill | mount | external | str",
    "payload": "dict dead-json",
}


def session_event_packet_shape_v1() -> Dict[str, Any]:
    """
    Return a copy of the public source session-event packet shape.

    This is intentionally documentation-as-data. It is safe for docs/tests/UI
    tooling to import. The canonical queue augments this source shape with a
    positive ``event_seq`` at record time.

    This object is not used as the runtime validator; runtime validation remains
    build_session_event + assert_dead_json.
    """
    return dict(SESSION_EVENT_PACKET_SHAPE_V1)


def provisional_event_copy_v1(
    event: Mapping[str, Any],
) -> Dict[str, Any]:
    """Return the non-canonical copy suitable for live/provisional delivery.

    ``event_seq`` is queue ownership metadata.  A callback that is meant to be
    heard while a dispatch is still in flight must never expose that field as
    though the callback itself were a canonical queue page.

    A deep copy is intentional: callers may inspect or locally transform the
    live packet without gaining a mutation path back into a canonical queued
    event object supplied by a lower runtime.
    """
    if not isinstance(event, Mapping):
        raise TypeError("provisional live event must be a mapping")

    out = deepcopy(dict(event))
    out.pop("event_seq", None)
    return out


def normalize_session_event_payload_v1(
    payload: Any,
) -> Dict[str, Any]:
    """
    Normalize and validate a session event payload.

    This function is intentionally the only payload-shape gate for session
    events. Event producers can send any dead-JSON-compatible structure; scalars
    and lists are wrapped under ``value`` so the packet payload is always a
    mapping.
    """
    if payload is None:
        payload = {}

    if not isinstance(payload, Mapping):
        payload = {
            "value": payload,
        }

    out = dict(payload)
    try:
        assert_dead_json(
            out,
            path="session_event.payload",
        )
    except DeadJSONError as exc:
        raise DatumLifecycleContractError(str(exc)) from exc

    return out


def build_session_event(
    *,
    form_id: str,
    frame_id: str,
    span_id: str,
    datum_id: str,
    signal_kind: str,
    name: str = "datum.event",
    payload: Any = None,
    source: str = "datum_widget",
) -> Dict[str, Any]:
    """
    Build the canonical source live-session event packet.

    This does not enqueue, drain, persist, assign ``event_seq``, or callback-
    deliver anything. Queue sequencing belongs solely to the concrete session
    event sink.
    """
    payload_norm = normalize_session_event_payload_v1(payload)

    ev = {
        "kind": SESSION_EVENT_KIND_V1,
        "event_id": str(uuid4()),
        "emitted_at": _utc_now_iso_v1(),
        "source": str(source or "datum_widget"),
        "name": str(name or "datum.event"),
        "form_id": str(form_id),
        "frame_id": str(frame_id),
        "span_id": str(span_id),
        "datum_id": str(datum_id),
        "signal_kind": str(signal_kind or Q_SIGNAL_FILL),
        "payload": payload_norm,
    }

    try:
        assert_dead_json(
            ev,
            path="session_event",
        )
    except DeadJSONError as exc:
        raise DatumLifecycleContractError(str(exc)) from exc

    return ev


__all__ = [
    "CONTROLLER_EVENTS_CALLBACK_KEY",
    "EXPLOSION_EVENTS_CALLBACK_KEY",
    "Q_SIGNAL_FILL",
    "SESSION_EVENT_KIND_V1",
    "SESSION_EVENT_PACKET_SHAPE_V1",
    "SESSION_EVENT_REQUIRED_KEYS_V1",
    "SESSION_EVENT_SOURCES_V1",
    "build_session_event",
    "normalize_session_event_payload_v1",
    "provisional_event_copy_v1",
    "session_event_packet_shape_v1",
]
