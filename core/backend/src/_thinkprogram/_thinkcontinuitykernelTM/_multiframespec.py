from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Dict, List

from ._contracts import apply_kernel_arg_defaults_v1
from ._history import build_kernel_past_wires_for_datum_v1


def build_kernel_multiframespec_v1(
    kernel: Mapping[str, Any],
    resolved_history_queries: Mapping[str, Any],
) -> Dict[str, Any]:
    step = deepcopy(dict(kernel["step"]))
    form = deepcopy(dict(kernel["form"]))
    frame = deepcopy(dict(kernel["frame"]))
    span = deepcopy(dict(kernel["span"]))

    kernel_flags_raw = kernel.get("kernel_flags") or {}
    if not isinstance(kernel_flags_raw, Mapping):
        raise ValueError("kernel.kernel_flags must be mapping")

    kernel_flags = deepcopy(dict(kernel_flags_raw))

    copy_scopes = bool(
        kernel_flags.get(
            "copy_form_frame_span_args_into_each_datum",
            True,
        )
    )
    mount_default = bool(
        kernel_flags.get(
            "mount_explode_default",
            True,
        )
    )

    history_queries_raw = kernel.get("history_queries") or {}
    if not isinstance(history_queries_raw, Mapping):
        raise ValueError("kernel.history_queries must be mapping")

    history_queries = {
        key: deepcopy(dict(value)) if isinstance(value, Mapping) else deepcopy(value)
        for key, value in dict(history_queries_raw).items()
    }

    datums_out: List[Dict[str, Any]] = []
    owns: List[str] = []
    authoritative: List[str] = []

    for d_raw in list(kernel.get("datums") or []):
        if not isinstance(d_raw, Mapping):
            raise ValueError("kernel.datums items must be mappings")

        d = dict(d_raw)
        did = str(d["id"])
        owns.append(did)

        is_authoritative = bool(d.get("authoritative", True))
        if is_authoritative:
            authoritative.append(did)

        lifecycle = deepcopy(dict(d.get("lifecycle") or {}))
        lifecycle.setdefault("mount_explode", mount_default)
        lifecycle.setdefault("max_reexplosions", 10)
        lifecycle.setdefault("max_proc_notes", 8)
        lifecycle.setdefault("max_messages", 8)
        lifecycle["widget"] = str(d["widget"])

        user_args = apply_kernel_arg_defaults_v1(
            widget=str(d["widget"]),
            args=deepcopy(dict(d.get("args") or {})),
        )

        frame_for_datum = (
            deepcopy(frame)
            if copy_scopes
            else {
                "id": frame.get("id"),
            }
        )
        span_for_datum = (
            deepcopy(span)
            if copy_scopes
            else {
                "id": span.get("id"),
            }
        )

        user_args["__kernel"] = {
            "kernel_args_surface_version": "v1",
            "past_wires": build_kernel_past_wires_for_datum_v1(
                datum=d,
                resolved_history_queries=resolved_history_queries,
            ),
            "history_queries": deepcopy(history_queries),
            "step": deepcopy(step),
            "form": deepcopy(form),
            "frame": frame_for_datum,
            "span": span_for_datum,

            # Effective runtime flags remain separate from authored arguments.
            "kernel_flags": deepcopy(kernel_flags),

            "system_flags": deepcopy(dict(d.get("system_flags") or {})),
            "authoritative": is_authoritative,
        }

        datum_out: Dict[str, Any] = {
            "id": did,
            "title": str(d.get("title") or did),
            "micros": deepcopy(list(d.get("micros") or [])),
            "args": user_args,
            "lifecycle": lifecycle,
        }

        for key in (
            "tags",
            "roles",
            "role",
            "system_flags",
            "authoritative",
        ):
            if key in d:
                datum_out[key] = deepcopy(d[key])

        datums_out.append(datum_out)

    span_out: Dict[str, Any] = {
        "id": str(span["id"]),
        "title": str(span.get("title") or span["id"]),
        "args": deepcopy(dict(span.get("args") or {})),
        "owns": owns,
        "authoritative": authoritative,
    }

    for key in ("roles", "role", "tags"):
        if key in span:
            span_out[key] = deepcopy(span[key])

    return {
        "app_form_id": str(form["id"]),
        "datums": datums_out,
        "frames": [
            {
                "id": str(frame["id"]),
                "title": str(frame.get("title") or frame["id"]),
                "args": deepcopy(dict(frame.get("args") or {})),
                "spans": [span_out],
            }
        ],
    }