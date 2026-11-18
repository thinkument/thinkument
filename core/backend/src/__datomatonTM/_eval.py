from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional

from _thinkengine._app_table_engine._engine_runtime_events_emission.engine_events_mixin import (
    SessionEventSink,
)

from ._commons_api import (
    read_datum_system_flags_limits,
    resolve_datum_widget_v1,
)

from ._contract_runtime import (
    ensure_widget_input_contract_v1,
    normalize_q_result_v1,
)

from ._events import (
    deliver_result_events_v1,
    make_widget_emit_v1,
)

from ._globals import (
    Q_SIGNAL_FILL,
    Q_SIGNAL_MOUNT,
    Q_STATUS_BLOCKED,
    Q_STATUS_DONE,
    Q_STATUS_REEXPLODE,
)

from ._surface_specs import (
    DatumQEvalV1,
)


def _build_q_input_dead_v1(
    *,
    form_id: str,
    frame_id: str,
    span_id: str,
    datum_id: str,
    datum: Mapping[str, Any],
    raw_fill: Any,
    partial_fill: Any,
    prefill: Any,
    row: Mapping[str, Any],
    policy: Mapping[str, Any],
    structurally_satisfied: bool,
    re_count: int,
    signal_kind_norm: str,
    signal_info_norm: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "form_id": str(form_id),
        "frame_id": str(frame_id),
        "span_id": str(span_id),
        "datum_id": str(datum_id),
        "datum": dict(datum),
        "raw_fill": raw_fill,
        "partial_fill": partial_fill,
        "prefill": prefill,
        "state": dict(row.get("state") or {}),
        "messages": [
            dict(x)
            for x in list(row.get("messages") or [])
            if isinstance(x, Mapping)
        ],
        "proc_notes": [
            dict(x)
            for x in list(row.get("proc_notes") or [])
            if isinstance(x, Mapping)
        ],
        "structurally_satisfied": bool(structurally_satisfied),
        "reexplode_count": re_count,
        "max_reexplosions": int(policy["max_reexplosions"]),
        "max_proc_notes": int(policy["max_proc_notes"]),
        "max_messages": int(policy["max_messages"]),
        "signal": {
            "kind": signal_kind_norm,
            "info": dict(signal_info_norm),
        },
        "signal_kind": signal_kind_norm,
        "signal_info": dict(signal_info_norm),
        "ctx": {
            "attempt": re_count + 1,
            "is_revisit": re_count > 0,
            "signal_kind": signal_kind_norm,
            "is_mount": signal_kind_norm == Q_SIGNAL_MOUNT,
            "has_controller_signal": signal_kind_norm not in {
                Q_SIGNAL_FILL,
                Q_SIGNAL_MOUNT,
            },
        },
    }


def explode_datum_widget(
    *,
    state: Dict[str, Any],
    form_id: str,
    frame_id: str,
    span_id: str,
    datum_id: str,
    datum: Mapping[str, Any],
    raw_fill: Any,
    partial_fill: Any,
    prefill: Any,
    structurally_satisfied: bool,
    signal_kind: str = Q_SIGNAL_FILL,
    signal_info: Optional[Mapping[str, Any]] = None,
    event_sink: Optional[SessionEventSink] = None,
    event_callback: Optional[Callable[[Mapping[str, Any]], None]] = None,
) -> DatumQEvalV1:
    from _thinkengine._app_table_engine._engine_manual_io_and_memory_pages.engine_forms_as_memory_pages.api_engine_memory_form_pages import (
        _datum_row_v1,
        _form_row_v1,
        ensure_datum_lifecycle_store_v1,
    )

    store = ensure_datum_lifecycle_store_v1(state)
    form_row = _form_row_v1(store, form_id)
    row = _datum_row_v1(form_row, datum_id, datum)

    policy = read_datum_system_flags_limits(datum)
    max_re = int(policy["max_reexplosions"])
    re_count = int(row.get("reexplode_count", 0) or 0)
    signal_kind_norm = (
        str(signal_kind or Q_SIGNAL_FILL).strip()
        or Q_SIGNAL_FILL
    )
    signal_info_norm = (
        dict(signal_info or {})
        if isinstance(signal_info, Mapping)
        else {}
    )

    emitted_events: List[Dict[str, Any]] = []

    q_input_dead = _build_q_input_dead_v1(
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        datum_id=datum_id,
        datum=datum,
        raw_fill=raw_fill,
        partial_fill=partial_fill,
        prefill=prefill,
        row=row,
        policy=policy,
        structurally_satisfied=structurally_satisfied,
        re_count=re_count,
        signal_kind_norm=signal_kind_norm,
        signal_info_norm=signal_info_norm,
    )

    q_input = ensure_widget_input_contract_v1(q_input_dead)
    q_input["emit"] = make_widget_emit_v1(
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        datum_id=datum_id,
        signal_kind=signal_kind_norm,
        emitted_events=emitted_events,
        event_sink=event_sink,
        event_callback=event_callback,
    )

    widget = resolve_datum_widget_v1(policy["widget"])
    raw_result = widget(q_input)
    result = normalize_q_result_v1(raw_result)

    deliver_result_events_v1(
        raw_events=result.get("events"),
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        datum_id=datum_id,
        signal_kind=signal_kind_norm,
        emitted_events=emitted_events,
        event_sink=event_sink,
        event_callback=event_callback,
    )

    status = str(result["status"])
    msg = dict(result["message"])
    msgs = tuple(
        dict(x)
        for x in list(result.get("messages") or [])
        if isinstance(x, Mapping)
    )
    next_state = dict(result["state"])

    if status == Q_STATUS_REEXPLODE:
        if re_count >= max_re:
            if not bool(policy.get("exhausted_means_satisfied", True)):
                exhausted_msg = {
                    "level": "error",
                    "text": (
                        f"maximum reexplosions reached for datum {datum_id}; "
                        "datum remains unsatisfied"
                    ),
                }
                return DatumQEvalV1(
                    datum_id=str(datum_id),
                    status=Q_STATUS_BLOCKED,
                    message=exhausted_msg,
                    state=next_state,
                    messages=(dict(exhausted_msg),),
                    working_fill=partial_fill,
                    has_working_fill=True,
                    forced_done=False,
                    signal_kind=signal_kind_norm,
                    signal_info=signal_info_norm,
                    emitted_events=tuple(emitted_events or ()),
                )

            exhausted_msg = {
                "level": "warning",
                "text": (
                    f"maximum reexplosions reached for datum {datum_id}; "
                    "forcing satisfied"
                ),
            }
            return DatumQEvalV1(
                datum_id=str(datum_id),
                status=Q_STATUS_DONE,
                message=exhausted_msg,
                state=next_state,
                messages=(dict(exhausted_msg),),
                working_fill=partial_fill,
                has_working_fill=True,
                forced_done=True,
                signal_kind=signal_kind_norm,
                signal_info=signal_info_norm,
                emitted_events=tuple(emitted_events or ()),
            )

        return DatumQEvalV1(
            datum_id=str(datum_id),
            status=status,
            message=msg,
            state=next_state,
            messages=msgs,
            reexplode_datum=dict(result["datum"]),
            working_fill=result.get("fill"),
            has_working_fill=("fill" in result),
            working_prefill=result.get("prefill"),
            has_working_prefill=("prefill" in result),
            proc_notes=(
                dict(result.get("proc_notes") or {})
                if isinstance(result.get("proc_notes"), Mapping)
                else None
            ),
            signal_kind=signal_kind_norm,
            signal_info=signal_info_norm,
            emitted_events=tuple(emitted_events or ()),
        )

    return DatumQEvalV1(
        datum_id=str(datum_id),
        status=status,
        message=msg,
        state=next_state,
        messages=msgs,
        working_fill=partial_fill,
        has_working_fill=True,
        signal_kind=signal_kind_norm,
        signal_info=signal_info_norm,
        emitted_events=tuple(emitted_events or ()),
    )


__all__ = [
    "explode_datum_widget",
]