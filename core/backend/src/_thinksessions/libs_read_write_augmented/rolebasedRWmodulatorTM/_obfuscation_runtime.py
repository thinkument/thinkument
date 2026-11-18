from __future__ import annotations

"""
Runtime role mismatch modulation.

This module owns the complete operational semantics:

    ctx, viewer role          -> augmented ctx
    augmented ctx             -> obfuscated ctx
    ctx, fill/signal, role    -> submission permission

The base App Table engine remains roleless.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence, Tuple

from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_active_span_record_from_ctx,
)
from _thinksessions.run.runme_surfaces_out.__renderer_agnostic_universal_ui_ctx_payload import (
    CTX_ROLE_MISMATCH_MODULATION_INFO,
    CTX_SESSION_METADATA,
)
from _thinksessions.sesh_metadata.__sesh_meta_rolebasedRWmodulatorTM_config_surface import (
    coerce_session_roles,
    effective_read_roles_for_role,
    role_can_read_required_roles,
    role_can_write_required_roles,
    role_mismatch_mode_for_viewer_role,
    sanitize_role_mismatch_policy_for_metadata,
    validate_role_modulation_surface,
)

from ._obfuscation_formalism import (
    collect_datum_ctx_addresses,
    constrain_ctx_to_current_frame_scope,
)
from ._obfuscation_modes import (
    DEFAULT_OBFUSCATION_MODE,
    RECEIPT_ACTIVITY,
    RECEIPT_IDENTITY,
    RECEIPT_OWNERSHIP,
    ObfuscationModeSpec,
    resolve_obfuscation_mode_spec,
)


RoleMap = Dict[str, Dict[str, Any]]
RoleMismatchPolicy = Dict[str, Any]


def _ctx_role_surface_is_inert_for_viewer(
    ctx: Mapping[str, Any],
    *,
    role: Optional[str],
) -> bool:
    """
    Fast path for ordinary roleless sessions.

    Most performance/complexity tests exercise the base session engine with no
    role sheet and no viewer role. In that case role modulation is a semantic
    no-op and must not deep-copy, scan multiframespecs, or recursively redact
    provenance.

    Important:
      - role=None with empty roles is inert.
      - role='x' with empty roles is not inert; it should still validate and
        raise through the normal path.
      - any non-empty role sheet or explicit mismatch policy goes through the
        normal path.
    """
    if role is not None:
        return False

    metadata = ctx.get(CTX_SESSION_METADATA)
    metadata = metadata if isinstance(metadata, Mapping) else {}

    raw_roles = metadata.get("roles")
    if isinstance(raw_roles, Mapping) and raw_roles:
        return False

    raw_policy = metadata.get("role_mismatch_policy")
    if isinstance(raw_policy, Mapping):
        role_modes = raw_policy.get("role_modes")
        if isinstance(role_modes, Mapping) and role_modes:
            return False

        default = str(
            raw_policy.get("default")
            or DEFAULT_OBFUSCATION_MODE
        ).strip()
        if default and default != DEFAULT_OBFUSCATION_MODE:
            return False

    return True


def _copy_for_public_noop_v1(
    ctx: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Cheap no-op release copy.

    The old modulator always returned a fresh dict. Preserve that outer-shell
    behavior without deep-copying the whole ctx for roleless sessions.
    """
    return dict(ctx or {})


def _roles_list(
    *,
    roles_value: Any,
    role_value: Any,
) -> list[str]:
    values: list[Any] = []

    if roles_value is not None:
        if isinstance(roles_value, str):
            values.append(roles_value)
        elif isinstance(roles_value, (list, tuple, set)):
            values.extend(list(roles_value))
        else:
            values.append(roles_value)
    elif role_value is not None:
        values.append(role_value)

    out: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)

    return out


def _is_datum_lifecycle_event_v1(
    event: Mapping[str, Any],
) -> bool:
    return (
        str(event.get("kind") or "")
        == "datum_lifecycle_event_v1"
        and bool(str(event.get("datum_id") or "").strip())
    )


def _mapping_roles_list(
    row: Mapping[str, Any],
) -> list[str]:
    return _roles_list(
        roles_value=row.get("roles"),
        role_value=row.get("role"),
    )


def _event_required_roles_from_ctx_v1(
    ctx: Mapping[str, Any],
    *,
    event: Mapping[str, Any],
) -> Optional[list[str]]:
    """
    Resolve the required roles for the datum targeted by one datum lifecycle
    event in one UI context.

    Return values:
      - list[str]: resolved required roles, possibly empty for unguarded;
      - None: this ctx does not contain enough location/source information for
        this event, so callers should try another event-time ctx.

    The resolver uses the same datum-over-span rule as public ctx modulation:

        datum.roles / datum.role
            win

        span.roles / span.role
            fallback when datum has no role data
    """
    if not _is_datum_lifecycle_event_v1(event):
        return []

    did = str(event.get("datum_id") or "").strip()
    if not did:
        return []

    event_frame_id = str(
        event.get("frame_id")
        or ""
    ).strip()
    event_span_id = str(
        event.get("span_id")
        or ""
    ).strip()

    fs = _ctx_multiframespec(ctx)
    datums = fs.get("datums") or []
    datums_by_id: Dict[str, Mapping[str, Any]] = {}

    if isinstance(datums, list):
        for datum in datums:
            if not isinstance(datum, Mapping):
                continue

            datum_id = str(
                datum.get("id")
                or ""
            ).strip()
            if datum_id:
                datums_by_id[datum_id] = datum

    datum = datums_by_id.get(did)
    if isinstance(datum, Mapping):
        datum_roles = _mapping_roles_list(datum)
        if datum_roles:
            return datum_roles

    frames = fs.get("frames") or []
    if isinstance(frames, list):
        for frame in frames:
            if not isinstance(frame, Mapping):
                continue

            frame_id = str(
                frame.get("id")
                or frame.get("name")
                or ""
            ).strip()
            if (
                event_frame_id
                and frame_id
                and not _ids_match(
                    wanted=event_frame_id,
                    candidate=frame_id,
                )
            ):
                continue

            spans = (
                frame.get("spans")
                or frame.get("fillspans")
                or []
            )
            if not isinstance(spans, list):
                continue

            for span in spans:
                if not isinstance(span, Mapping):
                    continue

                span_id = str(
                    span.get("id")
                    or span.get("name")
                    or ""
                ).strip()
                if (
                    event_span_id
                    and span_id
                    and not _ids_match(
                        wanted=event_span_id,
                        candidate=span_id,
                    )
                ):
                    continue

                owns = (
                    span.get("owns")
                    or span.get("fields")
                    or []
                )
                if not isinstance(owns, list):
                    owns = []

                if not any(
                    str(value) == did
                    for value in owns
                ):
                    continue

                return _mapping_roles_list(span)

    assignments = ctx.get("role_assignments")
    if isinstance(assignments, list):
        for row in assignments:
            if not isinstance(row, Mapping):
                continue
            if (
                str(row.get("datum_id") or "").strip()
                != did
            ):
                continue

            return [
                str(value)
                for value in list(row.get("roles") or [])
                if str(value or "").strip()
            ]

    return None


def _datum_required_roles_from_ctx_v1(
    ctx: Mapping[str, Any],
    *,
    datum_id: str,
) -> Optional[list[str]]:
    """
    Resolve one datum's roles in this context's active public scope.

    Controller action targets are interpreted relative to the dispatch entry
    context. A datum identifier may be reused by later frames or spans, so an
    unqualified global search by datum id is not sufficient.

    The synthetic lifecycle location therefore carries the context's active
    frame and span. The ordinary datum-over-span resolution law remains:

        datum.roles / datum.role
            override

        active span.roles / active span.role
            fallback
    """
    did = str(datum_id or "").strip()
    if not did:
        return []

    synthetic_event = {
        "kind": "datum_lifecycle_event_v1",
        "datum_id": did,
        "frame_id": str(
            ctx.get("current_frame_id")
            or ctx.get("frame_id")
            or ""
        ).strip(),
        "span_id": str(
            ctx.get("current_span")
            or ctx.get("current_span_id")
            or ctx.get("span_id")
            or ""
        ).strip(),
    }
    return _event_required_roles_from_ctx_v1(
        ctx,
        event=synthetic_event,
    )


def datum_readable_for_viewer_role(
    *,
    datum_id: str,
    role: Optional[str],
    context_candidates: Sequence[Mapping[str, Any]],
) -> bool:
    """Fail-closed read predicate for an action/event datum target."""
    if role is None:
        return True

    saw_role_surface = False
    for candidate in list(context_candidates or []):
        if not isinstance(candidate, Mapping):
            continue

        roles, _policy = role_sheet_from_context(candidate)
        if not roles:
            continue

        saw_role_surface = True
        validate_viewing_role(
            role=role,
            roles=roles,
        )
        required_roles = _datum_required_roles_from_ctx_v1(
            candidate,
            datum_id=datum_id,
        )
        if required_roles is None:
            continue

        return role_can_read_required_roles(
            roles,
            role=role,
            required_roles=required_roles,
        )

    return not saw_role_surface


def _datum_lifecycle_event_visibility_in_ctx_v1(
    ctx: Mapping[str, Any],
    *,
    event: Mapping[str, Any],
    role: Optional[str],
) -> Optional[bool]:
    """
    Tri-state event visibility for one candidate context.

    True/False means this ctx resolved the event datum. None means the ctx does
    not describe the event's datum location and another controller-loop ctx
    should be tried.
    """
    if not _is_datum_lifecycle_event_v1(event):
        return True

    roles, _policy = role_sheet_from_context(ctx)
    if not roles:
        return True

    validate_viewing_role(
        role=role,
        roles=roles,
    )

    required_roles = _event_required_roles_from_ctx_v1(
        ctx,
        event=event,
    )
    if required_roles is None:
        return None

    return role_can_read_required_roles(
        roles,
        role=role,
        required_roles=required_roles,
    )


def event_visible_for_viewer_role(
    event: Mapping[str, Any],
    *,
    role: Optional[str],
    context_candidates: Sequence[Mapping[str, Any]] = (),
) -> bool:
    """
    Return whether a source event may be released to one viewer role.

    Controller-loop events remain visible and have their payload.U projected by
    the caller. Datum lifecycle events are release-filtered by the role assigned
    to the event's datum. The canonical queue packet is never mutated.

    Unresolved guarded datum events are denied for named role-projected release.
    This is intentionally conservative: a missing event-time ctx must not become
    an accidental leak.
    """
    if role is None:
        return True

    if not _is_datum_lifecycle_event_v1(event):
        return True

    saw_candidate = False
    for candidate in list(context_candidates or []):
        if not isinstance(candidate, Mapping):
            continue

        saw_candidate = True
        verdict = _datum_lifecycle_event_visibility_in_ctx_v1(
            candidate,
            event=event,
            role=role,
        )
        if verdict is not None:
            return bool(verdict)

    if not saw_candidate:
        return False

    return False


def _ctx_multiframespec(
    ctx: Mapping[str, Any],
) -> Mapping[str, Any]:
    fs = ctx.get("multiframespec")
    if isinstance(fs, Mapping):
        return fs

    for key in (
        "pending_multiframespec",
        "form_spec",
        "_multiframespec",
    ):
        value = ctx.get(key)
        if isinstance(value, Mapping):
            return value

    return {}


def _ids_match(
    *,
    wanted: str,
    candidate: str,
) -> bool:
    wanted_id = str(wanted or "").strip()
    candidate_id = str(candidate or "").strip()

    if not wanted_id or not candidate_id:
        return False

    return (
        wanted_id == candidate_id
        or wanted_id.endswith(f":{candidate_id}")
        or wanted_id.endswith(f".{candidate_id}")
    )


def _active_frame_and_span(
    ctx: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    fs = _ctx_multiframespec(ctx)
    frames = fs.get("frames")

    if not isinstance(frames, list):
        return {}, {}

    current_frame_id = str(
        ctx.get("current_frame_id")
        or ctx.get("frame_id")
        or ""
    ).strip()
    current_span_id = str(
        ctx.get("current_span")
        or ctx.get("current_span_id")
        or ctx.get("span_id")
        or ""
    ).strip()

    candidate_frames: list[Mapping[str, Any]] = []

    for frame in frames:
        if not isinstance(frame, Mapping):
            continue

        frame_id = str(
            frame.get("id")
            or frame.get("name")
            or ""
        ).strip()

        if current_frame_id and frame_id == current_frame_id:
            candidate_frames.insert(0, frame)
        else:
            candidate_frames.append(frame)

    for frame in candidate_frames:
        spans = (
            frame.get("spans")
            or frame.get("fillspans")
            or []
        )
        if not isinstance(spans, list):
            continue

        for span in spans:
            if not isinstance(span, Mapping):
                continue

            span_id = str(
                span.get("id")
                or span.get("name")
                or ""
            ).strip()
            if _ids_match(
                wanted=current_span_id,
                candidate=span_id,
            ):
                return frame, span

    return {}, {}


def role_sheet_from_context(
    ctx: Mapping[str, Any],
) -> Tuple[RoleMap, RoleMismatchPolicy]:
    metadata = ctx.get(CTX_SESSION_METADATA)
    metadata = (
        metadata
        if isinstance(metadata, Mapping)
        else {}
    )

    roles = coerce_session_roles(
        metadata.get("roles")
    )
    policy = sanitize_role_mismatch_policy_for_metadata(
        metadata.get("role_mismatch_policy")
    )
    validate_role_modulation_surface(
        roles=roles,
        role_mismatch_policy=policy,
    )

    return roles, policy


def validate_viewing_role(
    *,
    role: Optional[str],
    roles: Mapping[str, Any],
) -> None:
    if role is not None and role not in roles:
        raise KeyError(
            f"role_viewing {role!r} not found in session roles"
        )


def _validate_policy_shape(
    policy: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Final accepted policy:

        {"default": "redacted", "role_modes": {"maker": "redacted"}}
    """
    out = sanitize_role_mismatch_policy_for_metadata(policy)

    default = out.get(
        "default",
        DEFAULT_OBFUSCATION_MODE,
    )
    if not isinstance(default, str) or not default.strip():
        raise ValueError(
            "role_mismatch_policy.default must be a non-empty string"
        )
    resolve_obfuscation_mode_spec(default)

    role_modes = out.get("role_modes")
    if isinstance(role_modes, Mapping):
        for role_name, mode_name in dict(role_modes).items():
            if not str(role_name or "").strip():
                raise ValueError(
                    "role_mismatch_policy.role_modes "
                    "has empty role name"
                )
            if (
                not isinstance(mode_name, str)
                or not mode_name.strip()
            ):
                raise ValueError(
                    f"role_mismatch_policy.role_modes[{role_name!r}] "
                    "must be a non-empty mode string"
                )
            resolve_obfuscation_mode_spec(mode_name)

    return out


def current_datum_role_assignments(
    ctx: Mapping[str, Any],
) -> list[Dict[str, Any]]:
    fs = _ctx_multiframespec(ctx)
    datums = fs.get("datums") or []
    datums_by_id: Dict[str, Mapping[str, Any]] = {}

    if isinstance(datums, list):
        for datum in datums:
            if not isinstance(datum, Mapping):
                continue

            datum_id = str(
                datum.get("id")
                or ""
            ).strip()
            if datum_id:
                datums_by_id[datum_id] = datum

    _frame, span = _active_frame_and_span(ctx)
    if not isinstance(span, Mapping) or not span:
        return []

    span_roles = _roles_list(
        roles_value=span.get("roles"),
        role_value=span.get("role"),
    )

    owns = (
        span.get("owns")
        or span.get("fields")
        or []
    )
    if not isinstance(owns, list):
        owns = []

    out: list[Dict[str, Any]] = []
    for raw_datum_id in owns:
        datum_id = str(raw_datum_id or "").strip()
        if not datum_id:
            continue

        datum = datums_by_id.get(datum_id) or {}
        datum_roles = (
            _roles_list(
                roles_value=datum.get("roles"),
                role_value=datum.get("role"),
            )
            if isinstance(datum, Mapping)
            else []
        )

        if datum_roles:
            roles = datum_roles
            source = "datum"
        else:
            roles = list(span_roles)
            source = "span" if span_roles else ""

        out.append(
            {
                "datum_id": datum_id,
                "roles": list(roles),
                "role_source": source,
            }
        )

    return out


def _augment_ctx_with_role_and_role_mismatch_info(
    ctx: Mapping[str, Any],
    *,
    role: Optional[str],
) -> Dict[str, Any]:
    out = deepcopy(dict(ctx or {}))

    metadata = dict(
        out.get(CTX_SESSION_METADATA)
        or {}
    )
    roles, raw_policy = role_sheet_from_context(out)
    policy = _validate_policy_shape(raw_policy)
    validate_role_modulation_surface(
        roles=roles,
        role_mismatch_policy=policy,
    )

    metadata["roles"] = roles
    metadata["role_mismatch_policy"] = policy
    out[CTX_SESSION_METADATA] = metadata

    validate_viewing_role(
        role=role,
        roles=roles,
    )
    read_role_names = sorted(
        effective_read_roles_for_role(
            roles,
            role=role,
        )
        if role is not None
        else set()
    )

    assignments = current_datum_role_assignments(out)

    guarded: list[Dict[str, Any]] = []
    mismatches: list[Dict[str, Any]] = []

    for assignment in assignments:
        row = dict(assignment)
        datum_id = str(
            row.get("datum_id")
            or ""
        )
        datum_roles = [
            str(value)
            for value in list(row.get("roles") or [])
            if str(value or "").strip()
        ]

        for required_role in datum_roles:
            if required_role not in roles:
                raise KeyError(
                    f"role {required_role!r} "
                    "not found in session roles"
                )

        row["datum_id"] = datum_id
        row["roles"] = datum_roles
        row["role_viewing"] = role
        row["read_role_names"] = list(read_role_names)
        row["read_allowed"] = role_can_read_required_roles(
            roles,
            role=role,
            required_roles=datum_roles,
        )
        row["write_allowed"] = role_can_write_required_roles(
            role=role,
            required_roles=datum_roles,
        )
        row["is_mismatch"] = bool(
            datum_roles
            and not row["read_allowed"]
        )
        row["obfuscation_mode"] = (
            role_mismatch_mode_for_viewer_role(
                policy,
                role=role,
            )
        )
        row["role_data_by_role"] = {
            role_name: dict(roles.get(role_name) or {})
            for role_name in datum_roles
        }

        if datum_roles:
            guarded.append(row)
        if row["is_mismatch"]:
            mismatches.append(row)

    out["role_assignments"] = assignments
    out[CTX_ROLE_MISMATCH_MODULATION_INFO] = {
        "kind": "role_mismatch_modulation_info_v1",
        "role_viewing": role,
        "read_role_names": list(read_role_names),
        "role_mismatch_policy": policy,
        "assignments": guarded,
        "mismatches": mismatches,
        "is_mismatch": bool(mismatches),
        "mismatch_datum_ids": [
            mismatch["datum_id"]
            for mismatch in mismatches
        ],
    }

    return out


def _redact_hidden_datums_from_kernel_source_object_v1(
    value: Any,
    *,
    hidden_by_datum_id: Mapping[str, Mapping[str, Any]],
) -> Any:
    """
    Redact hidden datum source copies from any ctx/provenance object in one pass.

    Previous implementation walked the entire ctx once per mismatch. That is
    safe but costly. This version walks once and checks a small hidden-id map.

    Joined universal-UI datum-state rows are recognized directly. This prevents
    their nested shell, fill, arguments, validation metadata, lifecycle state,
    and originating-step provenance from leaking if such a row is copied into
    another public metadata or provenance surface.
    """
    if isinstance(value, list):
        return [
            _redact_hidden_datums_from_kernel_source_object_v1(
                item,
                hidden_by_datum_id=hidden_by_datum_id,
            )
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            _redact_hidden_datums_from_kernel_source_object_v1(
                item,
                hidden_by_datum_id=hidden_by_datum_id,
            )
            for item in value
        ]

    if not isinstance(value, Mapping):
        return value

    m = dict(value)
    did = str(
        m.get("datum_id")
        or m.get("id")
        or ""
    ).strip()
    hidden = hidden_by_datum_id.get(did)

    is_universal_ui_datum_state = (
        str(m.get("kind") or "")
        == "universal_ui_datum_state_v1"
    )

    is_source_datum = bool(hidden) and (
        is_universal_ui_datum_state
        or "semantic_validation" in m
        or "originating_step" in m
        or "widget" in m
        or "micros" in m
        or "lifecycle" in m
        or "past_wires" in m
        or "system_flags" in m
        or "authoritative" in m
    )

    if is_source_datum:
        datum_roles = list(
            hidden.get("roles")
            or []
        )
        viewer_role = hidden.get("viewer_role")

        if is_universal_ui_datum_state:
            return {
                "kind": "role_mismatch_obfuscated_datum_v1",
                "datum_id": did,
                "role_mismatch_obfuscated": True,
                "obfuscated": True,
                "reason": "role_mismatch",
                "viewer_role": viewer_role,
                "required_roles": list(datum_roles),
                "is_authoritative": None,
                "is_pending": False,
            }

        return {
            "id": did,
            "title": "Unavailable",
            "micros": [],
            "tags": [],
            "roles": list(datum_roles),
            "required_roles": list(datum_roles),
            "viewer_role": viewer_role,
            "role_mismatch_obfuscated": True,
            "kind": "role_mismatch_obfuscated_datum_v1",
        }

    return {
        str(k): _redact_hidden_datums_from_kernel_source_object_v1(
            v,
            hidden_by_datum_id=hidden_by_datum_id,
        )
        for k, v in m.items()
    }


def _redact_mismatched_datums_from_metadata_provenance_v1(
    ctx: MutableMapping[str, Any],
    *,
    hidden_by_datum_id: Mapping[str, Mapping[str, Any]],
) -> None:
    """
    Redact all mismatched datum source copies anywhere in the public ctx.

    Runs once per public ctx release, not once per mismatched datum.
    """
    if not hidden_by_datum_id:
        return

    redacted = _redact_hidden_datums_from_kernel_source_object_v1(
        dict(ctx),
        hidden_by_datum_id=hidden_by_datum_id,
    )

    if not isinstance(redacted, Mapping):
        return

    ctx.clear()
    ctx.update(dict(redacted))


def _datum_id_from_last_error_key_v1(
    key: Any,
    *,
    known_datum_ids: set[str],
) -> Optional[str]:
    """
    Resolve a datum-addressed aggregate-error key.

    Engine semantic errors are normally keyed by macro datum id. Tolerate
    dotted/bracketed descendants as well so future validator detail can enlarge
    without creating a new release leak.

    Reserved aggregate keys such as ``__SPAN__`` are intentionally not datum
    keys and return None.
    """
    text = str(key or "").strip()
    if not text or text.startswith("__"):
        return None

    candidates = (
        text,
        text.split(".", 1)[0],
        text.split("[", 1)[0],
    )
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if normalized in known_datum_ids:
            return normalized

    return None


def _project_last_error_for_viewer_v1(
    ctx: MutableMapping[str, Any],
) -> None:
    """
    Release-filter the aggregate semantic error surface in public ``U``.

    ``last_error`` is one aggregate mapping keyed by datum. It is not a datum
    event and it is not attached to datum shells, so ordinary datum obfuscation
    does not remove it. This helper applies the already-computed assignment
    report to that final remaining datum-addressed surface.

    Laws:
      - canonical/raw ctx is never mutated (the caller operates on a copy);
      - readable and unguarded datum errors remain byte-equivalent;
      - unreadable datum errors are omitted;
      - reserved engine/span aggregate keys remain visible;
      - unknown non-reserved keys are denied conservatively;
      - an empty projected mapping normalizes to None.
    """
    raw_error = ctx.get("last_error")
    if not isinstance(raw_error, Mapping):
        return

    info = ctx.get(CTX_ROLE_MISMATCH_MODULATION_INFO)
    if not isinstance(info, Mapping):
        return

    all_assignments = [
        row
        for row in list(ctx.get("role_assignments") or [])
        if isinstance(row, Mapping)
    ]
    guarded_assignments = {
        str(row.get("datum_id") or "").strip(): row
        for row in list(info.get("assignments") or [])
        if (
            isinstance(row, Mapping)
            and str(row.get("datum_id") or "").strip()
        )
    }
    known_datum_ids = {
        str(row.get("datum_id") or "").strip()
        for row in all_assignments
        if str(row.get("datum_id") or "").strip()
    }

    readable_datum_ids: set[str] = set()
    for row in all_assignments:
        datum_id = str(
            row.get("datum_id")
            or ""
        ).strip()
        if not datum_id:
            continue

        required_roles = [
            str(value)
            for value in list(row.get("roles") or [])
            if str(value or "").strip()
        ]
        if not required_roles:
            readable_datum_ids.add(datum_id)
            continue

        guarded = guarded_assignments.get(datum_id)
        if (
            isinstance(guarded, Mapping)
            and bool(guarded.get("read_allowed"))
        ):
            readable_datum_ids.add(datum_id)

    projected: Dict[str, Any] = {}
    for raw_key, value in raw_error.items():
        key = str(raw_key)
        if key.startswith("__"):
            projected[key] = deepcopy(value)
            continue

        datum_id = _datum_id_from_last_error_key_v1(
            key,
            known_datum_ids=known_datum_ids,
        )
        if datum_id in readable_datum_ids:
            projected[key] = deepcopy(value)

    ctx["last_error"] = projected or None


def _datum_state_row_v1(
    ctx: Mapping[str, Any],
    *,
    datum_id: str,
) -> Mapping[str, Any]:
    for row in list(
        ctx.get("datum_states_on_this_span") or []
    ):
        if not isinstance(row, Mapping):
            continue
        if (
            str(row.get("datum_id") or "")
            == str(datum_id)
        ):
            return row
    return {}


def _bounded_activity_row_v1(
    ctx: Mapping[str, Any],
    *,
    datum_id: str,
) -> Dict[str, Any]:
    row = _datum_state_row_v1(
        ctx,
        datum_id=datum_id,
    )
    lifecycle = row.get("lifecycle")
    lifecycle = (
        lifecycle
        if isinstance(lifecycle, Mapping)
        else {}
    )
    runtime = lifecycle.get("runtime")
    runtime = (
        runtime
        if isinstance(runtime, Mapping)
        else {}
    )

    messages = runtime.get("messages")
    proc_notes = runtime.get("proc_notes")

    return {
        "datum_id": str(datum_id),
        "has_fill": bool(
            row.get("has_fill", False)
        ),
        "is_pending": bool(
            row.get("is_pending", False)
        ),
        "lifecycle_status": (
            None
            if runtime.get("status") is None
            else str(runtime.get("status"))
        ),
        "reexplode_count": int(
            runtime.get("reexplode_count") or 0
        ),
        "message_count": (
            len(messages)
            if isinstance(messages, list)
            else 0
        ),
        "proc_note_count": (
            len(proc_notes)
            if isinstance(proc_notes, list)
            else 0
        ),
    }


def _role_mismatch_receipt_v1(
    ctx_before_obfuscation: Mapping[str, Any],
    *,
    role: Optional[str],
    mismatches: Sequence[Mapping[str, Any]],
    mode_specs: Sequence[ObfuscationModeSpec],
) -> Optional[Dict[str, Any]]:
    if not mismatches:
        return None

    field_sets = {
        spec.receipt_fields
        for spec in mode_specs
    }
    mode_names = {
        spec.name
        for spec in mode_specs
    }
    if len(field_sets) != 1 or len(mode_names) != 1:
        raise RuntimeError(
            "one projected U must resolve exactly one mismatch mode"
        )

    fields = next(iter(field_sets))
    mode_name = next(iter(mode_names))
    if not fields:
        return None

    rows = [
        dict(row)
        for row in mismatches
    ]
    receipt: Dict[str, Any] = {
        "kind": "role_mismatch_activity_receipt_v1",
        "mode": mode_name,
        "viewer_role": role,
        "obfuscated_count": len(rows),
    }

    if RECEIPT_IDENTITY in fields:
        receipt["identity"] = [
            {
                "datum_id": str(
                    row.get("datum_id") or ""
                ),
            }
            for row in rows
        ]

    if RECEIPT_OWNERSHIP in fields:
        receipt["ownership"] = [
            {
                "datum_id": str(
                    row.get("datum_id") or ""
                ),
                "write_roles": [
                    str(value)
                    for value in list(
                        row.get("roles") or []
                    )
                    if str(value or "").strip()
                ],
            }
            for row in rows
        ]

    if RECEIPT_ACTIVITY in fields:
        activity = [
            _bounded_activity_row_v1(
                ctx_before_obfuscation,
                datum_id=str(
                    row.get("datum_id") or ""
                ),
            )
            for row in rows
        ]

        if RECEIPT_IDENTITY in fields:
            receipt["activity"] = activity
        else:
            receipt["activity"] = {
                "with_fill_count": sum(
                    bool(row["has_fill"])
                    for row in activity
                ),
                "pending_count": sum(
                    bool(row["is_pending"])
                    for row in activity
                ),
                "reexplode_count": sum(
                    int(row["reexplode_count"])
                    for row in activity
                ),
                "message_count": sum(
                    int(row["message_count"])
                    for row in activity
                ),
                "proc_note_count": sum(
                    int(row["proc_note_count"])
                    for row in activity
                ),
            }

    return receipt


def _obfuscate_ctx_for_specific_viewer_role(
    ctx: Mapping[str, Any],
    *,
    role: Optional[str],
) -> Dict[str, Any]:
    """
    Return public role-modulated ctx for one viewer role.

    Read authority:
      ``role=None`` is the privileged canonical read used by the engine,
      highest façade, canonical event queue, and canonical test/reporting
      surfaces. It is not an anonymous named viewer.

      Canonical release returns a detached deep copy and applies neither
      current-frame projection nor role-mismatch augmentation/obfuscation.

      Write-side role=None behavior is unchanged: submission authorization
      still denies writes to guarded datums.

    Hot path:
      roleless sessions with no role surface are no-ops and must not pay the
      role-modulation cost. This keeps undo/redo/query complexity tests from
      spending their runtime budget on defensive ctx copying/scanning.
    """
    if role is None:
        return deepcopy(dict(ctx or {}))

    if _ctx_role_surface_is_inert_for_viewer(
        ctx,
        role=role,
    ):
        return _copy_for_public_noop_v1(ctx)

    scoped = deepcopy(dict(ctx or {}))
    constrain_ctx_to_current_frame_scope(scoped)

    out = _augment_ctx_with_role_and_role_mismatch_info(
        scoped,
        role=role,
    )
    info = out.get(
        CTX_ROLE_MISMATCH_MODULATION_INFO
    )

    if not isinstance(info, Mapping):
        return out

    hidden_by_datum_id: Dict[str, Dict[str, Any]] = {}
    mode_specs: list[ObfuscationModeSpec] = []
    receipt_source_U = deepcopy(out)

    for row in list(info.get("mismatches") or []):
        if not isinstance(row, Mapping):
            continue

        datum_id = str(
            row.get("datum_id")
            or ""
        ).strip()
        if not datum_id:
            continue

        datum_roles = [
            str(value)
            for value in list(row.get("roles") or [])
            if str(value or "").strip()
        ]

        mode_name = str(
            row.get("obfuscation_mode")
            or DEFAULT_OBFUSCATION_MODE
        )
        mode_spec = resolve_obfuscation_mode_spec(
            mode_name
        )
        mode_specs.append(mode_spec)

        addresses = collect_datum_ctx_addresses(
            out,
            datum_id=datum_id,
        )

        mode_spec.transform(
            out,
            datum_id=datum_id,
            viewer_role=role,
            datum_roles=datum_roles,
            addresses=addresses,
            reason="role_mismatch",
        )

        hidden_by_datum_id[datum_id] = {
            "roles": list(datum_roles),
            "viewer_role": role,
        }

    _redact_mismatched_datums_from_metadata_provenance_v1(
        out,
        hidden_by_datum_id=hidden_by_datum_id,
    )

    _project_last_error_for_viewer_v1(out)

    receipt = _role_mismatch_receipt_v1(
        receipt_source_U,
        role=role,
        mismatches=[
            row
            for row in list(
                info.get("mismatches") or []
            )
            if isinstance(row, Mapping)
        ],
        mode_specs=mode_specs,
    )
    final_info = out.get(
        CTX_ROLE_MISMATCH_MODULATION_INFO
    )
    if isinstance(final_info, dict):
        final_info["receipt"] = receipt

    return out


def _submitted_datum_ids(
    fill: Optional[Mapping[str, Any]],
    signal: Optional[Mapping[str, Any]],
) -> set[str]:
    submitted: set[str] = set()

    if fill is not None:
        if not isinstance(fill, Mapping):
            raise TypeError(
                "fill must be a mapping/dict when provided"
            )
        submitted.update(
            str(key).split(".", 1)[0]
            for key in fill.keys()
            if str(key or "").strip()
        )

    if signal is not None:
        if not isinstance(signal, Mapping):
            raise TypeError(
                "signal must be a mapping/dict when provided"
            )
        datum_id = str(
            signal.get("datum_id")
            or ""
        ).strip()
        if datum_id:
            submitted.add(datum_id)

    return submitted


def _this_viewer_role_is_allowed_this_submission(
    ctx: Mapping[str, Any],
    *,
    role: Optional[str],
    fill: Optional[Mapping[str, Any]] = None,
    signal: Optional[Mapping[str, Any]] = None,
) -> bool:
    """
    Return True iff this viewer role may submit the provided fill and/or signal.

    Internal/non-datum stepping is allowed. Actual datum writes are checked
    datum-by-datum.

    Fast path:
      empty submissions in roleless sessions are semantic no-ops and should not
      build role-assignment reports.
    """
    submitted = _submitted_datum_ids(
        fill,
        signal,
    )

    if (
        not submitted
        and _ctx_role_surface_is_inert_for_viewer(
            ctx,
            role=role,
        )
    ):
        return True

    if not submitted:
        _augment_ctx_with_role_and_role_mismatch_info(
            ctx,
            role=role,
        )
        return True

    augmented = _augment_ctx_with_role_and_role_mismatch_info(
        ctx,
        role=role,
    )
    info = augmented.get(
        CTX_ROLE_MISMATCH_MODULATION_INFO
    )
    write_blocked = set()

    if isinstance(info, Mapping):
        for row in list(info.get("assignments") or []):
            if not isinstance(row, Mapping):
                continue

            datum_id = str(
                row.get("datum_id")
                or ""
            )
            if (
                datum_id
                and not bool(
                    row.get("write_allowed", False)
                )
            ):
                write_blocked.add(datum_id)

    blocked = sorted(
        submitted.intersection(write_blocked)
    )
    if blocked:
        raise PermissionError(
            "role write policy blocks submission for datum id(s): "
            + ", ".join(blocked)
        )

    return True


__all__ = [
    "RoleMap",
    "RoleMismatchPolicy",
    "current_datum_role_assignments",
    "datum_readable_for_viewer_role",
    "event_visible_for_viewer_role",
    "role_sheet_from_context",
    "validate_viewing_role",
    "_augment_ctx_with_role_and_role_mismatch_info",
    "_obfuscate_ctx_for_specific_viewer_role",
    "_project_last_error_for_viewer_v1",
    "_this_viewer_role_is_allowed_this_submission",
]