from __future__ import annotations

"""
Projection and sanitization helpers for the bounded public session façade.

This file owns S/G envelope construction and public output stripping. It does
not create sessions, step sessions, or build trace tables.

Public helpers intentionally kept stable here and re-exported by
session_facade.py:

- public_session_report_from_ctx_v1
- public_command_receipt_from_ctx_v1
- public_create_receipt_v1
- public_delete_receipt_v1
"""

from typing import Any, Dict, Mapping, Optional

from _thinkengine.runme._runme_progress_contract import (
    json_sanitize_v1,
)

from _thinkengine.runme_optimized_queryable._globals import (
    DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1,
    DEFAULT_OUTPUT_KEY_PREVIEW_LIMIT_V1,
    DEFAULT_PUBLIC_SANITIZER_DICT_LIMIT_V1,
    DEFAULT_PUBLIC_SANITIZER_LIST_LIMIT_V1,
    DEFAULT_PUBLIC_SANITIZER_STRING_LIMIT_V1,
    DEFAULT_REDO_ACTION_MAX_PAYLOAD_CHARS_V1,
    DEFAULT_REDO_MAX_DEPTH_V1,
    DEFAULT_FORMS_EMITTED_SNAPSHOT_WINDOW_V1,
    KIND_COMMAND_RECEIPT_V1,
    KIND_SESSION_REPORT_V1,
    PUBLIC_API_VERSION_V1,
    PublicSessionCaps,
    _PUBLIC_FORBIDDEN_CONTAINER_KEYS_V1,
)


def _coerce_public_caps_v1(
    caps: Optional[PublicSessionCaps | Mapping[str, Any]] = None,
) -> PublicSessionCaps:
    if caps is None:
        return PublicSessionCaps()

    if isinstance(caps, PublicSessionCaps):
        return caps

    if isinstance(caps, Mapping):
        return PublicSessionCaps(**dict(caps))

    raise TypeError(
        "public API caps must be PublicSessionCaps, mapping, or None; "
        f"got {type(caps).__name__}"
    )


def _merge_public_session_storage_policy_v1(
    session_metadata: Any,
    *,
    caps: PublicSessionCaps,
) -> Dict[str, Any]:
    """
    Add public default storage caps without overwriting app choices.
    """
    meta = dict(session_metadata or {}) if isinstance(session_metadata, Mapping) else {}
    storage = (
        dict(meta.get("session_storage") or {})
        if isinstance(meta.get("session_storage"), Mapping)
        else {}
    )

    storage.setdefault(
        "forms_emitted_snapshot_window",
        caps.forms_emitted_snapshot_window,
    )
    storage.setdefault("redo_max_depth", caps.redo_max_depth)
    storage.setdefault(
        "redo_action_max_payload_chars",
        caps.redo_action_max_payload_chars,
    )

    meta["session_storage"] = storage
    return meta


def _as_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _bounded_int(
    value: Any,
    *,
    default: int,
    upper: int,
) -> int:
    try:
        out = int(value)
    except Exception:
        out = int(default)

    if out <= 0:
        return int(default)

    return min(int(out), int(upper))


def _cursor_from_ctx(ctx: Mapping[str, Any]) -> Dict[str, Any]:
    cursor = _as_mapping(ctx.get("cursor"))
    return {
        "index": cursor.get("index"),
        "total": cursor.get("total"),
    }


def _state_counts_from_ctx(ctx: Mapping[str, Any]) -> Dict[str, Any]:
    state = _as_mapping(ctx.get("state"))

    return {
        "form_prefills": (
            state.get("form_prefills_count")
            if "form_prefills_count" in state
            else len(state.get("form_prefills_keys") or [])
        ),
        "form_fills": (
            state.get("form_fills_count")
            if "form_fills_count" in state
            else len(state.get("form_fills_keys") or [])
        ),
        "forms_emitted": (
            state.get("forms_emitted_count")
            if "forms_emitted_count" in state
            else len(state.get("forms_emitted_order") or [])
        ),
        "datum_widget_fills": state.get("datum_widget_fills_count"),
        "datum_lifecycle_epoch": state.get("datum_lifecycle_epoch"),
    }


def _pending_from_ctx(
    ctx: Mapping[str, Any],
    *,
    datum_widgets_on_this_span_preview_limit: int = (
        DEFAULT_datum_widgets_on_this_span_PREVIEW_LIMIT_V1
    ),
) -> Dict[str, Any]:
    """
    Project the current public stop into bounded metadata.
    """
    step = _as_mapping(ctx.get("step"))

    raw_datum_widgets_on_this_span = [
        str(x)
        for x in list(ctx.get("datum_widgets_on_this_span") or [])
    ]

    cap = max(1, int(datum_widgets_on_this_span_preview_limit))
    pending_preview = raw_datum_widgets_on_this_span[:cap]

    return {
        "form_id": ctx.get("form_id") or ctx.get("app_form_id"),
        "frame_id": ctx.get("current_frame_id") or step.get("frame_id"),
        "span_id": (
            ctx.get("current_span")
            or ctx.get("current_span_id")
            or step.get("span_id")
        ),
        "datum_widgets_on_this_span": pending_preview,
        "datum_widgets_on_this_span_count": len(raw_datum_widgets_on_this_span),
        "datum_widgets_on_this_span_truncated": (
            len(raw_datum_widgets_on_this_span) > cap
        ),
        "datum_widgets_on_this_span_preview_limit": cap,
    }


def _sanitize_small(value: Any) -> Any:
    return json_sanitize_v1(value)


def _is_public_metadata_path_v1(
    *,
    parent_key: str | None,
    key: str,
    value: Any,
) -> bool:
    if parent_key == "counts":
        return isinstance(value, (int, type(None)))

    if parent_key == "keys":
        return isinstance(value, list) and all(isinstance(x, str) for x in value)

    if parent_key == "truncated_keys":
        return isinstance(value, bool)

    if parent_key in {"previews", "summary", "result"}:
        return True

    return False


def _sanitize_public_value_v1(
    value: Any,
    *,
    parent_key: str | None = None,
    max_str: int = DEFAULT_PUBLIC_SANITIZER_STRING_LIMIT_V1,
    max_list: int = DEFAULT_PUBLIC_SANITIZER_LIST_LIMIT_V1,
    max_dict: int = DEFAULT_PUBLIC_SANITIZER_DICT_LIMIT_V1,
) -> Any:
    """
    Recursively sanitize public output and strip forbidden raw containers.
    """
    value = _sanitize_small(value)

    if isinstance(value, str):
        if len(value) <= max_str:
            return value
        return value[:max_str] + f"...<truncated {len(value) - max_str} chars>"

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    if isinstance(value, Mapping):
        out: dict[str, Any] = {}

        for i, (raw_key, raw_value) in enumerate(value.items()):
            if i >= max_dict:
                out["_truncated"] = True
                out["_max_items"] = max_dict
                break

            key = str(raw_key)

            if key in _PUBLIC_FORBIDDEN_CONTAINER_KEYS_V1:
                if not _is_public_metadata_path_v1(
                    parent_key=parent_key,
                    key=key,
                    value=raw_value,
                ):
                    continue

            out[key] = _sanitize_public_value_v1(
                raw_value,
                parent_key=key,
                max_str=max_str,
                max_list=max_list,
                max_dict=max_dict,
            )

        return out

    if isinstance(value, (list, tuple)):
        seq = list(value)
        out_list = [
            _sanitize_public_value_v1(
                item,
                parent_key=parent_key,
                max_str=max_str,
                max_list=max_list,
                max_dict=max_dict,
            )
            for item in seq[:max_list]
        ]

        if len(seq) > max_list:
            out_list.append(
                {
                    "_truncated": True,
                    "_max_items": max_list,
                    "_omitted_items": len(seq) - max_list,
                }
            )

        return out_list

    if isinstance(value, (set, frozenset)):
        seq = list(value)
        out_list = [
            _sanitize_public_value_v1(
                item,
                parent_key=parent_key,
                max_str=max_str,
                max_list=max_list,
                max_dict=max_dict,
            )
            for item in seq[:max_list]
        ]

        if len(seq) > max_list:
            out_list.append(
                {
                    "_truncated": True,
                    "_max_items": max_list,
                    "_omitted_items": len(seq) - max_list,
                }
            )

        return out_list

    return repr(value)[:max_str]


def _strip_forbidden_public_keys(
    row: Mapping[str, Any],
    *,
    caps: Optional[PublicSessionCaps | Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Sanitize one public envelope.
    """
    c = _coerce_public_caps_v1(caps)

    cleaned = _sanitize_public_value_v1(
        row,
        max_str=c.public_sanitizer_string_limit,
        max_list=c.public_sanitizer_list_limit,
        max_dict=c.public_sanitizer_dict_limit,
    )

    if isinstance(cleaned, dict):
        return cleaned

    return {"value": cleaned}


def public_session_report_from_ctx_v1(
    ctx: Mapping[str, Any],
    *,
    session_id: Optional[str] = None,
    operation: Optional[str] = None,
    caps: Optional[PublicSessionCaps | Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Project any raw ctx-like mapping into bounded public G.
    """
    c = _coerce_public_caps_v1(caps)

    sid = str(session_id or ctx.get("session_id") or "")

    out = {
        "kind": KIND_SESSION_REPORT_V1,
        "v": PUBLIC_API_VERSION_V1,
        "ok": True,
        "session_id": sid,
        "operation": operation,
        "event_kind": ctx.get("kind"),
        "cursor": _cursor_from_ctx(ctx),
        "pending": _pending_from_ctx(
            ctx,
            datum_widgets_on_this_span_preview_limit=(
                c.datum_widgets_on_this_span_preview_limit
            ),
        ),
        "counts": _state_counts_from_ctx(ctx),
        "finished": str(ctx.get("kind") or "") == "ATCOMPLETION",
        "last_error": ctx.get("last_error"),
        "slim_result": True,
    }

    return _strip_forbidden_public_keys(out, caps=c)


def public_command_receipt_from_ctx_v1(
    ctx: Mapping[str, Any],
    *,
    operation: str,
    session_id: Optional[str] = None,
    accepted: bool = True,
    caps: Optional[PublicSessionCaps | Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Project a post-command raw ctx into S.
    """
    c = _coerce_public_caps_v1(caps)

    sid = str(session_id or ctx.get("session_id") or "")

    out = {
        "kind": KIND_COMMAND_RECEIPT_V1,
        "v": PUBLIC_API_VERSION_V1,
        "ok": True,
        "operation": str(operation),
        "session_id": sid,
        "accepted": bool(accepted),
        "event_kind": ctx.get("kind"),
        "cursor": _cursor_from_ctx(ctx),
        "pending": _pending_from_ctx(
            ctx,
            datum_widgets_on_this_span_preview_limit=(
                c.datum_widgets_on_this_span_preview_limit
            ),
        ),
        "finished": str(ctx.get("kind") or "") == "ATCOMPLETION",
        "last_error": ctx.get("last_error"),
    }

    return _strip_forbidden_public_keys(out, caps=c)


def public_create_receipt_v1(
    created: Any,
    *,
    operation: str,
    caps: Optional[PublicSessionCaps | Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Project legacy create return into S.
    """
    c = _coerce_public_caps_v1(caps)

    if isinstance(created, tuple) and created:
        state = _as_mapping(created[0])
    else:
        state = _as_mapping(created)

    session_id = str(state.get("session_id") or "")

    if not session_id:
        raise TypeError("create operation did not produce a session_id")

    out = {
        "kind": KIND_COMMAND_RECEIPT_V1,
        "v": PUBLIC_API_VERSION_V1,
        "ok": True,
        "operation": str(operation),
        "session_id": session_id,
        "accepted": True,
        "event_kind": "SESSION_CREATED",
        "cursor": None,
        "pending": None,
        "finished": False,
        "last_error": None,
    }

    return _strip_forbidden_public_keys(out, caps=c)


def public_delete_receipt_v1(
    report: Any,
    *,
    session_id: str,
    caps: Optional[PublicSessionCaps | Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    c = _coerce_public_caps_v1(caps)
    raw = _as_mapping(report)

    out = {
        "kind": KIND_COMMAND_RECEIPT_V1,
        "v": PUBLIC_API_VERSION_V1,
        "ok": bool(raw.get("ok", True)),
        "operation": "delete_session",
        "session_id": str(session_id),
        "accepted": True,
        "event_kind": "SESSION_DELETED",
        "cursor": None,
        "pending": None,
        "finished": True,
        "last_error": None,
    }

    return _strip_forbidden_public_keys(out, caps=c)


def _outputs_report_from_outputs_v1(
    outputs: Mapping[str, Any],
    *,
    session_id: str,
    caps: Optional[PublicSessionCaps | Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Project raw outputs into G without returning large values.
    """
    c = _coerce_public_caps_v1(caps)

    globals_row = _as_mapping(outputs.get("globals"))
    prefills = _as_mapping(outputs.get("form_prefills"))
    fills = _as_mapping(outputs.get("form_fills"))
    merged = _as_mapping(outputs.get("merged_fills"))

    key_cap = max(1, int(c.output_key_preview_limit))

    globals_keys = sorted(str(k) for k in globals_row.keys())
    prefill_keys = sorted(str(k) for k in prefills.keys())
    fill_keys = sorted(str(k) for k in fills.keys())
    merged_keys = sorted(str(k) for k in merged.keys())

    out = {
        "kind": KIND_SESSION_REPORT_V1,
        "v": PUBLIC_API_VERSION_V1,
        "ok": True,
        "session_id": str(session_id),
        "operation": "outputs_report",
        "event_kind": "OUTPUTS_REPORT",
        "cursor": None,
        "pending": None,
        "finished": None,
        "last_error": None,
        "counts": {
            "globals": len(globals_row),
            "form_prefills": len(prefills),
            "form_fills": len(fills),
            "merged_fills": len(merged),
        },
        "keys": {
            "globals": globals_keys[:key_cap],
            "form_prefills": prefill_keys[:key_cap],
            "form_fills": fill_keys[:key_cap],
            "merged_fills": merged_keys[:key_cap],
        },
        "truncated_keys": {
            "globals": len(globals_keys) > key_cap,
            "form_prefills": len(prefill_keys) > key_cap,
            "form_fills": len(fill_keys) > key_cap,
            "merged_fills": len(merged_keys) > key_cap,
        },
        "key_preview_limit": key_cap,
        "slim_result": True,
    }

    return _strip_forbidden_public_keys(out, caps=c)