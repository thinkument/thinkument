from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional

from __exceptions.engine import (
    DatumLifecycleContractError,
)

from _thinkengine._app_table_engine._engine_runtime_events_emission.engine_events_mixin import (
    SessionEventSink,
    build_session_event,
    deliver_session_event,
)

from _thinksessions.run.runme_surfaces_out.__renderer_agnostic_datomaton_specialized_message_event_payload import (
    ensure_renderer_agnostic_datomaton_specialized_message_event_payload_v1,
)


def _validated_datomaton_event_payload_v1(
    payload: Any,
    *,
    path: str,
) -> Any:
    try:
        return (
            ensure_renderer_agnostic_datomaton_specialized_message_event_payload_v1(
                payload
            )
        )
    except ValueError as exc:
        raise DatumLifecycleContractError(
            f"{path}: {exc}"
        ) from exc


def make_widget_emit_v1(
    *,
    form_id: str,
    frame_id: str,
    span_id: str,
    datum_id: str,
    signal_kind: str,
    emitted_events: List[Dict[str, Any]],
    event_sink: Optional[SessionEventSink],
    event_callback: Optional[Callable[[Mapping[str, Any]], None]] = None,
) -> Callable[..., Dict[str, Any]]:

    def _emit_from_widget_v1(
        payload: Any = None,
        *,
        name: str = "datum.event",
        record_in_session_queue: bool = True,
    ) -> Dict[str, Any]:
        payload_checked = _validated_datomaton_event_payload_v1(
            payload,
            path="datum widget emit payload",
        )

        ev = build_session_event(
            form_id=str(form_id),
            frame_id=str(frame_id),
            span_id=str(span_id),
            datum_id=str(datum_id),
            signal_kind=signal_kind,
            name=name,
            payload=payload_checked,
            source="datum_widget",
        )
        if record_in_session_queue:
            emitted_events.append(ev)
        deliver_session_event(
            ev,
            event_sink=event_sink if record_in_session_queue else None,
            event_callback=event_callback,
        )
        return dict(ev)

    return _emit_from_widget_v1


def deliver_result_events_v1(
    *,
    raw_events: Any,
    form_id: str,
    frame_id: str,
    span_id: str,
    datum_id: str,
    signal_kind: str,
    emitted_events: List[Dict[str, Any]],
    event_sink: Optional[SessionEventSink],
    event_callback: Optional[Callable[[Mapping[str, Any]], None]] = None,
) -> None:
    if not raw_events:
        return

    for event_index, raw_event in enumerate(list(raw_events)):
        if not isinstance(raw_event, Mapping):
            raise DatumLifecycleContractError(
                "datum widget result.events entries must be mappings"
            )

        payload_checked = _validated_datomaton_event_payload_v1(
            raw_event.get("payload"),
            path=(
                "datum widget result.events"
                f"[{event_index}].payload"
            ),
        )

        ev = build_session_event(
            form_id=str(form_id),
            frame_id=str(frame_id),
            span_id=str(span_id),
            datum_id=str(datum_id),
            signal_kind=signal_kind,
            name=str(raw_event.get("name") or "datum.event"),
            payload=payload_checked,
            source="datum_widget_result",
        )
        emitted_events.append(ev)
        deliver_session_event(
            ev,
            event_sink=event_sink,
            event_callback=event_callback,
        )


__all__ = [
    "make_widget_emit_v1",
    "deliver_result_events_v1",
]