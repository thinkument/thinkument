from __future__ import annotations

"""
Explicit bounded G* query machinery for the public session façade.

This file owns the compact developer-inspection surfaces:

- runtime_writes query normalization;
- script action summaries;
- manifest call rows;
- program_trace_table construction;
- topology/datum/Q trace row shaping.

It does not expose a public import surface. session_facade.py imports these
helpers and re-exports only the public façade.
"""

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import query_runtime_writes

from _thinkengine.runme_optimized_queryable._globals import (
    KIND_PROGRAM_TRACE_TABLE_V1,
    PublicSessionCaps,
)
from _thinkengine.runme_optimized_queryable._helpers import (
    _as_mapping,
    _bounded_int,
    _coerce_public_caps_v1,
)


def _normalize_runtime_write_query_v1(
    query: Mapping[str, Any],
    *,
    caps: Optional[PublicSessionCaps | Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    c = _coerce_public_caps_v1(caps)
    q = dict(query or {})

    q["max_results"] = _bounded_int(
        q.get("max_results"),
        default=c.default_query_max_results,
        upper=c.absolute_query_max_results,
    )
    q["include_values"] = bool(q.get("include_values", False))

    return q


def _normalize_trace_query_v1(
    query: Mapping[str, Any],
    *,
    caps: Optional[PublicSessionCaps | Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    c = _coerce_public_caps_v1(caps)
    q = dict(query or {})

    q["max_results"] = _bounded_int(
        q.get("max_results"),
        default=c.default_trace_max_results,
        upper=c.absolute_query_max_results,
    )

    q["include_fn_args"] = bool(q.get("include_fn_args", False))
    q["include_datum_values"] = bool(q.get("include_datum_values", False))
    q["include_q_lifecycle"] = bool(q.get("include_q_lifecycle", False))
    q["include_topology"] = bool(q.get("include_topology", True))

    return q


def _public_script_action_summary_v1(raw_history: Any) -> Dict[str, Any]:
    """
    Return bounded script-history metadata, never raw history rows.
    """
    if not isinstance(raw_history, Sequence) or isinstance(
        raw_history,
        (str, bytes, bytearray),
    ):
        return {
            "history_count": 0,
            "actions": {},
            "modes": {},
            "first_actions": [],
            "last_actions": [],
        }

    action_counts: dict[str, int] = {}
    mode_counts: dict[str, int] = {}
    action_names: list[str] = []

    for row in raw_history:
        if isinstance(row, Mapping):
            action = str(row.get("action") or "UNKNOWN")
            mode = str(row.get("mode") or "UNKNOWN")
        else:
            action = "UNKNOWN"
            mode = "UNKNOWN"

        action_counts[action] = action_counts.get(action, 0) + 1
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        action_names.append(action)

    return {
        "history_count": len(raw_history),
        "actions": dict(sorted(action_counts.items())),
        "modes": dict(sorted(mode_counts.items())),
        "first_actions": action_names[:8],
        "last_actions": action_names[-8:],
    }


def _compact_manifest_call_rows_v1(
    manifest: Any,
    *,
    include_fn_args: bool,
) -> list[Dict[str, Any]]:
    """
    Project an app-table manifest into compact app_call rows.
    """
    if not isinstance(manifest, Sequence) or isinstance(
        manifest,
        (str, bytes, bytearray),
    ):
        return []

    rows: list[Dict[str, Any]] = []

    for i, raw_call in enumerate(manifest):
        if not isinstance(raw_call, Mapping):
            continue

        row: Dict[str, Any] = {
            "row_kind": "app_call",
            "call_index": i,
            "public_step_name": raw_call.get("public_step_name"),
            "step_fn": raw_call.get("step_fn"),
        }

        if include_fn_args:
            row["fn_args"] = _as_mapping(raw_call.get("fn_args"))

        rows.append(row)

    return rows


def _looks_like_multiframespec_v1(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False

    has_form_id = bool(
        value.get("app_form_id")
        or value.get("form_id")
        or value.get("id")
    )
    has_frames = isinstance(value.get("frames"), Sequence) and not isinstance(
        value.get("frames"),
        (str, bytes, bytearray),
    )
    has_datums = isinstance(value.get("datums"), Sequence) and not isinstance(
        value.get("datums"),
        (str, bytes, bytearray),
    )

    return bool(has_form_id and has_frames and has_datums)


def _iter_multiframespecs_v1(
    root: Any,
    *,
    max_nodes: int = 20_000,
) -> Iterable[Mapping[str, Any]]:
    """
    Best-effort multiframespec discovery over raw outputs/snapshot/state.
    """
    stack = [root]
    seen: set[int] = set()
    visited = 0
    yielded: set[int] = set()

    while stack and visited < max_nodes:
        cur = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if _looks_like_multiframespec_v1(cur):
            if oid not in yielded:
                yielded.add(oid)
                yield cur

        if isinstance(cur, Mapping):
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)


def _micro_names_v1(value: Any) -> list[str]:
    """
    Extract micro names from a datum-like object or micros list.
    """
    if isinstance(value, Mapping):
        micros = value.get("micros")
    else:
        micros = value

    if not isinstance(micros, Sequence) or isinstance(micros, (str, bytes, bytearray)):
        return []

    out: list[str] = []
    for micro in micros:
        if isinstance(micro, Mapping):
            name = micro.get("name")
            if name is not None:
                out.append(str(name))
        elif isinstance(micro, str):
            out.append(micro)

    return out


def _multiframespec_topology_v1(
    multiframespecs: Iterable[Mapping[str, Any]],
) -> tuple[list[Dict[str, Any]], dict[str, Dict[str, Any]], dict[str, str], dict[str, str]]:
    """
    Convert discovered multiframespecs into compact topology rows.
    """
    rows: list[Dict[str, Any]] = []
    datum_defs: dict[str, Dict[str, Any]] = {}
    datum_to_span: dict[str, str] = {}
    span_to_form: dict[str, str] = {}
    seen_spans: set[tuple[str, str, str]] = set()

    for fs in multiframespecs:
        form_id = str(
            fs.get("app_form_id")
            or fs.get("form_id")
            or fs.get("id")
            or ""
        )

        datums = fs.get("datums")
        if isinstance(datums, Sequence) and not isinstance(datums, (str, bytes, bytearray)):
            for raw_datum in datums:
                if not isinstance(raw_datum, Mapping):
                    continue

                datum_id = raw_datum.get("id") or raw_datum.get("datum_id")
                if datum_id is None:
                    continue

                did = str(datum_id)
                datum_defs[did] = dict(raw_datum)

        frames = fs.get("frames")
        if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes, bytearray)):
            continue

        for frame in frames:
            if not isinstance(frame, Mapping):
                continue

            frame_id = str(frame.get("id") or frame.get("frame_id") or "")
            spans = frame.get("spans")

            if not isinstance(spans, Sequence) or isinstance(spans, (str, bytes, bytearray)):
                continue

            for span in spans:
                if not isinstance(span, Mapping):
                    continue

                span_id = str(span.get("id") or span.get("span_id") or "")
                owns = [
                    str(x)
                    for x in list(span.get("owns") or span.get("datum_ids") or [])
                ]

                key = (form_id, frame_id, span_id)
                if key in seen_spans:
                    continue
                seen_spans.add(key)

                for datum_id in owns:
                    datum_to_span[datum_id] = span_id
                if span_id:
                    span_to_form[span_id] = form_id

                rows.append(
                    {
                        "row_kind": "span",
                        "form_id": form_id,
                        "frame_id": frame_id,
                        "span_id": span_id,
                        "owns": owns,
                    }
                )

    return rows, datum_defs, datum_to_span, span_to_form


def _datum_io_rows_from_outputs_v1(
    outputs: Mapping[str, Any],
    *,
    include_values: bool,
    datum_to_span: Mapping[str, str],
) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []

    sources = [
        ("form_prefill", _as_mapping(outputs.get("form_prefills"))),
        ("form_fill", _as_mapping(outputs.get("form_fills"))),
    ]

    for write_kind, bucket in sources:
        for raw_datum_id in sorted(bucket.keys(), key=lambda x: str(x)):
            datum_id = str(raw_datum_id)
            row: Dict[str, Any] = {
                "row_kind": "datum_io",
                "datum_id": datum_id,
                "span_id": datum_to_span.get(datum_id),
                "write_kind": write_kind,
            }

            if include_values:
                row["value"] = bucket.get(raw_datum_id)

            rows.append(row)

    return rows


def _query_runtime_rows_for_trace_v1(
    state: Mapping[str, Any],
    *,
    include_values: bool,
    max_results: int,
) -> list[Dict[str, Any]]:
    """
    Query runtime write index for fill/prefill/lifecycle facts.
    """
    result = query_runtime_writes(
        state,
        {
            "write_kinds": ["form_fill", "form_prefill", "datum_lifecycle"],
            "include_values": include_values,
            "max_results": max_results,
        },
    )

    rows = result.get("writes") if isinstance(result, Mapping) else None
    if not isinstance(rows, list):
        return []

    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _find_first_mapping_under_key_v1(
    root: Any,
    wanted_key: str,
    *,
    max_nodes: int = 10_000,
) -> Dict[str, Any]:
    stack = [root]
    seen: set[int] = set()
    visited = 0

    while stack and visited < max_nodes:
        cur = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, Mapping):
            for raw_k, raw_v in cur.items():
                k = str(raw_k)
                if k == wanted_key and isinstance(raw_v, Mapping):
                    return dict(raw_v)
                stack.append(raw_v)
        elif isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)

    return {}


def _find_status_v1(root: Any) -> str | None:
    stack = [root]
    seen: set[int] = set()
    visited = 0

    while stack and visited < 10_000:
        cur = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        if isinstance(cur, Mapping):
            status = cur.get("status")
            if isinstance(status, str):
                return status
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)

    return None


def _find_any_micro_names_v1(root: Any) -> list[str]:
    """
    Find the first non-empty micros list in a nested lifecycle value.
    """
    stack = [root]
    seen: set[int] = set()
    visited = 0

    while stack and visited < 10_000:
        cur = stack.pop()
        visited += 1

        oid = id(cur)
        if oid in seen:
            continue
        seen.add(oid)

        names = _micro_names_v1(cur)
        if names:
            return names

        if isinstance(cur, Mapping):
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple, set, frozenset)):
            stack.extend(cur)

    return []


def _runtime_rows_to_trace_rows_v1(
    runtime_rows: Sequence[Mapping[str, Any]],
    *,
    include_values: bool,
    include_q_lifecycle: bool,
    datum_defs: Mapping[str, Mapping[str, Any]],
    datum_to_span: Mapping[str, str],
) -> list[Dict[str, Any]]:
    """
    Convert indexed runtime-write rows into public table rows.
    """
    rows: list[Dict[str, Any]] = []

    seen_io: set[tuple[str, str, str]] = set()
    seen_q: set[tuple[str, str, str]] = set()

    for raw in runtime_rows:
        write_kind = str(raw.get("write_kind") or raw.get("kind") or "")
        datum_id = str(raw.get("key") or raw.get("datum_id") or "")

        if not datum_id:
            continue

        span_id = str(raw.get("span_id") or datum_to_span.get(datum_id) or "")

        if write_kind in {"form_fill", "form_prefill"}:
            dedupe = (write_kind, datum_id, repr(raw.get("value")))
            if dedupe in seen_io:
                continue
            seen_io.add(dedupe)

            row: Dict[str, Any] = {
                "row_kind": "datum_io",
                "datum_id": datum_id,
                "span_id": span_id or None,
                "write_kind": write_kind,
            }

            if include_values and "value" in raw:
                row["value"] = raw.get("value")

            rows.append(row)
            continue

        if write_kind != "datum_lifecycle" or not include_q_lifecycle:
            continue

        value = raw.get("value")
        status = _find_status_v1(value) or raw.get("status") or "unknown"
        from_micros = _micro_names_v1(datum_defs.get(datum_id, {}))
        to_micros = _find_any_micro_names_v1(value)
        prefill = _find_first_mapping_under_key_v1(value, "prefill")
        q_state = _find_first_mapping_under_key_v1(value, "state")

        text = repr(value)
        has_reexplode_shape = bool(
            status in {"reexplode", "forced_done"}
            or to_micros
            or prefill
            or "reexplode" in text
        )

        if not has_reexplode_shape:
            continue

        dedupe = (datum_id, status, repr(to_micros or prefill))
        if dedupe in seen_q:
            continue
        seen_q.add(dedupe)

        row = {
            "row_kind": "datum_reexplosion",
            "datum_id": datum_id,
            "span_id": span_id or None,
            "status": status,
            "from_micros": from_micros,
            "to_micros": to_micros,
        }

        if include_values:
            if prefill:
                row["prefill"] = prefill
            if q_state:
                row["q_state"] = q_state

        rows.append(row)

    return rows


def _bounded_rows_result_v1(
    *,
    rows: Sequence[Mapping[str, Any]],
    max_results: int,
) -> Dict[str, Any]:
    seq = [dict(row) for row in rows]
    limited = seq[:max_results]

    return {
        "kind": KIND_PROGRAM_TRACE_TABLE_V1,
        "max_results": int(max_results),
        "row_count": len(limited),
        "total_available": len(seq),
        "truncated": len(seq) > max_results,
        "rows": limited,
    }


def _program_trace_table_v1(
    *,
    session_id: str,
    manifest_rows: Sequence[Mapping[str, Any]],
    outputs: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    query: Mapping[str, Any],
    caps: Optional[PublicSessionCaps | Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build the compact public trace table used by query_session(...).
    """
    q = _normalize_trace_query_v1(query, caps=caps)
    max_results = int(q["max_results"])
    include_values = bool(q["include_datum_values"])
    include_topology = bool(q["include_topology"])
    include_q_lifecycle = bool(q["include_q_lifecycle"])

    state = snapshot.get("state")
    if not isinstance(state, Mapping):
        state = {}

    all_roots = {
        "outputs": outputs,
        "snapshot": snapshot,
        "state": state,
    }

    multiframespecs = list(_iter_multiframespecs_v1(all_roots))
    topology_rows, datum_defs, datum_to_span, _span_to_form = (
        _multiframespec_topology_v1(multiframespecs)
    )

    rows: list[Dict[str, Any]] = []

    rows.extend(dict(row) for row in manifest_rows)

    if include_topology:
        rows.extend(topology_rows)

    rows.extend(
        _datum_io_rows_from_outputs_v1(
            outputs,
            include_values=include_values,
            datum_to_span=datum_to_span,
        )
    )

    runtime_rows = _query_runtime_rows_for_trace_v1(
        state,
        include_values=include_values,
        max_results=max_results,
    )

    rows.extend(
        _runtime_rows_to_trace_rows_v1(
            runtime_rows,
            include_values=include_values,
            include_q_lifecycle=include_q_lifecycle,
            datum_defs=datum_defs,
            datum_to_span=datum_to_span,
        )
    )

    order = {
        "app_call": 0,
        "span": 1,
        "datum_io": 2,
        "datum_reexplosion": 3,
    }
    rows.sort(
        key=lambda row: (
            order.get(str(row.get("row_kind")), 99),
            str(row.get("call_index", "")),
            str(row.get("form_id", "")),
            str(row.get("frame_id", "")),
            str(row.get("span_id", "")),
            str(row.get("datum_id", "")),
            str(row.get("write_kind", "")),
        )
    )

    return _bounded_rows_result_v1(
        rows=rows,
        max_results=max_results,
    )