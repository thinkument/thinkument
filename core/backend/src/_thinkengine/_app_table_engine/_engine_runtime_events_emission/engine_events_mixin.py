from __future__ import annotations

"""
Session event runtime machinery.

This module owns the canonical bounded session event queue plus transient
callback delivery:

- synchronous process-wide callback delivery;
- per-dispatch callback delivery;
- per-session canonical bounded queue ownership;
- generic controller/datum/external live event queueing;
- external/artificial event emission;
- engine-facing drain/emit methods.

Packet construction and packet validation live in the public event packet sheet:

    _thinksessions.run.runme_surfaces_out.__engine_event_packet

Canonical delivery law
----------------------

The concrete engine delivery path is deliberately sink-first:

    source packet
        -> canonical session sink assigns event_seq
        -> sink returns the canonical queued packet
        -> per-dispatch callback, else process callback

That ordering gives live epsilon observers the exact session-local canonical
sequence without a callback-time engine read. The producer's source packet is
not mutated; queue sequencing remains owned by the canonical sink.

A custom sink may return ``None`` for backward compatibility. In that weaker
case callback delivery falls back to the source packet. Contracts that require a
canonical sequence must reject such an unsequenced callback packet.

The canonical bounded queue is durable through the engine snapshot. It is not
written into engine.state, outputs, datum lifecycle rows, or the runtime write
index. Callback functions and callback receiver state remain transient.
"""

from typing import Any, Callable, Dict, List, Mapping, Optional

from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    Q_SIGNAL_FILL,
    SESSION_EVENT_KIND_V1,
    build_session_event,
)


SESSION_EVENT_QUEUE_MAXLEN_V1 = 32
SESSION_EVENT_SEQ_KEY_V1 = "event_seq"
SessionEventSink = Callable[
    [Mapping[str, Any]],
    Optional[Mapping[str, Any]],
]
SessionEventCallback = Callable[[Mapping[str, Any]], None]


def _noop_session_event_callback(
    _event: Mapping[str, Any],
) -> None:
    return None


_SESSION_EVENT_CALLBACK: SessionEventCallback = (
    _noop_session_event_callback
)


def set_session_event_callback(
    fn: Optional[SessionEventCallback],
) -> None:
    """
    Install the process-wide live event callback.

    Passing None restores the default no-op callback.

    Delivery order is:

        canonical session sink first
        per-dispatch callback second, when supplied
        otherwise process callback second

    On the concrete sink path the callback packet is the sink-returned canonical
    packet and therefore carries ``event_seq``. That order is intentional: a
    callback failure cannot silently erase the already-recorded event from the
    session-local queue.
    """
    global _SESSION_EVENT_CALLBACK
    _SESSION_EVENT_CALLBACK = (
        fn
        if callable(fn)
        else _noop_session_event_callback
    )


def deliver_session_event(
    event: Mapping[str, Any],
    *,
    event_sink: Optional[SessionEventSink],
    event_callback: Optional[SessionEventCallback] = None,
) -> None:
    """
    Deliver one already-built source session event packet.

    The sink is authoritative for canonical queue sequencing. When it returns a
    mapping, that mapping is the exact packet delivered to the callback and may
    therefore include queue-owned fields such as ``event_seq``. When a legacy or
    custom sink returns ``None``, callback delivery falls back to the unsequenced
    source copy.

    The source packet supplied by the producer is never mutated here.

    A per-dispatch ``event_callback`` is preferred when supplied. This keeps
    dispatch-scoped observers isolated from the legacy process-wide callback.
    """
    source_event = dict(event)
    callback_event = source_event

    if callable(event_sink):
        canonical = event_sink(source_event)
        if isinstance(canonical, Mapping):
            callback_event = dict(canonical)

    if callable(event_callback):
        event_callback(callback_event)
        return

    _SESSION_EVENT_CALLBACK(callback_event)


def emit_external_session_event(
    *,
    form_id: str,
    frame_id: str,
    span_id: str,
    datum_id: str,
    payload: Any = None,
    name: str = "datum.external",
    event_sink: Optional[SessionEventSink] = None,
    event_callback: Optional[SessionEventCallback] = None,
) -> Dict[str, Any]:
    """
    Build and deliver a general external event onto a live session.

    This is the engine-side primitive for artificial/server/frontend/webhook
    style emissions. The caller must provide explicit session addressing.

    The return value remains the builder/source packet for compatibility.
    Concrete live callbacks may receive the queue-canonicalized copy with
    ``event_seq`` according to ``deliver_session_event``.
    """
    ev = build_session_event(
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        datum_id=datum_id,
        signal_kind="external",
        name=name,
        payload=payload,
        source="external",
    )
    deliver_session_event(
        ev,
        event_sink=event_sink,
        event_callback=event_callback,
    )
    return ev


class SessionEventsMixin:
    """
    Canonical bounded session event queue and engine-facing event methods.

    Durable snapshot fields owned by this mixin:
      - _session_events_v1
      - _next_session_event_seq_v1

    Compatibility:
      - older live instances using ``_transient_events_v1`` are adopted;
      - older snapshots without queue fields restore an empty queue at seq 1.
    """

    def _init_session_events_runtime_state_v1(self) -> None:
        self._session_events_v1: List[Dict[str, Any]] = []
        self._next_session_event_seq_v1 = 1

    def _session_event_queue_maxlen_v1(self) -> int:
        policy_getter = getattr(
            self,
            "_session_storage_policy_v1",
            None,
        )
        if callable(policy_getter):
            try:
                policy = policy_getter()
                return max(
                    0,
                    int(
                        dict(policy or {}).get(
                            "events_snapshot_window",
                            SESSION_EVENT_QUEUE_MAXLEN_V1,
                        )
                        or 0
                    ),
                )
            except Exception:
                pass
        return SESSION_EVENT_QUEUE_MAXLEN_V1

    def _ensure_session_events_runtime_state_v1(self) -> None:
        events = getattr(self, "_session_events_v1", None)
        if not isinstance(events, list):
            legacy = getattr(self, "_transient_events_v1", None)
            events = list(legacy) if isinstance(legacy, list) else []
            self._session_events_v1 = [
                dict(event)
                for event in events
                if isinstance(event, Mapping)
            ]

        next_seq = getattr(self, "_next_session_event_seq_v1", None)
        try:
            next_seq_int = int(next_seq)
        except Exception:
            next_seq_int = 0

        retained_max = max(
            (
                int(event.get(SESSION_EVENT_SEQ_KEY_V1) or 0)
                for event in self._session_events_v1
                if isinstance(event, Mapping)
            ),
            default=0,
        )
        self._next_session_event_seq_v1 = max(
            1,
            next_seq_int,
            retained_max + 1,
        )

        cap = self._session_event_queue_maxlen_v1()
        if cap <= 0:
            self._session_events_v1.clear()
        elif len(self._session_events_v1) > cap:
            del self._session_events_v1[:-cap]

    def latest_session_event_seq_v1(self) -> int:
        """
        Return the latest canonical sequence assigned in this session.

        This is O(1) and independent of retained event payload size and queue
        length. Sequence zero means that no event has ever been recorded.

        ``event_seq`` is a strict total order only inside one session. It is not
        a wall-clock value and is not comparable across sessions.
        """
        self._ensure_session_events_runtime_state_v1()
        return max(0, int(self._next_session_event_seq_v1) - 1)

    def _emit_datum_event_to_engine_session(
        self,
        event: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """
        Engine-local canonical event sink.

        The returned mapping is the exact queue-canonicalized copy, including
        its assigned ``event_seq``. ``deliver_session_event`` uses this return
        value for callback delivery, which keeps sequence authority in one place
        and avoids callback-time reads.

        This event remains intentionally isolated from:
        - state;
        - runtime write index;
        - outputs.
        """
        return self.record_event_to_engine_session(event)

    def record_event_to_engine_session(
        self,
        event: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """
        Append one already-built packet to the canonical bounded queue.

        ``event_seq`` is assigned here and nowhere else. Producer-supplied
        ``event_seq`` values are ignored so canonical order cannot be forged,
        duplicated, or moved backwards.

        The input mapping is copied and not mutated. The returned mapping is a
        copy of the exact canonical queue packet and is therefore safe for the
        sink-first callback membrane to publish to live observers.
        """
        self._ensure_session_events_runtime_state_v1()

        ev = dict(event)
        seq = int(self._next_session_event_seq_v1)
        ev[SESSION_EVENT_SEQ_KEY_V1] = seq
        self._next_session_event_seq_v1 = seq + 1
        self._session_events_v1.append(ev)

        cap = self._session_event_queue_maxlen_v1()
        overflow = len(self._session_events_v1) - cap
        if overflow > 0:
            del self._session_events_v1[:overflow]
        elif cap <= 0:
            self._session_events_v1.clear()

        # Optional runtime-only persistence hook installed by the concrete
        # session API. It persists only the scalar high-water mark and is never
        # serialized into the engine snapshot.
        on_advanced = getattr(
            self,
            "_session_event_seq_advanced_callback_v1",
            None,
        )
        if callable(on_advanced):
            on_advanced(seq)

        return dict(ev)

    def peek_events_from_session(
        self,
        *,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Non-destructively view this session's transient event queue.

        limit=None returns the whole bounded queue.
        limit=k returns the latest k events.
        limit<=0 returns an empty list.
        """
        self._ensure_session_events_runtime_state_v1()

        events = list(
            getattr(self, "_session_events_v1", []) or []
        )

        if limit is None:
            return [dict(event) for event in events]

        try:
            k = int(limit)
        except Exception:
            raise TypeError("session event queue limit must be an integer or None")

        if k <= 0:
            return []

        return [dict(event) for event in events[-k:]]

    def drain_events_from_session(self) -> List[Dict[str, Any]]:
        """
        Destructively drain this session's transient event queue.
        """
        self._ensure_session_events_runtime_state_v1()

        events = list(
            getattr(self, "_session_events_v1", []) or []
        )
        try:
            self._session_events_v1.clear()
        except Exception:
            self._session_events_v1 = []
        return events

    def emit_datum_event_to_engine_session(
        self,
        *,
        form_id: str,
        frame_id: str,
        span_id: str,
        datum_id: str,
        payload: Any = None,
        name: str = "datum.external",
        event_callback: Optional[SessionEventCallback] = None,
    ) -> Dict[str, Any]:
        """
        Emit a general event onto this live engine session.

        Despite the historical method name, this is not limited to datum
        explosions. Any caller with explicit form/frame/span/datum addressing
        may use this path.
        """
        self._ensure_session_events_runtime_state_v1()

        return emit_external_session_event(
            form_id=form_id,
            frame_id=frame_id,
            span_id=span_id,
            datum_id=datum_id,
            payload=payload,
            name=name,
            event_sink=self._emit_datum_event_to_engine_session,
            event_callback=event_callback,
        )


__all__ = [
    "Q_SIGNAL_FILL",
    "SESSION_EVENT_KIND_V1",
    "SESSION_EVENT_QUEUE_MAXLEN_V1",
    "SESSION_EVENT_SEQ_KEY_V1",
    "SessionEventCallback",
    "SessionEventSink",
    "SessionEventsMixin",
    "build_session_event",
    "deliver_session_event",
    "emit_external_session_event",
    "set_session_event_callback",
]
