from __future__ import annotations

from typing import Any, Dict, List, Mapping


# global imports

from __datomatonTM import (
    DATUM_LIFECYCLE_STATUS_BLOCKED,
    DATUM_LIFECYCLE_STATUS_DONE,
    DATUM_LIFECYCLE_STATUS_FORCED_DONE,
    DATUM_LIFECYCLE_STATUS_REEXPLODED,
    DEFAULT_MAX_BAGGAGE_V1,
    DEFAULT_MAX_MESSAGES_V1,
    Q_SIGNAL_MOUNT,
    Q_STATUS_BLOCKED,
    Q_STATUS_DONE,
    Q_STATUS_REEXPLODE,
)

from __datomatonTM import (
    _eval_messages_v1,
)

from __datomatonTM import (
    read_datum_system_flags_limits,
)

from __multiframespecTM.api import (
    span_key_v1
)

from __datomatonTM import (
    DatumQEvalV1,
)


# local imports

from ._create_new_form_page_rows import (
    _datum_row_v1,
    _form_row_v1,
    ensure_datum_lifecycle_store_v1,
)

from ._undo_form_page_changes import (
    _make_lifecycle_incremental_undo_v1,
)


def apply_q_reexplode_batch_v1(
    *,
    state: Dict[str, Any],
    form_id: str,
    frame_id: str,
    span_id: str,
    evaluations: List[DatumQEvalV1],
    working_fills: Mapping[str, Any],
) -> Dict[str, Any]:
    touched_ids = [
        str(ev.datum_id)
        for ev in list(evaluations or [])
    ]
    undo = _make_lifecycle_incremental_undo_v1(
        state=state,
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        datum_ids=touched_ids,
    )

    store = ensure_datum_lifecycle_store_v1(state)
    form_row = _form_row_v1(store, form_id)
    form_row["epoch"] = int(form_row.get("epoch", 0) or 0) + 1
    form_row["structural_epoch"] = (
        int(form_row.get("structural_epoch", 0) or 0) + 1
    )

    sk = span_key_v1(frame_id, span_id)

    wf_root = form_row.setdefault("working_fills_by_span", {})
    wf = dict(wf_root.get(sk) or {})
    wf.update(
        {
            str(k): v
            for k, v in dict(working_fills or {}).items()
        }
    )

    wp_root = form_row.setdefault("working_prefills_by_span", {})
    wp = dict(wp_root.get(sk) or {})

    for ev in evaluations:
        row = _datum_row_v1(
            form_row,
            ev.datum_id,
            ev.reexplode_datum or {"id": ev.datum_id},
        )
        row["epoch"] = int(row.get("epoch", 0) or 0) + 1
        row["state"] = dict(ev.state)
        row["status"] = DATUM_LIFECYCLE_STATUS_REEXPLODED

        if ev.reexplode_datum is not None:
            row["current_datum"] = dict(ev.reexplode_datum)

        row["reexplode_count"] = (
            int(row.get("reexplode_count", 0) or 0) + 1
        )

        effective_datum = (
            ev.reexplode_datum
            or row.get("current_datum")
            or {"id": ev.datum_id}
        )
        policy = read_datum_system_flags_limits(
            effective_datum
            if isinstance(effective_datum, Mapping)
            else {}
        )

        max_messages = int(
            policy.get("max_messages", DEFAULT_MAX_MESSAGES_V1)
            or 0
        )
        messages = list(row.get("messages") or [])
        for msg_item in _eval_messages_v1(ev):
            messages.append(dict(msg_item))
        row["messages"] = (
            messages[-max_messages:]
            if max_messages > 0
            else []
        )

        if ev.proc_notes is not None:
            max_proc_notes = int(
                policy.get("max_proc_notes", DEFAULT_MAX_BAGGAGE_V1)
                or 0
            )
            proc_notes = list(row.get("proc_notes") or [])
            proc_notes.append(dict(ev.proc_notes))
            row["proc_notes"] = (
                proc_notes[-max_proc_notes:]
                if max_proc_notes > 0
                else []
            )

        if ev.has_working_fill:
            wf[ev.datum_id] = ev.working_fill
        if ev.has_working_prefill:
            wp[ev.datum_id] = ev.working_prefill

    wf_root[sk] = wf
    if wp:
        wp_root[sk] = wp

    return undo


def apply_q_mount_batch_v1(
    *,
    state: Dict[str, Any],
    form_id: str,
    frame_id: str,
    span_id: str,
    evaluations: List[DatumQEvalV1],
    working_fills: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Commit mount-signal lifecycle evaluations.

    Mount is intentionally implemented as the first concrete generic signal:

        signal.kind == "mount"
        signal.info == {...}

    It can:
      - block and simply mark the span mounted with a message/state;
      - reexplode and replace the effective datum surface before first render;
      - complete and mark the datum satisfied.

    The mounted mark is span-local so respanned datums can mount again later.
    """
    evals = list(evaluations or [])
    touched_ids = [
        str(ev.datum_id)
        for ev in evals
    ]

    undo = _make_lifecycle_incremental_undo_v1(
        state=state,
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        datum_ids=touched_ids,
    )

    if not evals:
        return undo

    store = ensure_datum_lifecycle_store_v1(state)
    form_row = _form_row_v1(store, form_id)
    form_row["epoch"] = int(form_row.get("epoch", 0) or 0) + 1

    sk = span_key_v1(frame_id, span_id)
    structural_changed = False

    wf_root = form_row.setdefault("working_fills_by_span", {})
    wf = dict(wf_root.get(sk) or {})
    wf.update(
        {
            str(k): v
            for k, v in dict(working_fills or {}).items()
        }
    )

    wp_root = form_row.setdefault("working_prefills_by_span", {})
    wp = dict(wp_root.get(sk) or {})

    for ev in evals:
        effective_datum = ev.reexplode_datum or {"id": ev.datum_id}
        row = _datum_row_v1(
            form_row,
            ev.datum_id,
            effective_datum,
        )

        row["epoch"] = int(row.get("epoch", 0) or 0) + 1
        row["state"] = dict(ev.state)
        row["forced_done"] = bool(ev.forced_done)

        mounted = row.setdefault("spans_mounted_on", {})
        if isinstance(mounted, dict):
            mounted[sk] = {
                "frame_id": str(frame_id),
                "span_id": str(span_id),
                "signal_kind": str(ev.signal_kind or Q_SIGNAL_MOUNT),
                "signal_info": dict(ev.signal_info or {}),
                "epoch": int(row.get("epoch", 0) or 0),
            }

        if ev.status == Q_STATUS_REEXPLODE:
            row["status"] = DATUM_LIFECYCLE_STATUS_REEXPLODED
            if ev.reexplode_datum is not None:
                row["current_datum"] = dict(ev.reexplode_datum)

            row["reexplode_count"] = (
                int(row.get("reexplode_count", 0) or 0) + 1
            )
            structural_changed = True

            if ev.has_working_fill:
                wf[ev.datum_id] = ev.working_fill
            if ev.has_working_prefill:
                wp[ev.datum_id] = ev.working_prefill

        elif ev.status == Q_STATUS_DONE:
            row["status"] = (
                DATUM_LIFECYCLE_STATUS_FORCED_DONE
                if ev.forced_done
                else DATUM_LIFECYCLE_STATUS_DONE
            )
            if ev.has_working_fill:
                wf[ev.datum_id] = ev.working_fill

        elif ev.status == Q_STATUS_BLOCKED:
            row["status"] = DATUM_LIFECYCLE_STATUS_BLOCKED
            if ev.has_working_fill:
                wf[ev.datum_id] = ev.working_fill

        effective_datum2 = row.get("current_datum")
        if not isinstance(effective_datum2, Mapping):
            effective_datum2 = effective_datum

        policy = read_datum_system_flags_limits(
            effective_datum2
            if isinstance(effective_datum2, Mapping)
            else {}
        )

        max_messages = int(
            policy.get("max_messages", DEFAULT_MAX_MESSAGES_V1)
            or 0
        )
        messages = list(row.get("messages") or [])
        for msg_item in _eval_messages_v1(ev):
            if msg_item.get("text"):
                messages.append(dict(msg_item))
        row["messages"] = (
            messages[-max_messages:]
            if max_messages > 0
            else []
        )

        if ev.proc_notes is not None:
            max_proc_notes = int(
                policy.get("max_proc_notes", DEFAULT_MAX_BAGGAGE_V1)
                or 0
            )
            proc_notes = list(row.get("proc_notes") or [])
            proc_notes.append(dict(ev.proc_notes))
            row["proc_notes"] = (
                proc_notes[-max_proc_notes:]
                if max_proc_notes > 0
                else []
            )

    if structural_changed:
        form_row["structural_epoch"] = (
            int(form_row.get("structural_epoch", 0) or 0) + 1
        )

    if wf:
        wf_root[sk] = wf
    if wp:
        wp_root[sk] = wp

    return undo


def apply_q_done_batch_v1(
    *,
    state: Dict[str, Any],
    form_id: str,
    frame_id: str,
    span_id: str,
    evaluations: List[DatumQEvalV1],
) -> Dict[str, Any]:
    evals = list(evaluations or [])
    touched_ids = [
        str(ev.datum_id)
        for ev in evals
    ]

    undo = _make_lifecycle_incremental_undo_v1(
        state=state,
        form_id=form_id,
        frame_id=frame_id,
        span_id=span_id,
        datum_ids=touched_ids,
    )

    store = ensure_datum_lifecycle_store_v1(state)
    form_row = _form_row_v1(store, form_id)
    form_row["epoch"] = int(form_row.get("epoch", 0) or 0) + 1

    for ev in evals:
        row = _datum_row_v1(
            form_row,
            ev.datum_id,
            {"id": ev.datum_id},
        )
        row["state"] = dict(ev.state)
        row["status"] = (
            DATUM_LIFECYCLE_STATUS_FORCED_DONE
            if ev.forced_done
            else DATUM_LIFECYCLE_STATUS_DONE
        )
        row["forced_done"] = bool(ev.forced_done)

        effective_datum = row.get("current_datum")
        if not isinstance(effective_datum, Mapping):
            effective_datum = {
                "id": ev.datum_id,
            }

        policy = read_datum_system_flags_limits(effective_datum)
        max_messages = int(
            policy.get("max_messages", DEFAULT_MAX_MESSAGES_V1)
            or 0
        )

        messages = list(row.get("messages") or [])
        for msg_item in _eval_messages_v1(ev):
            if msg_item.get("text"):
                messages.append(dict(msg_item))
        row["messages"] = (
            messages[-max_messages:]
            if max_messages > 0
            else []
        )

    sk = span_key_v1(frame_id, span_id)

    wf = form_row.get("working_fills_by_span")
    if isinstance(wf, dict):
        wf.pop(sk, None)

    wp = form_row.get("working_prefills_by_span")
    if isinstance(wp, dict):
        wp.pop(sk, None)

    return undo