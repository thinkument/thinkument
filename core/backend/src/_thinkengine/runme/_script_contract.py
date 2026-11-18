"""
Central reusable session/result contract helpers.

This module owns generic, non-scripting-specific mechanics:

    - dead-JSON-ish sanitization for result shells
    - fill normalization for session input
    - slim ctx projection for histories/results

It deliberately imports no UI renderer, no launch layer, no concrete session
API implementation, and no scripting rollout policy.
"""

from typing import Any, Dict, Mapping, Optional

from _thinkprogram._iomicrosTM.tiny_helpers import JSONValue, mapping_from_any_v1, json_sanitize_v1


def normalize_session_fill_json_v1(
    fill: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Normalize dotted fill syntax into session fill shape.

    Examples:
        {"PROFILE.name": "Ada"}
        -> {"PROFILE": {"name": "Ada"}}

        {"PROFILE": {"name": "Ada"}}
        -> unchanged grouped datum fill
    """
    if not fill:
        return None

    out: Dict[str, Any] = {}
    for raw_key, raw_value in dict(fill).items():
        key = str(raw_key)

        if "." in key:
            datum_id, micro_name = key.split(".", 1)
            current = dict(out.get(datum_id) or {})
            current[micro_name] = raw_value
            out[datum_id] = current
            continue

        if isinstance(raw_value, Mapping):
            current = dict(out.get(key) or {})
            current.update(dict(raw_value))
            out[key] = current
            continue

        out[key] = raw_value

    return out


def slim_ctx_for_script_result_v1(ctx: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Compact ctx shell safe for histories and public results.

    This must never include multiframespec, snapshot, outputs, or full
    report blobs.
    """
    cursor = mapping_from_any_v1(ctx.get("cursor"))
    state = mapping_from_any_v1(ctx.get("state"))
    out = {
        "kind": ctx.get("kind"),
        "session_id": ctx.get("session_id"),
        "cursor": {
            "index": cursor.get("index"),
            "total": cursor.get("total"),
        },
        "step": ctx.get("step") if isinstance(ctx.get("step"), Mapping) else {},
        "datum_widgets_on_this_span": list(ctx.get("datum_widgets_on_this_span") or []),
        "current_frame_id": ctx.get("current_frame_id"),
        "current_span": ctx.get("current_span") or ctx.get("current_span_id"),
        "form_id": ctx.get("form_id"),
        "last_error": ctx.get("last_error"),
        "state": {
            "pending_multiframespec": bool(state.get("pending_multiframespec")),
            "pending_multiframespec_id": state.get("pending_multiframespec_id"),
            "form_prefills_keys": list(state.get("form_prefills_keys") or []),
            "form_fills_keys": list(state.get("form_fills_keys") or []),
            "forms_emitted_order": list(state.get("forms_emitted_order") or []),
        },
        "slim_result": True,
    }
    return json_sanitize_v1(out)  # type: ignore[return-value]


__all__ = [
    "json_sanitize_v1",
    "mapping_from_any_v1",
    "normalize_session_fill_json_v1",
    "slim_ctx_for_script_result_v1",
]
