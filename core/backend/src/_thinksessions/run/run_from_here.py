from __future__ import annotations

"""Highest authoring run facade for authored live and black-box sessions.

The existing live-session surface remains unchanged. This module also provides
``run_funked_black_box_from_program`` for one-shot, fully-funked P/SM/C runs.
"""

import json
from typing import Any, Dict, Mapping, Optional

from _thinkengine._engine_interactive_flow_controller import UserAction
from _thinksessions.libs_read_write_augmented.rolebasedRWmodulatorTM.obfuscation_api import role_modulation
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
)
from _thinkengine.runme_optimized_queryable.facade_rolemodulated import (
    create_core_session_from_program as _core_create_session_from_program,
    delete_core_session as _core_delete_session,
    dispatch_live_session_action as _core_dispatch_live_session_action,
    get_live_session_context,
    get_live_session_events as _core_get_live_session_events,
    get_live_session_latest_event_seq as _core_get_live_session_latest_event_seq,
    get_service_public_session_api,
    normalize_service_role,
    render_current_session_state as _core_render_current_session_state,
)
from _thinksessions.sesh_metadata.sesh_metadata_surface import (
    build_interactive_session_metadata,
)
from _thinksessions.sesh_metadata.sesh_metadata_surface_puppeteering import (
    bind_session_metadata_symbols_v1,
    route_puppeteering_overlay_to_symbol_surfaces_v1,
)
from _thinksessions.run._dispatch_staleness import (
    check_dispatch_staleness,
    dispatch_committed_writes_v1,
    dispatch_rejection_packet_v1,
    forget_dispatch_staleness_session_v1,
    record_successful_dispatch_v1,
    resolve_canonical_write_targets_v1,
    serialized_dispatch_boundary_v1,
)
from _thinksessions.run._funked_black_box import (
    BLACK_BOX_ERROR_REPORT_KIND_V1,
    BLACK_BOX_RESULT_KIND_V1,
    FunkedBlackBoxContractError,
    FunkedBlackBoxRunIncompleteError,
    validate_funked_black_box_contract_v1,
)
from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    EXPLOSION_EVENTS_CALLBACK_KEY,
    provisional_event_copy_v1,
)
from _thinksessions.sesh_metadata.__sesh_meta_chainreactionTM_config_surface import (
    FUNKT_M_CONFIG_KEY,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM._errors import (
    FunkUnanticipatedDatumRoleRuntimeError,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM._runtime import (
    run_chain_reaction_after_initial_dispatch,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM._static import (
    normalize_chainreactiontm_config_from_session_metadata,
)


_UNSET = object()


def _require_dispatcher_identity_id_v1(value: Any) -> str:
    identity_id = str(value or "").strip()
    if not identity_id:
        identity_id = ""
    return identity_id


def _funked_dispatcher_identity_id_v1(
    *,
    initial_identity_id: str,
    generated_role: Optional[str],
) -> str:
    initial = _require_dispatcher_identity_id_v1(initial_identity_id)
    normalized_role = normalize_service_role(generated_role)
    role_name = normalized_role or "roleless"
    return f"funkedauto-{role_name}-{initial}"


# =============================================================================
# Live/provisional callback delivery contract
# =============================================================================


class _ExplosionEventsLiveCallbackV1:
    """Project canonical datum events back onto the epsilon callback surface.

    Lower engine machinery may have already recorded an event and therefore be
    holding the canonical queued packet with ``event_seq`` by the time it calls
    the threaded explosion callback.  ``run_from_here`` is the public membrane
    that separates those two surfaces: the callback remains provisional and
    source-shaped, while the canonical queue remains the sole owner of the
    sequence cursor.

    Some callback objects (notably the web provisional publisher) also expose
    ``observe_unmodulated_context_v1``.  Forwarding that optional hook is
    required so role projection can still release datum events once a suitable
    raw U becomes available.
    """

    __slots__ = ("_callback",)

    def __init__(self, callback: Any) -> None:
        self._callback = callback

    def __call__(self, event: Mapping[str, Any]) -> Any:
        return self._callback(provisional_event_copy_v1(event))

    def observe_unmodulated_context_v1(
        self,
        U: Mapping[str, Any],
    ) -> Any:
        observer = getattr(
            self._callback,
            "observe_unmodulated_context_v1",
            None,
        )
        if callable(observer):
            return observer(U)
        return None


def _threaded_callbacks_for_live_delivery_v1(
    threaded_callbacks: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return callbacks with the datum explosion epsilon law enforced.

    Only the explosion callback is adapted. Controller callback semantics are
    intentionally untouched here because controller events have their own
    trident/U/A contract. The adapter is idempotent so chain-reaction dispatches
    can safely pass the prepared mapping through repeated generated dispatches.
    """
    if threaded_callbacks is None:
        return None

    out = dict(threaded_callbacks)
    callback = out.get(EXPLOSION_EVENTS_CALLBACK_KEY)
    if callable(callback) and not isinstance(
        callback,
        _ExplosionEventsLiveCallbackV1,
    ):
        out[EXPLOSION_EVENTS_CALLBACK_KEY] = _ExplosionEventsLiveCallbackV1(
            callback
        )
    return out


# =============================================================================
# Dead-JSON helpers and static ThinkProgram inspection
# =============================================================================


def _dead_json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def describe_think_program(
    *,
    program: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(program, Mapping):
        raise TypeError("describe_think_program requires a mapping program")

    p = dict(program)
    run = p.get("run")
    run = run if isinstance(run, Mapping) else {}
    program_row = run.get("program")
    program_row = program_row if isinstance(program_row, Mapping) else {}
    info = program_row.get("info")
    info = info if isinstance(info, Mapping) else {}
    widgets_raw = program_row.get("widgets")
    widgets_raw = widgets_raw if isinstance(widgets_raw, Mapping) else {}
    flow_raw = program_row.get("flow")
    flow_raw = flow_raw if isinstance(flow_raw, list) else []

    widget_rows: list[Dict[str, Any]] = []
    role_names: set[str] = set()
    for widget_id, raw_widget in widgets_raw.items():
        row = raw_widget if isinstance(raw_widget, Mapping) else {}
        roles = [
            str(role)
            for role in list(row.get("roles") or [])
            if str(role or "").strip()
        ]
        role_names.update(roles)
        widget_rows.append(
            {
                "id": str(widget_id),
                "widget": row.get("widget"),
                "title": row.get("title"),
                "roles": roles,
                "authoritative": bool(row.get("authoritative", False)),
                "tags": list(row.get("tags") or []),
            }
        )

    flow_rows: list[Dict[str, Any]] = []
    for index, raw_step in enumerate(flow_raw):
        step = raw_step if isinstance(raw_step, Mapping) else {}
        widgets = [
            str(widget_id)
            for widget_id in list(step.get("widgets") or [])
            if str(widget_id or "").strip()
        ]
        flow_rows.append(
            {
                "index": index,
                "id": str(step.get("id") or ""),
                "title": step.get("title"),
                "widgets": widgets,
                "authoritative": list(step.get("authoritative") or []),
            }
        )

    return _dead_json_copy(
        {
            "kind": "think_program_static_description_v1",
            "program_kind": p.get("kind"),
            "surface_version": p.get("surface_version"),
            "id": info.get("id"),
            "title": info.get("title"),
            "description": info.get("description"),
            "counts": {
                "widgets": len(widget_rows),
                "flow_steps": len(flow_rows),
                "roles": len(role_names),
            },
            "roles": sorted(role_names),
            "widgets": widget_rows,
            "flow": flow_rows,
        }
    )


# =============================================================================
# Launch-surface resolution, creation, deletion, render, bounded reports
# =============================================================================


def _resolve_live_session_launch_surfaces_v1(
    *,
    program: Any,
    initial_parameter_overrides: Optional[Mapping[str, Any]],
    session_metadata: Optional[Mapping[str, Any]],
    roles: Optional[Mapping[str, Any]],
    role_mismatch_policy: Optional[Mapping[str, Any]],
) -> tuple[Any, Dict[str, Any]]:
    """Resolve the effective P and SM exactly once before runtime allocation."""
    metadata_source = dict(session_metadata or {})
    overlay_is_empty = (
        initial_parameter_overrides is None
        or (
            isinstance(initial_parameter_overrides, Mapping)
            and not initial_parameter_overrides
        )
    )

    if overlay_is_empty:
        effective_program = program
        effective_metadata_source = metadata_source
    else:
        if not isinstance(program, Mapping):
            raise TypeError(
                "joint puppeteering requires a mapping ThinkProgram surface"
            )
        routed = route_puppeteering_overlay_to_symbol_surfaces_v1(
            surfaces={
                "program": program,
                "session_metadata": metadata_source,
            },
            initial_parameter_overrides=initial_parameter_overrides,
        )
        effective_program = routed["program"]
        effective_metadata_source = routed["session_metadata"]

    metadata = bind_session_metadata_symbols_v1(effective_metadata_source)
    if roles is not None or role_mismatch_policy is not None:
        metadata = build_interactive_session_metadata(
            ui_opts=metadata,
            roles=(dict(roles or {}) or None),
            role_mismatch_policy=(dict(role_mismatch_policy or {}) or None),
        )

    return effective_program, dict(metadata or {})


def _create_live_session_from_resolved_surfaces_v1(
    *,
    program: Any,
    program_language: str,
    resolved_session_metadata: Mapping[str, Any],
) -> Dict[str, Any]:
    return dict(
        _core_create_session_from_program(
            program=program,
            program_language=program_language,
            initial_parameter_overrides={},
            session_metadata=dict(resolved_session_metadata or {}),
        )
        or {}
    )


def create_live_session_from_program(
    *,
    program: Any,
    program_language: str,
    initial_parameter_overrides: Optional[Mapping[str, Any]] = None,
    session_metadata: Optional[Mapping[str, Any]] = None,
    roles: Optional[Mapping[str, Any]] = None,
    role_mismatch_policy: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    effective_program, metadata = _resolve_live_session_launch_surfaces_v1(
        program=program,
        initial_parameter_overrides=initial_parameter_overrides,
        session_metadata=session_metadata,
        roles=roles,
        role_mismatch_policy=role_mismatch_policy,
    )
    return _create_live_session_from_resolved_surfaces_v1(
        program=effective_program,
        program_language=program_language,
        resolved_session_metadata=metadata,
    )


def delete_live_session(*, session_id: str) -> Dict[str, Any]:
    sid = str(session_id)
    deleted = dict(_core_delete_session(sid) or {})
    forget_dispatch_staleness_session_v1(sid)
    return deleted


def render_live_session_state(
    *,
    session_id: str,
    role: Optional[str] = None,
    include_ctx: bool = False,
) -> Dict[str, Any]:
    return dict(
        _core_render_current_session_state(
            session_id=str(session_id),
            role=normalize_service_role(role),
            include_ctx=include_ctx,
        )
        or {}
    )


def get_live_session_current_report(*, session_id: str) -> Dict[str, Any]:
    return dict(get_service_public_session_api().current_report(str(session_id)) or {})


def get_live_session_progress_report(*, session_id: str) -> Dict[str, Any]:
    return dict(get_service_public_session_api().progress_report(str(session_id)) or {})


def get_live_session_outputs_report(*, session_id: str) -> Dict[str, Any]:
    return dict(get_service_public_session_api().outputs_report(str(session_id)) or {})


def query_live_session(
    *,
    session_id: str,
    query_kind: str,
    query: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return dict(
        get_service_public_session_api().query_session(
            str(session_id),
            query_kind=str(query_kind),
            query=dict(query or {}),
        )
        or {}
    )


# =============================================================================
# Event reads
# =============================================================================


def _event_seq(event: Mapping[str, Any]) -> int:
    raw = event.get("event_seq")
    if isinstance(raw, bool):
        raise TypeError("event_seq must be an integer, not bool")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"live event is missing a valid event_seq: {raw!r}") from exc
    if value < 1:
        raise ValueError(f"event_seq must be positive; got {value}")
    return value


def _normalized_limit(limit: Optional[int]) -> Optional[int]:
    if limit is None:
        return None
    if isinstance(limit, bool):
        raise TypeError("limit must be an integer, not bool")
    value = int(limit)
    if value < 0:
        raise ValueError("limit must be >= 0")
    return value


def get_live_session_events(
    *,
    session_id: str,
    role: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[Dict[str, Any]]:
    return _core_get_live_session_events(
        session_id=str(session_id),
        role=normalize_service_role(role),
        limit=_normalized_limit(limit),
    )


def get_live_session_latest_event_seq(*, session_id: str) -> int:
    return _core_get_live_session_latest_event_seq(session_id=str(session_id))


def _seq_ranges_v1(values: list[int]) -> list[Dict[str, int]]:
    if not values:
        return []
    out: list[Dict[str, int]] = []
    start = previous = int(values[0])
    for raw in values[1:]:
        value = int(raw)
        if value == previous + 1:
            previous = value
            continue
        out.append({"from_event_seq": start, "to_event_seq": previous})
        start = previous = value
    out.append({"from_event_seq": start, "to_event_seq": previous})
    return out


def get_live_session_events_since(
    *,
    session_id: str,
    role: Optional[str] = None,
    after_event_seq: Optional[int] = None,
    limit: Optional[int] = None,
    identity_id: Optional[str] = None,
) -> Dict[str, Any]:
    sid = str(session_id)
    normalized_role = normalize_service_role(role)
    page_limit = _normalized_limit(limit)

    if after_event_seq is None:
        after = 0
    else:
        if isinstance(after_event_seq, bool):
            raise TypeError("after_event_seq must be an integer, not bool")
        after = int(after_event_seq)
        if after < 0:
            raise ValueError("after_event_seq must be >= 0")

    canonical = get_live_session_events(session_id=sid, role=None, limit=None)
    canonical_seqs = [_event_seq(event) for event in canonical]
    earliest = canonical_seqs[0] if canonical_seqs else 0
    latest = get_live_session_latest_event_seq(session_id=sid)

    projected = get_live_session_events(
        session_id=sid,
        role=normalized_role,
        limit=None,
    )
    projected_by_seq = {
        _event_seq(event): dict(event)
        for event in projected
        if _event_seq(event) > after
    }

    visible: list[Dict[str, Any]] = []
    hidden_seqs: list[int] = []
    scanned_through = after
    if page_limit != 0:
        for event in canonical:
            seq = _event_seq(event)
            if seq <= after:
                continue
            scanned_through = seq
            projected_event = projected_by_seq.get(seq)
            if projected_event is None:
                hidden_seqs.append(seq)
            else:
                visible.append(projected_event)
            if page_limit is not None and len(visible) >= page_limit:
                break

    return {
        "kind": "live_session_events_since_v1",
        "session_id": sid,
        "identity_id": None if identity_id is None else str(identity_id),
        "role": normalized_role,
        "after_event_seq": after,
        "session_earliest_event_seq": earliest,
        "session_latest_event_seq": latest,
        "scanned_through_event_seq": scanned_through,
        "next_after_event_seq": scanned_through,
        "canonical_gap_detected": bool(
            canonical_seqs and after > 0 and after < earliest - 1
        ),
        "visibility_receipt": {
            "kind": "live_session_event_visibility_receipt_v1",
            "role": normalized_role,
            "scanned_from_event_seq_exclusive": after,
            "scanned_through_event_seq": scanned_through,
            "hidden_event_count": len(hidden_seqs),
            "hidden_event_seq_ranges": _seq_ranges_v1(hidden_seqs),
            "reason": "role_projection" if hidden_seqs else "none",
        },
        "events": visible,
    }


# =============================================================================
# Chain-reaction helpers
# =============================================================================


def _session_metadata_for_chainreactiontm_config_validation(
    session_id: str,
) -> Dict[str, Any]:
    raw_ctx = get_concrete_session_api().get_session_context(str(session_id))
    if not isinstance(raw_ctx, Mapping):
        return {}
    session_metadata = raw_ctx.get("session_metadata")
    return dict(session_metadata or {}) if isinstance(session_metadata, Mapping) else {}


def _is_step_action(action: str | UserAction) -> bool:
    if isinstance(action, UserAction):
        return action is UserAction.STEP
    text = str(action or "")
    if text == UserAction.STEP.name:
        return True
    try:
        return UserAction(text) is UserAction.STEP
    except Exception:
        return False


def _packet_with_chainreactiontm_stop(
    packet: Mapping[str, Any],
    *,
    enabled: bool,
    stopped_reason: str,
) -> Dict[str, Any]:
    out = dict(packet or {})
    out["chainreactionTM_receipt"] = {
        "kind": "chainreactionTM_chain_reaction_receipt_v1",
        "enabled": bool(enabled),
        "stopped_reason": str(stopped_reason),
    }
    return out


def _looks_like_unknown_session_role_keyerror(exc: KeyError) -> bool:
    text = str(exc)
    return "not found in session roles" in text and "role" in text


def _normalize_call_chainreactiontm_config(
    session_metadata: Mapping[str, Any],
    *,
    chainreactionTM_config: Any,
):
    if chainreactionTM_config is _UNSET:
        return normalize_chainreactiontm_config_from_session_metadata(session_metadata)
    if chainreactionTM_config is None:
        disabled_meta = dict(session_metadata or {})
        disabled_meta[FUNKT_M_CONFIG_KEY] = None
        return normalize_chainreactiontm_config_from_session_metadata(disabled_meta)
    if not isinstance(chainreactionTM_config, Mapping):
        return normalize_chainreactiontm_config_from_session_metadata(
            session_metadata,
            override=chainreactionTM_config,
        )
    base_global = (
        dict(session_metadata.get(FUNKT_M_CONFIG_KEY) or {})
        if isinstance(session_metadata.get(FUNKT_M_CONFIG_KEY), Mapping)
        else {}
    )
    return normalize_chainreactiontm_config_from_session_metadata(
        session_metadata,
        override={**base_global, **dict(chainreactionTM_config)},
    )


def _latest_canonical_event_seq(session_id: str) -> int:
    return get_live_session_latest_event_seq(session_id=str(session_id))


def _attach_direct_dispatch_receipt(
    packet: Mapping[str, Any],
    *,
    before_event_seq: int,
    after_event_seq: int,
    identity_id: str,
    role: Optional[str],
) -> Dict[str, Any]:
    out = dict(packet or {})
    systematic_error = isinstance(out.get("system_error"), Mapping)
    out["kind"] = "live_session_dispatch_result_v1"
    out["ok"] = not systematic_error
    out["applied"] = True
    out["rejected"] = False
    out["rejection_kind"] = None
    out["events_only"] = False
    out["dispatcher_identity_id"] = str(identity_id)
    out["dispatcher_role"] = normalize_service_role(role)
    out["dispatch_concurrency"] = {
        "kind": "live_session_dispatch_concurrency_receipt_v1",
        "applied": True,
        "rejected": False,
        "stale_policy": "highest_facade_optional_cursor_v1",
        "before_event_seq": int(before_event_seq),
        "after_event_seq": int(after_event_seq),
        "idempotent_replay": False,
        "guarding": "per_session_serialized_highest_facade",
    }
    return out


def _events_only_dispatch_receipt_v1(
    packet: Mapping[str, Any],
    *,
    chain: bool,
) -> Dict[str, Any]:
    out = {
        "kind": (
            "live_session_events_only_chain_dispatch_receipt_v1"
            if chain
            else "live_session_events_only_dispatch_receipt_v1"
        ),
        "session_id": str(packet.get("session_id") or ""),
        "dispatcher_identity_id": packet.get("dispatcher_identity_id"),
        "dispatcher_role": packet.get("dispatcher_role"),
        "events_only": True,
        "ok": bool(packet.get("ok", True)),
        "applied": bool(packet.get("applied", True)),
        "rejected": bool(packet.get("rejected", False)),
        "rejection_kind": packet.get("rejection_kind"),
        "dispatch_outcome": packet.get("dispatch_outcome"),
        "write_committed": bool(packet.get("write_committed", False)),
        "event_kind": packet.get("event_kind"),
        "finished": packet.get("finished"),
        "last_error": packet.get("last_error"),
        "system_error": packet.get("system_error"),
    }
    if "ctx_report" in packet:
        out["ctx_report"] = packet.get("ctx_report")
    if "chainreactionTM_receipt" in packet:
        out["chainreactionTM_receipt"] = packet.get("chainreactionTM_receipt")
    if "dispatch_concurrency" in packet:
        out["dispatch_concurrency"] = packet.get("dispatch_concurrency")
    if "dispatch_staleness" in packet:
        out["dispatch_staleness"] = packet.get("dispatch_staleness")
    return out


def _signal_or_none(
    user_signal: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    return dict(user_signal) if isinstance(user_signal, Mapping) else None


def _dispatch_direct_inside_boundary(
    *,
    session_id: str,
    action: str | UserAction,
    user_fill: Optional[Mapping[str, Any]],
    user_signal: Optional[Mapping[str, Any]],
    role: Optional[str],
    identity_id: str,
    threaded_callbacks: Optional[Mapping[str, Any]],
    my_current_event_seq_number: Optional[int],
    staleness_state: Any,
    dispatch_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    sid = str(session_id)
    normalized_identity_id = _require_dispatcher_identity_id_v1(identity_id)
    normalized_role = normalize_service_role(role)
    delivery_callbacks = _threaded_callbacks_for_live_delivery_v1(
        threaded_callbacks
    )

    raw_before_U = get_concrete_session_api().get_session_context(sid)
    if not isinstance(raw_before_U, Mapping):
        raise TypeError("highest facade requires a mapping session context")

    role_modulation.assert_submission_allowed(
        raw_before_U,
        role=normalized_role,
        fill=user_fill,
        signal=user_signal,
    )

    before_scope, targets = resolve_canonical_write_targets_v1(
        raw_before_U,
        user_fill=user_fill,
        user_signal=user_signal,
    )
    before = _latest_canonical_event_seq(sid)
    staleness = check_dispatch_staleness(
        my_current_event_seq_number=my_current_event_seq_number,
        actual_latest_event_seq=before,
        targets=targets,
        state=staleness_state,
    )
    if staleness["outcome"] == "rejected":
        return dispatch_rejection_packet_v1(
            session_id=sid,
            staleness_receipt=staleness,
        )

    packet = _core_dispatch_live_session_action(
        session_id=sid,
        action=action,
        user_fill=dict(user_fill or {}),
        user_signal=_signal_or_none(user_signal),
        role=normalized_role,
        identity_id=normalized_identity_id,
        threaded_callbacks=delivery_callbacks,
        dispatch_context=(
            dict(dispatch_context)
            if isinstance(dispatch_context, Mapping)
            else None
        ),
    )

    after = _latest_canonical_event_seq(sid)
    out = _attach_direct_dispatch_receipt(
        dict(packet or {}),
        before_event_seq=before,
        after_event_seq=after,
        identity_id=normalized_identity_id,
        role=normalized_role,
    )
    out["dispatch_staleness"] = dict(staleness)

    raw_after_U = get_concrete_session_api().get_session_context(sid)
    if not isinstance(raw_after_U, Mapping):
        raise TypeError("highest facade requires a mapping session context")
    after_scope, _unused_after_targets = resolve_canonical_write_targets_v1(
        raw_after_U,
        user_fill=None,
        user_signal=None,
    )

    systematic_error = isinstance(out.get("system_error"), Mapping)
    committed_writes = (
        False
        if systematic_error
        else dispatch_committed_writes_v1(out, targets=targets)
    )
    out["write_committed"] = bool(committed_writes)
    if systematic_error:
        out["dispatch_outcome"] = "system_error"
    elif committed_writes or not targets:
        out["dispatch_outcome"] = "applied"
    else:
        out["dispatch_outcome"] = "semantic_rejected"

    record_successful_dispatch_v1(
        state=staleness_state,
        before_scope=before_scope,
        after_scope=after_scope,
        after_event_seq=after,
        targets=targets,
        committed_writes=committed_writes,
    )
    return out


def _dispatch_direct(
    *,
    session_id: str,
    action: str | UserAction,
    user_fill: Optional[Mapping[str, Any]],
    user_signal: Optional[Mapping[str, Any]],
    role: Optional[str],
    identity_id: str,
    threaded_callbacks: Optional[Mapping[str, Any]],
    my_current_event_seq_number: Optional[int],
) -> Dict[str, Any]:
    sid = str(session_id)
    with serialized_dispatch_boundary_v1(sid) as staleness_state:
        return _dispatch_direct_inside_boundary(
            session_id=sid,
            action=action,
            user_fill=user_fill,
            user_signal=user_signal,
            role=role,
            identity_id=identity_id,
            threaded_callbacks=threaded_callbacks,
            my_current_event_seq_number=my_current_event_seq_number,
            staleness_state=staleness_state,
            dispatch_context=None,
        )


# =============================================================================
# Dispatch endpoints
# =============================================================================


def dispatch_live_session_action(
    *,
    session_id: str,
    action: str | UserAction,
    identity_id: str = None,
    user_fill: Optional[Mapping[str, Any]] = None,
    user_signal: Optional[Mapping[str, Any]] = None,
    role: Optional[str] = None,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
    events_only: bool = False,
    my_current_event_seq_number: Optional[int] = None,
) -> Dict[str, Any]:
    """Dispatch one action through the highest authoring facade."""
    packet = _dispatch_direct(
        session_id=str(session_id),
        action=action,
        user_fill=user_fill,
        user_signal=user_signal,
        role=role,
        identity_id=identity_id,
        threaded_callbacks=threaded_callbacks,
        my_current_event_seq_number=my_current_event_seq_number,
    )
    return _events_only_dispatch_receipt_v1(packet, chain=False) if events_only else packet


def dispatch_live_session_action_with_chain_reaction(
    *,
    session_id: str,
    action: str | UserAction,
    identity_id: str = None,
    user_fill: Optional[Mapping[str, Any]] = None,
    user_signal: Optional[Mapping[str, Any]] = None,
    role: Optional[str] = None,
    chainreactionTM_config: Any = _UNSET,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
    events_only: bool = False,
    my_current_event_seq_number: Optional[int] = None,
) -> Dict[str, Any]:
    """Dispatch one action and continue through configured generated dispatches.

    Generated continuations use derived dispatcher identities while preserving
    the ordinary threaded callback surface.
    """
    sid = str(session_id)
    initial_identity_id = _require_dispatcher_identity_id_v1(identity_id)
    delivery_callbacks = _threaded_callbacks_for_live_delivery_v1(
        threaded_callbacks
    )
    session_metadata = _session_metadata_for_chainreactiontm_config_validation(sid)
    config = _normalize_call_chainreactiontm_config(
        session_metadata,
        chainreactionTM_config=chainreactionTM_config,
    )

    with serialized_dispatch_boundary_v1(sid) as staleness_state:
        try:
            initial_packet = _dispatch_direct_inside_boundary(
                session_id=sid,
                action=action,
                user_fill=user_fill,
                user_signal=user_signal,
                role=role,
                identity_id=initial_identity_id,
                threaded_callbacks=delivery_callbacks,
                my_current_event_seq_number=my_current_event_seq_number,
                staleness_state=staleness_state,
            )
        except KeyError as exc:
            if config.enabled and _looks_like_unknown_session_role_keyerror(exc):
                raise FunkUnanticipatedDatumRoleRuntimeError(str(exc)) from exc
            raise

        if initial_packet.get("rejected") is True:
            packet = dict(initial_packet)
        elif isinstance(initial_packet.get("system_error"), Mapping):
            packet = _packet_with_chainreactiontm_stop(
                initial_packet,
                enabled=config.enabled,
                stopped_reason="initial_dispatch_system_error",
            )
        elif not _is_step_action(action):
            packet = _packet_with_chainreactiontm_stop(
                initial_packet,
                enabled=config.enabled,
                stopped_reason="non_step_action",
            )
        else:

            def generated_dispatch(**kwargs: Any) -> Dict[str, Any]:
                generated_role = normalize_service_role(kwargs.get("role"))
                generated_identity_id = _funked_dispatcher_identity_id_v1(
                    initial_identity_id=initial_identity_id,
                    generated_role=generated_role,
                )
                return _dispatch_direct_inside_boundary(
                    session_id=str(kwargs["session_id"]),
                    action=kwargs["action"],
                    user_fill=kwargs.get("user_fill"),
                    user_signal=kwargs.get("user_signal"),
                    role=generated_role,
                    identity_id=generated_identity_id,
                    threaded_callbacks=kwargs.get("threaded_callbacks"),
                    my_current_event_seq_number=None,
                    staleness_state=staleness_state,
                    dispatch_context=(
                        dict(kwargs.get("dispatch_context") or {})
                        if isinstance(kwargs.get("dispatch_context"), Mapping)
                        else None
                    ),
                )

            packet = dict(
                run_chain_reaction_after_initial_dispatch(
                    session_id=sid,
                    config=config,
                    initial_packet=dict(initial_packet),
                    dispatch_fn=generated_dispatch,
                    get_live_ctx_fn=get_live_session_context,
                    get_live_events_fn=get_live_session_events,
                    threaded_callbacks=delivery_callbacks,
                )
                or {}
            )
            packet["dispatch_staleness"] = dict(
                initial_packet["dispatch_staleness"]
            )

    return _events_only_dispatch_receipt_v1(packet, chain=True) if events_only else packet


# =============================================================================
# Fully-funked black-box run
# =============================================================================


def run_funked_black_box_from_program(
    *,
    program: Mapping[str, Any],
    program_language: str,
    initial_parameter_overrides: Optional[Mapping[str, Any]] = None,
    session_metadata: Optional[Mapping[str, Any]] = None,
    roles: Optional[Mapping[str, Any]] = None,
    role_mismatch_policy: Optional[Mapping[str, Any]] = None,
    identity_id: Optional[str] = None,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
    retain_session: bool = False,
) -> Dict[str, Any]:
    """Create and completely execute one P/SM/C flow without manual I/O.

    Static contract, evaluated on the resolved launch surfaces before session
    allocation:
      1. every role authored on resolved P exists in resolved SM.roles;
      2. chainreactionTM is enabled;
      3. every P role is scheduled and has a non-null normalized funk config.

    Runtime contract:
      4. one empty manual STEP starts the program;
      5. the ensuing generated dispatch chain reaches canonical ATCOMPLETION;
      6. stopping at any manual-I/O frontier is an error.

    The function returns the final canonical context, outputs, the retained
    canonical event window, initial+chain dispatch receipt, and static contract
    receipt. By default the temporary live session is deleted after those
    values are captured. Set ``retain_session=True`` when a hosting layer wants
    to keep the completed or failed session for inspection.
    """
    if not isinstance(program, Mapping):
        raise TypeError("run_funked_black_box_from_program requires a mapping program")

    effective_program, resolved_metadata = _resolve_live_session_launch_surfaces_v1(
        program=program,
        initial_parameter_overrides=initial_parameter_overrides,
        session_metadata=session_metadata,
        roles=roles,
        role_mismatch_policy=role_mismatch_policy,
    )
    if not isinstance(effective_program, Mapping):
        raise TypeError("resolved black-box ThinkProgram must be a mapping")

    config = _normalize_call_chainreactiontm_config(
        resolved_metadata,
        chainreactionTM_config=_UNSET,
    )
    contract = validate_funked_black_box_contract_v1(
        program=effective_program,
        resolved_session_metadata=resolved_metadata,
        normalized_chainreaction_config=config,
    )

    created = _create_live_session_from_resolved_surfaces_v1(
        program=effective_program,
        program_language=program_language,
        resolved_session_metadata=resolved_metadata,
    )
    sid = str(created["session_id"])

    try:
        dispatcher_identity = str(identity_id or "").strip() or f"blackbox-{sid}"
        initial_cursor = get_live_session_latest_event_seq(session_id=sid)

        dispatch_result = dispatch_live_session_action_with_chain_reaction(
            session_id=sid,
            action=UserAction.STEP,
            identity_id=dispatcher_identity,
            user_fill=None,
            user_signal=None,
            role=None,
            threaded_callbacks=threaded_callbacks,
            events_only=False,
            my_current_event_seq_number=initial_cursor,
        )

        final_ctx = get_concrete_session_api().get_session_context(sid)
        if not isinstance(final_ctx, Mapping):
            raise TypeError("black-box final context must be a mapping")
        final_ctx = dict(final_ctx)
        outputs = get_live_session_outputs_report(session_id=sid)
        events = get_live_session_events(session_id=sid, role=None, limit=None)
        latest_event_seq = get_live_session_latest_event_seq(session_id=sid)

        finished = str(final_ctx.get("kind") or "") == "ATCOMPLETION"
        failed_dispatch = bool(
            dispatch_result.get("rejected")
            or isinstance(dispatch_result.get("system_error"), Mapping)
        )

        chain_receipt = dispatch_result.get("chainreactionTM_receipt")
        stopped_reason = (
            str(chain_receipt.get("stopped_reason") or "")
            if isinstance(chain_receipt, Mapping)
            else ""
        )

        base_report = {
            "kind": (
                BLACK_BOX_RESULT_KIND_V1
                if finished and not failed_dispatch
                else BLACK_BOX_ERROR_REPORT_KIND_V1
            ),
            "ok": bool(finished and not failed_dispatch),
            "session_id": sid,
            "session_retained": bool(retain_session),
            "dispatcher_identity_id": dispatcher_identity,
            "contract": contract,
            "dispatch_result": dict(dispatch_result),
            "final_context": final_ctx,
            "final_context_kind": str(final_ctx.get("kind") or ""),
            "chain_stopped_reason": stopped_reason or None,
            "outputs_report": outputs,
            "events": events,
            "latest_event_seq": latest_event_seq,
        }

        if not finished or failed_dispatch:
            message = (
                "funked black-box run did not reach ATCOMPLETION"
                + (
                    f"; chain stopped_reason={stopped_reason!r}"
                    if stopped_reason
                    else ""
                )
            )
            if not retain_session:
                base_report["delete_report"] = delete_live_session(session_id=sid)
                base_report["session_retained"] = False
            raise FunkedBlackBoxRunIncompleteError(
                message,
                report=base_report,
            )

        if not retain_session:
            base_report["delete_report"] = delete_live_session(session_id=sid)
            base_report["session_retained"] = False
        return base_report
    except FunkedBlackBoxRunIncompleteError:
        raise
    except Exception:
        if not retain_session:
            try:
                delete_live_session(session_id=sid)
            except Exception:
                pass
        raise


__all__ = [
    "FunkedBlackBoxContractError",
    "FunkedBlackBoxRunIncompleteError",
    "UserAction",
    "check_dispatch_staleness",
    "create_live_session_from_program",
    "delete_live_session",
    "describe_think_program",
    "dispatch_live_session_action",
    "dispatch_live_session_action_with_chain_reaction",
    "get_live_session_context",
    "get_live_session_current_report",
    "get_live_session_events",
    "get_live_session_latest_event_seq",
    "get_live_session_events_since",
    "get_live_session_outputs_report",
    "get_live_session_progress_report",
    "query_live_session",
    "render_live_session_state",
    "run_funked_black_box_from_program",
]
