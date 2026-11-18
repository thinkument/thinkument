from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from _thinkprogram._iomicrosTM.tiny_helpers import (
    _is_json_safe,
    _merge_dicts,
    _safe_mapping_dict,
)


def _lift_style_tokens(style: Any, renderer_config_cls: Any) -> Dict[str, Any]:
    """
    Drift-proof lifting of recognized semantic UI tokens from a style dict.

    Dataclass-driven: when RendererSpecificConfig gains a new field,
    the adapter automatically begins lifting it.
    """
    return renderer_config_cls.lift_style_tokens(style)


def _collect_frames(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    frames = spec.get("frames") or []
    if not isinstance(frames, list):
        raise TypeError("_multiframespec.frames must be a list of dicts")
    return [f for f in frames if isinstance(f, dict)]


def _collect_datums(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    datums = spec.get("datums") or []
    if not isinstance(datums, list):
        raise TypeError("_multiframespec.datums must be a list of dicts")
    return [d for d in datums if isinstance(d, dict)]


def _collect_spans(frame: Dict[str, Any]) -> List[Dict[str, Any]]:
    spans = frame.get("spans") or []
    if not isinstance(spans, list):
        raise TypeError("Frame.spans must be a list of dicts")
    return [s for s in spans if isinstance(s, dict)]


def _span_id_collision_policy(frames: List[Dict[str, Any]]) -> Tuple[bool, Set[str]]:
    """
    Return (needs_qualification, raw_ids_set).
    """
    seen: Set[str] = set()
    dup: Set[str] = set()
    for fr in frames:
        for sp in _collect_spans(fr):
            sid = str(sp.get("id") or "")
            if not sid:
                continue
            if sid in seen:
                dup.add(sid)
            seen.add(sid)
    return (len(dup) > 0, seen)


def _qualify_span_name(frame_id: str, span_id: str, *, qualify: bool) -> str:
    return f"{frame_id}:{span_id}" if qualify else span_id


def _resolve_current_span_name(
    *,
    request_frame_id: str,
    request_span_id: str,
    qualify: bool,
) -> str:
    if qualify:
        if ":" in request_span_id:
            return request_span_id
        return f"{request_frame_id}:{request_span_id}"
    return request_span_id


def _validate_multiframespec_ui_request(req: Mapping[str, Any]) -> None:
    """
    Validate the minimum shape for a multiframespec -> UI context adaptation request.

    This does NOT validate that frame/span exist in the spec; that's the adapter's job.
    """
    if not isinstance(req, Mapping):
        raise TypeError("multiframespecUIRequest must be a mapping/dict")

    frame_id = req.get("frame_id")
    if not isinstance(frame_id, str) or not frame_id.strip():
        raise ValueError("multiframespecUIRequest.frame_id must be a non-empty string")

    readonly = bool(req.get("readonly", False))

    span_id = req.get("span_id", None)
    if not readonly:
        if not isinstance(span_id, str) or not str(span_id).strip():
            raise ValueError(
                "multiframespecUIRequest.span_id must be a non-empty string (unless readonly=True)"
            )

    fv = req.get("datum_widget_fills", {})
    if fv is not None and not isinstance(fv, dict):
        raise TypeError("multiframespecUIRequest.datum_widget_fills must be a dict if provided")

    pf = req.get("datum_widgets_on_this_span", None)
    if pf is not None and not isinstance(pf, (list, tuple)):
        raise TypeError("multiframespecUIRequest.datum_widgets_on_this_span must be a sequence if provided")

    le = req.get("last_error", None)
    if le is not None and not isinstance(le, dict):
        raise TypeError("multiframespecUIRequest.last_error must be a dict if provided")

    meta = req.get("session_metadata", {})
    if meta is not None and not isinstance(meta, dict):
        raise TypeError("multiframespecUIRequest.session_metadata must be a dict if provided")


def _extract_ui_sheet(spec: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Extract the L2/L3 args-sheet snapshot stored in spec["boxed"]["ui"].

    FINAL behavior:
      - best-effort: if absent/malformed, return {}
      - dict-only: always return a plain dict
    """
    boxed = spec.get("boxed")
    if not isinstance(boxed, Mapping):
        return {}
    ui = boxed.get("ui")
    if not isinstance(ui, Mapping):
        return {}
    return {str(k): v for k, v in dict(ui).items()}


def _micro_spec_value(micro: Mapping[str, Any], key: str) -> Any:
    """
    Resolve renderer-facing micro spec values with tolerant precedence:

      1) top-level micro[key]
      2) micro["style"][key]

    This preserves compatibility across both historical shapes:
    - spec-ish fields emitted directly on the micro
    - design overlays mirrored into the canonical micro style surface
    """
    direct = micro.get(key)
    if direct is not None:
        return direct
    style = micro.get("style")
    if isinstance(style, Mapping):
        return style.get(key)
    return None


_MICRO_UI_CONTEXT_CORE_KEYS = {
    "name",
    "type",
    "required",
    "tags",
    "value",
    "style",
    "validators",
    "constraints",
    "args",
    "placeholder",
    "options",
    "label",
}


def _sealed_micro_renderer_args_v1(micro: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Preserve custom micro declaration args across the multiframespec -> UI-context membrane.

    Forever law:
      - micro["args"] is the canonical sealed custom-micro declaration transport.
      - top-level mirrored custom keys are compatibility mirrors.
      - the UI adapter must not erase either before DatumRenderer sees them.
    """
    out: Dict[str, Any] = {}

    args = micro.get("args")
    if isinstance(args, Mapping):
        out["args"] = dict(args)
        out.update(dict(args))

    for k, v in micro.items():
        ks = str(k)
        if ks in _MICRO_UI_CONTEXT_CORE_KEYS:
            continue
        if v is not None:
            out[ks] = v

    return out


def _datum_content_fields(d: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Datum-level human content fields surfaced into UI datum_args.

    V2 authors think in title/subtitle/help_text at the form/datum level.
    These should be directly visible in datum_args, not only buried inside
    the boxed structure args.
    """
    out = {
        "title": d.get("title"),
        "subtitle": d.get("subtitle"),
        "help_text": d.get("help_text"),
    }

    structure = d.get("structure")
    if isinstance(structure, Mapping):
        args = structure.get("args")
        if isinstance(args, Mapping):
            if out.get("subtitle") is None:
                out["subtitle"] = args.get("subtitle")
            if out.get("help_text") is None:
                out["help_text"] = args.get("help_text")
            if out.get("title") is None:
                out["title"] = args.get("title")

    return _merge_dicts(out)


__all__ = [
    "_collect_datums",
    "_collect_frames",
    "_collect_spans",
    "_datum_content_fields",
    "_extract_ui_sheet",
    "_is_json_safe",
    "_lift_style_tokens",
    "_merge_dicts",
    "_micro_spec_value",
    "_qualify_span_name",
    "_resolve_current_span_name",
    "_safe_mapping_dict",
    "_sealed_micro_renderer_args_v1",
    "_span_id_collision_policy",
    "_validate_multiframespec_ui_request",
]