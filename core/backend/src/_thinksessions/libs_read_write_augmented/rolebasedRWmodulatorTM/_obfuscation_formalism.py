from __future__ import annotations

"""
Role mismatch obfuscation formalism.

This module is the only place that knows how to locate datum-owned information
inside the renderer-facing UI ctx vector.

Formal object
-------------

For a UI ctx vector C and datum id d, this module constructs:

    A(C, d)

the address set of every known renderer-facing location that may contain
information about d.

Public ctx scope
----------------

The public renderer-facing ctx is not a full pending-form dump. It is the
current-frame projection:

    Π_frame(C)

Renderers need the whole current frame to render correctly. They do not need
future frames, future spans, or future datum declarations/fills.

If the UI ctx shape drifts away from this contract, this module raises early
instead of silently letting role-mismatch masking become stale.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, MutableMapping

from _thinksessions.run.runme_surfaces_out.__renderer_agnostic_universal_ui_ctx_payload import (
    CTX_CURRENT_FRAME_ID,
    CTX_CURRENT_SPAN,
    CTX_CURRENT_SPAN_ID,
    CTX_DATUM_STATES_ON_THIS_SPAN,
    CTX_DATUM_WIDGET_DECLS,
    CTX_DATUM_WIDGET_FILLS,
    CTX_DATUM_WIDGETS_ON_THIS_SPAN,
    CTX_FRAMES,
    CTX_LAST_ERROR,
    CTX_MULTIFRAMESPEC,
    CTX_SPAN_ORDER,
    CTX_SPAN_TO_DATUM_WIDGETS,
    CTX_STEP,
)


@dataclass(frozen=True, slots=True)
class DatumCtxAddresses:
    datum_id: str
    has_decl: bool
    has_fill: bool
    has_last_error: bool
    on_this_span_indices: tuple[int, ...]
    datum_states_on_this_span_indices: tuple[int, ...]
    span_to_datum_widgets_keys: tuple[str, ...]
    frame_field_id_slots: tuple[tuple[int, int], ...]
    step_list_keys: tuple[str, ...]
    multiframespec_datum_indices: tuple[int, ...]
    multiframespec_fill_present: bool
    multiframespec_frame_span_own_slots: tuple[tuple[int, int, int], ...]
    multiframespec_frame_indices: tuple[int, ...]


def _require_mapping(ctx: Any) -> MutableMapping[str, Any]:
    if not isinstance(ctx, MutableMapping):
        raise TypeError("role modulation requires a mutable dict ctx")
    return ctx


def _require_dict(value: Any, *, key: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"ctx[{key!r}] must be a dict when present")
    return value


def _require_list(value: Any, *, key: str) -> List[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"ctx[{key!r}] must be a list when present")
    return value


def _ids_match(*, wanted: str, candidate: str) -> bool:
    wanted_id = str(wanted or "").strip()
    candidate_id = str(candidate or "").strip()

    if not wanted_id or not candidate_id:
        return False

    return (
        wanted_id == candidate_id
        or wanted_id.endswith(f":{candidate_id}")
        or wanted_id.endswith(f".{candidate_id}")
    )


def _ctx_multiframespec(ctx: Mapping[str, Any]) -> MutableMapping[str, Any]:
    raw = ctx.get(CTX_MULTIFRAMESPEC)
    if raw is None:
        return {}
    if not isinstance(raw, MutableMapping):
        raise TypeError(
            f"ctx[{CTX_MULTIFRAMESPEC!r}] must be a dict when present"
        )
    return raw


def _current_frame_id(ctx: Mapping[str, Any]) -> str:
    return str(
        ctx.get(CTX_CURRENT_FRAME_ID)
        or ctx.get("frame_id")
        or ""
    ).strip()


def _current_span_id(ctx: Mapping[str, Any]) -> str:
    return str(
        ctx.get(CTX_CURRENT_SPAN)
        or ctx.get(CTX_CURRENT_SPAN_ID)
        or ctx.get("span_id")
        or ""
    ).strip()


def _span_id(span: Mapping[str, Any]) -> str:
    return str(span.get("id") or span.get("name") or "").strip()


def _frame_id(frame: Mapping[str, Any]) -> str:
    return str(frame.get("id") or frame.get("name") or "").strip()


def collect_datum_ctx_addresses(
    ctx: MutableMapping[str, Any],
    *,
    datum_id: str,
) -> DatumCtxAddresses:
    """
    Return A(ctx, datum_id), the formal address set for datum-owned UI data.
    """
    _require_mapping(ctx)
    did = str(datum_id or "").strip()
    if not did:
        raise ValueError("datum_id must be non-empty")

    decls = _require_dict(
        ctx.get(CTX_DATUM_WIDGET_DECLS),
        key=CTX_DATUM_WIDGET_DECLS,
    )
    fills = _require_dict(
        ctx.get(CTX_DATUM_WIDGET_FILLS),
        key=CTX_DATUM_WIDGET_FILLS,
    )

    last_error_raw = ctx.get(CTX_LAST_ERROR)
    if last_error_raw is None:
        last_error = {}
    elif isinstance(last_error_raw, dict):
        last_error = last_error_raw
    else:
        raise TypeError(f"ctx[{CTX_LAST_ERROR!r}] must be dict|None")

    on_this_span = _require_list(
        ctx.get(CTX_DATUM_WIDGETS_ON_THIS_SPAN),
        key=CTX_DATUM_WIDGETS_ON_THIS_SPAN,
    )

    datum_states = _require_list(
        ctx.get(CTX_DATUM_STATES_ON_THIS_SPAN),
        key=CTX_DATUM_STATES_ON_THIS_SPAN,
    )
    datum_state_indices: list[int] = []
    for i, row in enumerate(datum_states):
        if not isinstance(row, Mapping):
            raise TypeError(
                f"ctx[{CTX_DATUM_STATES_ON_THIS_SPAN!r}]"
                f"[{i}] must be a dict"
            )

        candidate_id = str(
            row.get("datum_id")
            or row.get("id")
            or ""
        )
        if candidate_id == did:
            datum_state_indices.append(i)

    span_to_datums = _require_dict(
        ctx.get(CTX_SPAN_TO_DATUM_WIDGETS),
        key=CTX_SPAN_TO_DATUM_WIDGETS,
    )

    span_keys: list[str] = []
    for span_key, members in span_to_datums.items():
        if not isinstance(members, list):
            raise TypeError(
                f"ctx[{CTX_SPAN_TO_DATUM_WIDGETS!r}]"
                f"[{span_key!r}] must be a list"
            )
        if any(str(x) == did for x in members):
            span_keys.append(str(span_key))

    frames = _require_list(ctx.get(CTX_FRAMES), key=CTX_FRAMES)
    frame_slots: list[tuple[int, int]] = []
    for frame_i, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise TypeError(
                f"ctx[{CTX_FRAMES!r}][{frame_i}] must be a dict"
            )

        field_ids = frame.get("field_ids")
        if field_ids is None:
            continue
        if not isinstance(field_ids, list):
            raise TypeError(
                f"ctx[{CTX_FRAMES!r}]"
                f"[{frame_i}]['field_ids'] must be a list"
            )

        for field_i, value in enumerate(field_ids):
            if str(value) == did:
                frame_slots.append((frame_i, field_i))

    step = ctx.get(CTX_STEP)
    step_list_keys: list[str] = []
    if step is not None:
        if not isinstance(step, MutableMapping):
            raise TypeError(
                f"ctx[{CTX_STEP!r}] must be a dict when present"
            )

        for key in (
            "datum_widgets_on_this_span",
            "span_authoritative",
            "span_owns",
        ):
            value = step.get(key)
            if value is None:
                continue
            if not isinstance(value, list):
                raise TypeError(
                    f"ctx[{CTX_STEP!r}][{key!r}] must be a list"
                )
            if any(str(x) == did for x in value):
                step_list_keys.append(key)

    fs = _ctx_multiframespec(ctx)
    fs_datums = fs.get("datums") or []
    if not isinstance(fs_datums, list):
        raise TypeError(
            f"ctx[{CTX_MULTIFRAMESPEC!r}]['datums'] must be a list"
        )

    fs_datum_indices: list[int] = []
    for i, datum in enumerate(fs_datums):
        if not isinstance(datum, Mapping):
            raise TypeError(
                f"ctx[{CTX_MULTIFRAMESPEC!r}]"
                f"['datums'][{i}] must be a dict"
            )
        if str(datum.get("id") or "") == did:
            fs_datum_indices.append(i)

    fs_fills = fs.get("fills") or {}
    if not isinstance(fs_fills, Mapping):
        raise TypeError(
            f"ctx[{CTX_MULTIFRAMESPEC!r}]['fills'] must be a dict"
        )

    fs_frames = fs.get("frames") or []
    if not isinstance(fs_frames, list):
        raise TypeError(
            f"ctx[{CTX_MULTIFRAMESPEC!r}]['frames'] must be a list"
        )

    fs_own_slots: list[tuple[int, int, int]] = []
    fs_frame_indices: list[int] = []
    for frame_i, frame in enumerate(fs_frames):
        if not isinstance(frame, Mapping):
            raise TypeError(
                f"ctx[{CTX_MULTIFRAMESPEC!r}]"
                f"['frames'][{frame_i}] must be a dict"
            )

        spans = frame.get("spans") or []
        if not isinstance(spans, list):
            raise TypeError(
                f"ctx[{CTX_MULTIFRAMESPEC!r}]"
                f"['frames'][{frame_i}]['spans'] must be a list"
            )

        for span_i, span in enumerate(spans):
            if not isinstance(span, Mapping):
                continue

            owns = span.get("owns") or []
            if not isinstance(owns, list):
                raise TypeError("multiframespec span owns must be a list")

            for own_i, value in enumerate(owns):
                if str(value) == did:
                    fs_own_slots.append((frame_i, span_i, own_i))
                    if frame_i not in fs_frame_indices:
                        fs_frame_indices.append(frame_i)

    return DatumCtxAddresses(
        datum_id=did,
        has_decl=did in decls,
        has_fill=did in fills,
        has_last_error=did in last_error,
        on_this_span_indices=tuple(
            i
            for i, value in enumerate(on_this_span)
            if str(value) == did
        ),
        datum_states_on_this_span_indices=tuple(
            datum_state_indices
        ),
        span_to_datum_widgets_keys=tuple(span_keys),
        frame_field_id_slots=tuple(frame_slots),
        step_list_keys=tuple(step_list_keys),
        multiframespec_datum_indices=tuple(fs_datum_indices),
        multiframespec_fill_present=did in fs_fills,
        multiframespec_frame_span_own_slots=tuple(fs_own_slots),
        multiframespec_frame_indices=tuple(fs_frame_indices),
    )


def remove_datum_from_membership_vectors(
    ctx: MutableMapping[str, Any],
    *,
    datum_id: str,
) -> None:
    """
    Remove a datum from editable/navigation memberships.

    This is what makes mismatched micros non-fillable from the public ctx.

    ``datum_states_on_this_span`` is intentionally not modified here. It is the
    static span-owned datum product vector. Hidden rows remain in place as inert
    role-mismatch markers so ownership order and vector shape remain stable.
    """
    did = str(datum_id)

    on_this_span = ctx.get(CTX_DATUM_WIDGETS_ON_THIS_SPAN)
    if isinstance(on_this_span, list):
        ctx[CTX_DATUM_WIDGETS_ON_THIS_SPAN] = [
            x
            for x in on_this_span
            if str(x) != did
        ]

    span_to_datums = ctx.get(CTX_SPAN_TO_DATUM_WIDGETS)
    if isinstance(span_to_datums, dict):
        for span_key, members in list(span_to_datums.items()):
            if isinstance(members, list):
                span_to_datums[span_key] = [
                    x
                    for x in members
                    if str(x) != did
                ]

    frames = ctx.get(CTX_FRAMES)
    if isinstance(frames, list):
        for frame in frames:
            if not isinstance(frame, dict):
                continue

            field_ids = frame.get("field_ids")
            if isinstance(field_ids, list):
                frame["field_ids"] = [
                    x
                    for x in field_ids
                    if str(x) != did
                ]

    step = ctx.get(CTX_STEP)
    if isinstance(step, dict):
        for key in (
            "datum_widgets_on_this_span",
            "span_authoritative",
            "span_owns",
        ):
            value = step.get(key)
            if isinstance(value, list):
                step[key] = [
                    x
                    for x in value
                    if str(x) != did
                ]

    fs = ctx.get(CTX_MULTIFRAMESPEC)
    if isinstance(fs, dict):
        frames = fs.get("frames")
        if isinstance(frames, list):
            for frame in frames:
                if not isinstance(frame, dict):
                    continue

                spans = frame.get("spans")
                if not isinstance(spans, list):
                    continue

                for span in spans:
                    if not isinstance(span, dict):
                        continue

                    owns = span.get("owns")
                    if isinstance(owns, list):
                        span["owns"] = [
                            x
                            for x in owns
                            if str(x) != did
                        ]


def current_frame_scope_from_ctx(
    ctx: MutableMapping[str, Any],
) -> Dict[str, Any]:
    """
    Return the renderer-public current-frame scope.

    The scope contains:
      - current frame ids
      - current frame span ids
      - datum ids owned by spans in the current frame

    It intentionally excludes future frames/spans/datums.
    """
    _require_mapping(ctx)

    fs = _ctx_multiframespec(ctx)
    fs_frames = fs.get("frames") or []
    if not isinstance(fs_frames, list):
        raise TypeError(
            f"ctx[{CTX_MULTIFRAMESPEC!r}]['frames'] must be a list"
        )

    current_frame_id = _current_frame_id(ctx)
    current_span_id = _current_span_id(ctx)

    selected_frame_indices: list[int] = []

    for i, frame in enumerate(fs_frames):
        if not isinstance(frame, Mapping):
            raise TypeError(
                f"ctx[{CTX_MULTIFRAMESPEC!r}]"
                f"['frames'][{i}] must be a dict"
            )

        fid = _frame_id(frame)
        spans = frame.get("spans") or []
        if not isinstance(spans, list):
            raise TypeError("multiframespec frame spans must be a list")

        has_current_span = False
        for span in spans:
            if (
                isinstance(span, Mapping)
                and _ids_match(
                    wanted=current_span_id,
                    candidate=_span_id(span),
                )
            ):
                has_current_span = True
                break

        if current_frame_id and fid == current_frame_id:
            selected_frame_indices = [i]
            break

        if not selected_frame_indices and has_current_span:
            selected_frame_indices = [i]

    if not selected_frame_indices:
        return {
            "frame_ids": set(),
            "span_ids": set(),
            "datum_ids": set(),
        }

    span_ids: set[str] = set()
    datum_ids: set[str] = set()
    frame_ids: set[str] = set()

    for i in selected_frame_indices:
        frame = fs_frames[i]
        if not isinstance(frame, Mapping):
            continue

        fid = _frame_id(frame)
        if fid:
            frame_ids.add(fid)

        for span in list(frame.get("spans") or []):
            if not isinstance(span, Mapping):
                continue

            sid = _span_id(span)
            if sid:
                span_ids.add(sid)

            owns = span.get("owns") or []
            if isinstance(owns, list):
                datum_ids.update(
                    str(x)
                    for x in owns
                    if str(x or "").strip()
                )

    return {
        "frame_ids": frame_ids,
        "span_ids": span_ids,
        "datum_ids": datum_ids,
    }


def constrain_ctx_to_current_frame_scope(
    ctx: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """
    Public ctx projection Π_frame(C).

    Keeps the whole current frame. Removes future frames, future spans, and
    future datum declarations/fills/spec entries.
    """
    scope = current_frame_scope_from_ctx(ctx)
    frame_ids = set(scope["frame_ids"])
    span_ids = set(scope["span_ids"])
    datum_ids = set(scope["datum_ids"])

    if not frame_ids and not span_ids and not datum_ids:
        return ctx

    frames = ctx.get(CTX_FRAMES)
    if isinstance(frames, list):
        scoped_frames: list[Any] = []
        for frame in frames:
            if not isinstance(frame, dict):
                continue

            fid = str(frame.get("id") or frame.get("name") or "")
            fillspans = frame.get("fillspans") or []
            frame_span_ids = {
                str(s.get("name") or s.get("id") or "")
                for s in fillspans
                if isinstance(s, Mapping)
            }
            keep = bool(
                fid in frame_ids
                or frame_span_ids.intersection(span_ids)
            )
            if not keep:
                continue

            clone = dict(frame)
            if isinstance(clone.get("field_ids"), list):
                clone["field_ids"] = [
                    x
                    for x in clone["field_ids"]
                    if str(x) in datum_ids
                ]

            if isinstance(clone.get("fillspans"), list):
                clone["fillspans"] = [
                    sp
                    for sp in clone["fillspans"]
                    if (
                        isinstance(sp, Mapping)
                        and str(
                            sp.get("name")
                            or sp.get("id")
                            or ""
                        ) in span_ids
                    )
                ]

            scoped_frames.append(clone)

        ctx[CTX_FRAMES] = scoped_frames

    if isinstance(ctx.get(CTX_SPAN_ORDER), list):
        ctx[CTX_SPAN_ORDER] = [
            x
            for x in ctx[CTX_SPAN_ORDER]
            if str(x) in span_ids
        ]

    if isinstance(ctx.get(CTX_SPAN_TO_DATUM_WIDGETS), dict):
        ctx[CTX_SPAN_TO_DATUM_WIDGETS] = {
            str(span_id): [
                x
                for x in members
                if str(x) in datum_ids
            ]
            for span_id, members in dict(
                ctx[CTX_SPAN_TO_DATUM_WIDGETS]
            ).items()
            if (
                str(span_id) in span_ids
                and isinstance(members, list)
            )
        }

    if isinstance(ctx.get(CTX_DATUM_WIDGETS_ON_THIS_SPAN), list):
        ctx[CTX_DATUM_WIDGETS_ON_THIS_SPAN] = [
            x
            for x in ctx[CTX_DATUM_WIDGETS_ON_THIS_SPAN]
            if str(x) in datum_ids
        ]

    if isinstance(ctx.get(CTX_DATUM_STATES_ON_THIS_SPAN), list):
        ctx[CTX_DATUM_STATES_ON_THIS_SPAN] = [
            row
            for row in ctx[CTX_DATUM_STATES_ON_THIS_SPAN]
            if (
                isinstance(row, Mapping)
                and str(
                    row.get("datum_id")
                    or row.get("id")
                    or ""
                ) in datum_ids
            )
        ]

    if isinstance(ctx.get(CTX_DATUM_WIDGET_DECLS), dict):
        ctx[CTX_DATUM_WIDGET_DECLS] = {
            k: v
            for k, v in dict(ctx[CTX_DATUM_WIDGET_DECLS]).items()
            if str(k) in datum_ids
        }

    if isinstance(ctx.get(CTX_DATUM_WIDGET_FILLS), dict):
        ctx[CTX_DATUM_WIDGET_FILLS] = {
            k: v
            for k, v in dict(ctx[CTX_DATUM_WIDGET_FILLS]).items()
            if str(k) in datum_ids
        }

    fs = ctx.get(CTX_MULTIFRAMESPEC)
    if isinstance(fs, dict):
        if isinstance(fs.get("datums"), list):
            fs["datums"] = [
                datum
                for datum in fs["datums"]
                if (
                    isinstance(datum, Mapping)
                    and str(datum.get("id") or "") in datum_ids
                )
            ]

        if isinstance(fs.get("fills"), dict):
            fs["fills"] = {
                k: v
                for k, v in dict(fs["fills"]).items()
                if str(k) in datum_ids
            }

        if isinstance(fs.get("frames"), list):
            fs["frames"] = [
                frame
                for frame in fs["frames"]
                if (
                    isinstance(frame, Mapping)
                    and str(
                        frame.get("id")
                        or frame.get("name")
                        or ""
                    ) in frame_ids
                )
            ]

            for frame in fs["frames"]:
                if (
                    isinstance(frame, dict)
                    and isinstance(frame.get("spans"), list)
                ):
                    frame["spans"] = [
                        span
                        for span in frame["spans"]
                        if (
                            isinstance(span, Mapping)
                            and str(
                                span.get("id")
                                or span.get("name")
                                or ""
                            ) in span_ids
                        )
                    ]

    return ctx


__all__ = [
    "DatumCtxAddresses",
    "collect_datum_ctx_addresses",
    "constrain_ctx_to_current_frame_scope",
    "current_frame_scope_from_ctx",
    "remove_datum_from_membership_vectors",
]