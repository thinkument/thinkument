from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence

from _thinksessions.libs_read_write_augmented.rolebasedRWmodulatorTM.obfuscation_api import role_modulation
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
    query_runtime_writes,
)

try:
    from _thinkengine._app_table_engine._engine_runtime_data_book.global_write_addresses import (
        KEY_FORMS_EMITTED,
        KEY_PENDING_FORM,
    )
except Exception:  # pragma: no cover
    KEY_FORMS_EMITTED = "forms_emitted"
    KEY_PENDING_FORM = "pending_form"

from _thinksessions.libs_read_write_augmented.chainreactionTM._autoregistry import (
    FunkTMRequest,
    FunkTMResult,
    get_chainreactiontm_version,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM._errors import (
    FunkInputSemanticError,
    FunkMaxFillsE2EExceeded,
    FunkMaxFillsOnSpanExceeded,
    FunkMaxSemanticErrorsExceeded,
    FunkUnanticipatedDatumRoleRuntimeError,
)
from _thinksessions.libs_read_write_augmented.chainreactionTM._static import (
    NormalizedFunkTMConfig,
)


MANUAL_KIND = "MANUALFILLNEEDEDSTEP"
COMPLETE_KIND = "ATCOMPLETION"

NEXT_U_FUNKABILITY_KIND_V1 = (
    "chainreactionTM_next_U_funkability_v1"
)
NEXT_U_FUNKABILITY_RECEIPT_KEY_V1 = "next_U_funkability"
_END_DISPATCH_CONTEXT_FINALIZER_KEY_V1 = (
    "__controller_end_dispatch_context_finalizer_v1__"
)

_EXACT_PENDING_DATUM_VECTOR_KEYS = (
    "pending_datum_widgets",
    "pending_datums",
    "unsatisfied_datum_widgets",
    "unsatisfied_datums",
    "span_pending_datums",
    "span_unsatisfied_datums",
)
_FALLBACK_PENDING_DATUM_VECTOR_KEYS = (
    "datum_widgets_on_this_span",
    "span_authoritative",
    "span_owns",
)


@dataclass
class FunkTMRunState:
    generated_fills_e2e: int = 0
    semantic_errors_in_row: int = 0
    current_span_key: Optional[str] = None
    fills_on_current_span: int = 0
    dispatch_receipts: list[Dict[str, Any]] = field(default_factory=list)
    roles_used: list[str] = field(default_factory=list)
    stopped_reason: str = "not_started"
    active_semantic_error: Optional[Dict[str, Any]] = None


def _ctx_kind(ctx: Mapping[str, Any]) -> str:
    return str(ctx.get("kind") or "")


def _span_key(ctx: Mapping[str, Any]) -> str:
    step = ctx.get("step") if isinstance(ctx.get("step"), Mapping) else {}
    return str(
        ctx.get("current_span")
        or ctx.get("current_span_id")
        or step.get("span_id")
        or ""
    )


def _coerce_datum_id_vector(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    out: list[str] = []
    seen: set[str] = set()

    for item in value:
        datum_id = str(item or "").strip()
        if datum_id and datum_id not in seen:
            seen.add(datum_id)
            out.append(datum_id)

    return out


def _first_datum_vector(
    *,
    ctx: Mapping[str, Any],
    step: Mapping[str, Any],
    keys: Sequence[str],
) -> list[str]:
    for key in keys:
        vector = _coerce_datum_id_vector(ctx.get(key))
        if vector:
            return vector

        vector = _coerce_datum_id_vector(step.get(key))
        if vector:
            return vector

    return []


def _pending_datum_ids(ctx: Mapping[str, Any]) -> list[str]:
    step = ctx.get("step") if isinstance(ctx.get("step"), Mapping) else {}
    exact = _first_datum_vector(
        ctx=ctx,
        step=step,
        keys=_EXACT_PENDING_DATUM_VECTOR_KEYS,
    )
    if exact:
        return exact

    return _first_datum_vector(
        ctx=ctx,
        step=step,
        keys=_FALLBACK_PENDING_DATUM_VECTOR_KEYS,
    )


def _manual_frontier_signature(ctx: Mapping[str, Any]) -> Dict[str, Any]:
    pending = _pending_datum_ids(ctx)

    decls = ctx.get("datum_widget_decls")
    decls = decls if isinstance(decls, Mapping) else {}

    fills = ctx.get("datum_widget_fills")
    fills = fills if isinstance(fills, Mapping) else {}

    state = ctx.get("state")
    state = state if isinstance(state, Mapping) else {}

    cursor = ctx.get("cursor")
    cursor = cursor if isinstance(cursor, Mapping) else {}

    return {
        "kind": _ctx_kind(ctx),
        "span": _span_key(ctx),
        "cursor": {
            "index": cursor.get("index"),
            "total": cursor.get("total"),
        },
        "pending": pending,
        "decls": {
            datum_id: decls.get(datum_id)
            for datum_id in pending
        },
        "fills": {
            datum_id: fills.get(datum_id)
            for datum_id in pending
        },
        "datum_lifecycle_epoch": state.get("datum_lifecycle_epoch"),
    }


def _generated_dispatch_had_fresh_semantic_error(
    *,
    before_ctx: Mapping[str, Any],
    after_ctx: Mapping[str, Any],
) -> bool:
    last_error = after_ctx.get("last_error")
    return bool(
        isinstance(last_error, Mapping)
        and last_error
        and _ctx_kind(after_ctx) == MANUAL_KIND
        and _manual_frontier_signature(before_ctx)
        == _manual_frontier_signature(after_ctx)
    )


def _assignments_by_datum(
    ctx: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    return {
        str(row.get("datum_id")): dict(row)
        for row in role_modulation.current_datum_role_assignments(ctx)
        if isinstance(row, Mapping) and row.get("datum_id")
    }


def _current_pending_role_set(
    ctx: Mapping[str, Any],
    *,
    config: NormalizedFunkTMConfig,
) -> set[str]:
    pending_ids = set(_pending_datum_ids(ctx))
    assignments = _assignments_by_datum(ctx)
    allowed_roles = set(config.flat_roles_ordered)
    roles: set[str] = set()

    for datum_id in pending_ids:
        row = assignments.get(datum_id)
        if not row:
            continue

        for role_name in [
            str(value)
            for value in list(row.get("roles") or [])
            if str(value or "").strip()
        ]:
            if role_name not in allowed_roles:
                raise FunkUnanticipatedDatumRoleRuntimeError(
                    f"active datum {datum_id!r} has unanticipated role "
                    f"{role_name!r}"
                )
            roles.add(role_name)

    return roles


def _choose_next_chainreactioned_role(
    *,
    pending_roles: set[str],
    config: NormalizedFunkTMConfig,
) -> Optional[str]:
    for group in config.roles_ordered:
        group_pending = [
            role
            for role in group
            if role in pending_roles
        ]
        if not group_pending:
            continue

        chainreactioned = [
            role
            for role in group_pending
            if config.role_configs.get(role) is not None
        ]
        return chainreactioned[0] if chainreactioned else None

    return None


def inspect_next_U_funkability_v1(
    *,
    U: Mapping[str, Any],
    config: NormalizedFunkTMConfig,
) -> Dict[str, Any]:
    """Describe whether the controller-end U admits another generated STEP.

    This is a pure observation over the exact canonical U carried by the
    current controller.loop.end packet plus the already-normalized static
    chainreactionTM configuration. It performs no engine read and no mutation.
    """
    kind = _ctx_kind(U)
    span_key = _span_key(U)

    base: Dict[str, Any] = {
        "kind": NEXT_U_FUNKABILITY_KIND_V1,
        "evaluated_from": "controller.loop.end.payload.U",
        "U_kind": kind,
        "span_id": span_key or None,
        "will_funk_next_dispatch": False,
        "selected_role": None,
        "selected_version": None,
        "pending_roles": [],
        "reason": "not_evaluated",
    }

    if not config.enabled:
        base["reason"] = "disabled"
        return base

    if kind != MANUAL_KIND:
        base["reason"] = "program_complete_or_not_manual"
        return base

    pending_roles = _current_pending_role_set(U, config=config)
    base["pending_roles"] = [
        role
        for group in config.roles_ordered
        for role in group
        if role in pending_roles
    ]

    if not pending_roles:
        base["reason"] = "no_roled_pending_datums"
        return base

    role = _choose_next_chainreactioned_role(
        pending_roles=pending_roles,
        config=config,
    )
    if role is None:
        base["reason"] = "next_pending_role_unchainreactioned"
        return base

    role_config = config.role_configs.get(role)
    if role_config is None:
        base["reason"] = "selected_role_unchainreactioned"
        return base

    writable = _pending_datums_for_role(U, role=role)
    if not writable:
        base["selected_role"] = role
        base["selected_version"] = str(role_config["version"])
        base["reason"] = "selected_role_has_no_writable_pending_datums"
        return base

    base.update(
        {
            "will_funk_next_dispatch": True,
            "selected_role": role,
            "selected_version": str(role_config["version"]),
            "writable_pending_datum_ids": sorted(
                str(row["datum_id"])
                for row in writable
            ),
            "reason": "next_dispatch_funkable",
        }
    )
    return base


def _generated_dispatch_context_finalizer_v1(
    *,
    config: NormalizedFunkTMConfig,
) -> Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]:
    def finalize(
        base_dispatch_context: Mapping[str, Any],
        end_U: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        out = dict(base_dispatch_context)
        filler_receipt = dict(out.get("filler_receipt") or {})
        filler_receipt[NEXT_U_FUNKABILITY_RECEIPT_KEY_V1] = (
            inspect_next_U_funkability_v1(
                U=end_U,
                config=config,
            )
        )
        out["filler_receipt"] = filler_receipt
        return out

    return finalize


def _pending_datums_for_role(
    ctx_for_role: Mapping[str, Any],
    *,
    role: str,
) -> list[Dict[str, Any]]:
    pending_ids = set(_pending_datum_ids(ctx_for_role))
    assignments = _assignments_by_datum(ctx_for_role)

    decls = ctx_for_role.get("datum_widget_decls")
    decls = decls if isinstance(decls, Mapping) else {}

    fills = ctx_for_role.get("datum_widget_fills")
    fills = fills if isinstance(fills, Mapping) else {}

    out: list[Dict[str, Any]] = []

    for datum_id in pending_ids:
        assignment = assignments.get(datum_id) or {}
        required_roles = [
            str(value)
            for value in list(assignment.get("roles") or [])
            if str(value or "").strip()
        ]

        if not role_modulation.can_write_roles(
            role=role,
            required_roles=required_roles,
        ):
            continue

        decl = decls.get(datum_id)
        if isinstance(decl, Mapping):
            out.append(
                {
                    "datum_id": datum_id,
                    "required_roles": required_roles,
                    "decl": dict(decl),
                    "current_fill": fills.get(datum_id),
                }
            )

    return out


def _json_size(value: Any) -> int:
    try:
        return len(
            json.dumps(
                value,
                separators=(",", ":"),
                default=str,
            )
        )
    except Exception:
        return len(repr(value))


def _cap_history_size(
    history: Dict[str, Any],
    *,
    cap: int,
) -> Dict[str, Any]:
    if _json_size(history) <= cap:
        return history

    out = dict(history)
    rows = list(out.get("rows") or [])

    while rows and _json_size({**out, "rows": rows}) > cap:
        rows.pop(0)

    out["rows"] = rows
    out["truncated_by_size"] = True
    out["history_size_cap"] = cap
    return out


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []

    raw = (
        [value]
        if isinstance(value, str)
        else list(value)
        if isinstance(value, Sequence)
        and not isinstance(value, (bytes, bytearray, str))
        else [value]
    )

    out: list[str] = []
    seen: set[str] = set()

    for item in raw:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)

    return out


def _role_list_from_row(
    row: Mapping[str, Any],
) -> list[str] | None:
    if "roles" in row:
        return _string_list(row.get("roles"))
    if "role" in row:
        return _string_list(row.get("role"))
    return None


def _looks_like_multiframespec(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(value.get("datums"), list)
        and isinstance(value.get("frames"), list)
    )


def _iter_known_multiframespecs_from_snapshot(
    *,
    snapshot: Mapping[str, Any],
    raw_ctx: Mapping[str, Any],
) -> Iterable[Mapping[str, Any]]:
    seen: set[int] = set()

    def emit(value: Any) -> Iterable[Mapping[str, Any]]:
        if not _looks_like_multiframespec(value) or id(value) in seen:
            return

        seen.add(id(value))
        yield value

    yield from emit(raw_ctx.get("multiframespec"))

    state = snapshot.get("state")
    if not isinstance(state, Mapping):
        return

    for candidate in (
        state.get(KEY_PENDING_FORM),
        state.get("pending_form"),
        state.get("__pending_form__"),
    ):
        yield from emit(candidate)

    for bucket in (
        state.get(KEY_FORMS_EMITTED),
        state.get("forms_emitted"),
        state.get("__forms_emitted__"),
    ):
        if isinstance(bucket, Mapping):
            for child in bucket.values():
                yield from emit(child)


def _datum_role_map_from_multiframespec(
    multiframespec: Mapping[str, Any],
) -> Dict[str, list[str]]:
    out: Dict[str, list[str]] = {}
    explicit: Dict[str, list[str] | None] = {}

    for raw_datum in list(multiframespec.get("datums") or []):
        if not isinstance(raw_datum, Mapping):
            continue

        datum_id = str(
            raw_datum.get("id")
            or raw_datum.get("datum_id")
            or ""
        ).strip()
        if not datum_id:
            continue

        roles = _role_list_from_row(raw_datum)
        explicit[datum_id] = roles

        if roles is not None:
            out[datum_id] = roles

    for raw_frame in list(multiframespec.get("frames") or []):
        if not isinstance(raw_frame, Mapping):
            continue

        for raw_span in list(raw_frame.get("spans") or []):
            if not isinstance(raw_span, Mapping):
                continue

            span_roles = _role_list_from_row(raw_span) or []

            for datum_id in [
                str(value or "").strip()
                for value in list(raw_span.get("owns") or [])
                if str(value or "").strip()
            ]:
                out[datum_id] = (
                    explicit.get(datum_id)
                    if explicit.get(datum_id) is not None
                    else span_roles
                )

    for datum_id, roles in explicit.items():
        if roles is None:
            out.setdefault(datum_id, [])

    return out


def _datum_role_map_for_session(
    *,
    snapshot: Mapping[str, Any],
    raw_ctx: Mapping[str, Any],
) -> Dict[str, list[str]]:
    role_map: Dict[str, list[str]] = {}

    for spec in _iter_known_multiframespecs_from_snapshot(
        snapshot=snapshot,
        raw_ctx=raw_ctx,
    ):
        role_map.update(_datum_role_map_from_multiframespec(spec))

    for datum_id, row in _assignments_by_datum(raw_ctx).items():
        role_map[datum_id] = [
            str(value)
            for value in list(row.get("roles") or [])
            if str(value or "").strip()
        ]

    return role_map


def _bounded_history_last_k_invocations(
    *,
    history_tail_cap: int,
    readable_role_count: int,
) -> int:
    return max(
        1,
        min(
            max(1, history_tail_cap)
            * max(1, readable_role_count)
            * 8,
            10_000,
        ),
    )


def _bounded_history_query_max_results(
    *,
    history_tail_cap: int,
    readable_role_count: int,
) -> int:
    return max(
        1,
        min(
            max(1, history_tail_cap)
            * max(1, readable_role_count)
            * 16,
            max(1, history_tail_cap) * 512,
            10_000,
        ),
    )


def collect_bounded_history_for_role(
    *,
    session_id: str,
    role: str,
    history_tail_cap: int,
    history_size_cap: int,
    raw_ctx: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    raw_api = get_concrete_session_api()
    current_ctx = (
        dict(raw_ctx)
        if isinstance(raw_ctx, Mapping)
        else raw_api.get_session_context(str(session_id))
    )

    roles, _policy = role_modulation.role_sheet_from_context(current_ctx)
    readable_roles = sorted(
        role_modulation.effective_read_roles(
            roles,
            role=role,
        )
    )

    snapshot = raw_api.export_session_snapshot(str(session_id))
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}

    state = snapshot.get("state")
    state = state if isinstance(state, Mapping) else {}

    role_map = _datum_role_map_for_session(
        snapshot=snapshot,
        raw_ctx=current_ctx,
    )

    last_k_invocations = _bounded_history_last_k_invocations(
        history_tail_cap=history_tail_cap,
        readable_role_count=len(readable_roles),
    )

    result = query_runtime_writes(
        state,
        {
            "write_kinds": [
                "form_fill",
                "form_prefill",
                "datum_lifecycle",
            ],
            "include_values": True,
            "last_k_invocations": last_k_invocations,
            "max_results": _bounded_history_query_max_results(
                history_tail_cap=history_tail_cap,
                readable_role_count=len(readable_roles),
            ),
        },
    )

    rows = result.get("writes") if isinstance(result, Mapping) else []
    rows = rows if isinstance(rows, list) else []

    by_role: Dict[str, list[Dict[str, Any]]] = {
        readable_role: []
        for readable_role in readable_roles
    }
    unknown_role_rows_dropped = 0
    unreadable_role_rows_dropped = 0

    for raw_row in rows:
        if not isinstance(raw_row, Mapping):
            continue

        datum_id = str(
            raw_row.get("datum_id")
            or raw_row.get("key")
            or ""
        ).strip()
        if not datum_id:
            continue

        datum_roles = role_map.get(datum_id)
        if datum_roles is None:
            unknown_role_rows_dropped += 1
            continue

        visible_to = (
            [
                datum_role
                for datum_role in datum_roles
                if datum_role in readable_roles
            ]
            if datum_roles
            else [role]
        )

        if not visible_to:
            unreadable_role_rows_dropped += 1
            continue

        for owner_role in visible_to:
            if owner_role in by_role:
                by_role[owner_role].append(
                    {
                        "datum_id": datum_id,
                        "write_kind": (
                            raw_row.get("write_kind")
                            or raw_row.get("kind")
                        ),
                        "value": raw_row.get("value"),
                        "seq": raw_row.get("seq"),
                    }
                )

    compact_rows = [
        {
            "role": owner_role,
            **row,
        }
        for owner_role, role_rows in by_role.items()
        for row in role_rows[-history_tail_cap:]
    ]

    return _cap_history_size(
        {
            "kind": "chainreactionTM_history_v1",
            "role_viewing": role,
            "readable_roles": readable_roles,
            "history_tail_cap": history_tail_cap,
            "rows": compact_rows,
            "unknown_role_rows_dropped": unknown_role_rows_dropped,
            "unreadable_role_rows_dropped": unreadable_role_rows_dropped,
            "source": "runtime_write_index",
            "last_k_invocations": last_k_invocations,
        },
        cap=history_size_cap,
    )


def build_receipt(state: FunkTMRunState) -> Dict[str, Any]:
    return {
        "kind": "chainreactionTM_chain_reaction_receipt_v1",
        "enabled": True,
        "generated_fills_e2e": state.generated_fills_e2e,
        "generated_dispatches_e2e": state.generated_fills_e2e,
        "semantic_errors_in_row": state.semantic_errors_in_row,
        "fills_on_current_span": state.fills_on_current_span,
        "generated_dispatches_on_current_span": (
            state.fills_on_current_span
        ),
        "roles_used": list(state.roles_used),
        "stopped_reason": state.stopped_reason,
        "dispatch_count": state.generated_fills_e2e,
        "dispatch_receipts": state.dispatch_receipts[-8:],
    }


def _validate_chainreactiontm_result_scope(
    *,
    result: FunkTMResult,
    pending_datums: Sequence[Mapping[str, Any]],
    role: str,
) -> None:
    allowed = {
        str(row.get("datum_id") or "").strip()
        for row in pending_datums
        if str(row.get("datum_id") or "").strip()
    }

    for raw_key in dict(result.fill or {}):
        datum_id = str(raw_key or "").strip()
        if datum_id not in allowed:
            raise TypeError(
                f"chainreactionTM result for role {role!r} attempted to fill "
                f"non-pending or non-writable datum {datum_id!r}"
            )

    if isinstance(result.signal, Mapping):
        target = str(
            result.signal.get("datum_id")
            or result.signal.get("target")
            or ""
        ).strip()
        if target and target not in allowed:
            raise TypeError(
                f"chainreactionTM result for role {role!r} attempted to signal "
                f"non-pending or non-writable datum {target!r}"
            )


def _recent_events_for_funk_request(
    *,
    session_id: str,
    role: str,
    events_queue_length: int,
    get_live_events_fn: Optional[
        Callable[..., list[Dict[str, Any]]]
    ],
) -> list[Dict[str, Any]]:
    """
    Return the latest role-projected event tail for FunkTMRequest.events.

    events_queue_length=0 is the compatibility default and performs no event
    queue read.
    """
    if int(events_queue_length or 0) <= 0:
        return []

    if not callable(get_live_events_fn):
        return []

    events = get_live_events_fn(
        session_id=str(session_id),
        role=role,
        limit=int(events_queue_length),
    )

    return [
        dict(event or {})
        for event in list(events or [])
    ]


def run_chain_reaction_after_initial_dispatch(
    *,
    session_id: str,
    config: NormalizedFunkTMConfig,
    initial_packet: Dict[str, Any],
    dispatch_fn: Any,
    get_live_ctx_fn: Any,
    get_live_events_fn: Optional[
        Callable[..., list[Dict[str, Any]]]
    ] = None,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
    event_scope_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    if not config.enabled:
        out = dict(initial_packet)
        out["chainreactionTM_receipt"] = {
            "kind": "chainreactionTM_chain_reaction_receipt_v1",
            "enabled": False,
            "stopped_reason": "disabled",
        }
        return out

    state = FunkTMRunState()
    last_packet = dict(initial_packet)
    raw_api = get_concrete_session_api()

    while True:
        raw_ctx = raw_api.get_session_context(str(session_id))

        if _ctx_kind(raw_ctx) != MANUAL_KIND:
            state.stopped_reason = "program_complete_or_not_manual"
            break

        span_key = _span_key(raw_ctx)
        if span_key != state.current_span_key:
            state.current_span_key = span_key
            state.fills_on_current_span = 0
            state.semantic_errors_in_row = 0

        if state.generated_fills_e2e >= config.max_fills_e2e:
            raise FunkMaxFillsE2EExceeded(
                f"max_fills_e2e exceeded: {config.max_fills_e2e}"
            )

        if state.fills_on_current_span >= config.max_fills_on_a_span:
            raise FunkMaxFillsOnSpanExceeded(
                f"max_fills_on_a_span exceeded on span {span_key!r}: "
                f"{config.max_fills_on_a_span}"
            )

        pending_roles = _current_pending_role_set(
            raw_ctx,
            config=config,
        )
        if not pending_roles:
            state.stopped_reason = "no_roled_pending_datums"
            break

        role = _choose_next_chainreactioned_role(
            pending_roles=pending_roles,
            config=config,
        )
        if role is None:
            state.stopped_reason = "next_pending_role_unchainreactioned"
            break

        role_config = config.role_configs.get(role)
        if role_config is None:
            state.stopped_reason = "selected_role_unchainreactioned"
            break

        role_ctx = get_live_ctx_fn(
            session_id=str(session_id),
            role=role,
        )

        pending_datums = _pending_datums_for_role(
            role_ctx,
            role=role,
        )
        if not pending_datums:
            state.stopped_reason = (
                "selected_role_has_no_writable_pending_datums"
            )
            break

        history = collect_bounded_history_for_role(
            session_id=str(session_id),
            role=role,
            history_tail_cap=config.history_tail_cap,
            history_size_cap=config.history_size_cap,
            raw_ctx=raw_ctx,
        )

        events = _recent_events_for_funk_request(
            session_id=str(session_id),
            role=role,
            events_queue_length=config.events_queue_length,
            get_live_events_fn=get_live_events_fn,
        )

        version_spec = get_chainreactiontm_version(
            str(role_config["version"])
        )

        result = version_spec.run(
            FunkTMRequest(
                session_id=str(session_id),
                role=role,
                args=dict(role_config.get("args") or {}),
                ctx=dict(role_ctx),
                pending_datums=pending_datums,
                history=history,
                last_error=(
                    dict(state.active_semantic_error)
                    if isinstance(
                        state.active_semantic_error,
                        Mapping,
                    )
                    else None
                ),
                semantic_errors_in_row=state.semantic_errors_in_row,
                events=events,
            )
        )

        if not isinstance(result, FunkTMResult):
            raise TypeError(
                f"chainreactionTM version {version_spec.name!r} "
                "must return FunkTMResult"
            )

        _validate_chainreactiontm_result_scope(
            result=result,
            pending_datums=pending_datums,
            role=role,
        )

        if not result.fill and not result.signal:
            state.stopped_reason = "chainreaction_version_returned_noop"
            break

        dispatch_context = {
            "kind": "chainreactionTM_generated_dispatch_context_v1",
            "origin": "chainreactionTM",
            "role": role,
            "version": version_spec.name,
            "generated_dispatch_index": state.generated_fills_e2e + 1,
            "span_generated_dispatch_index": state.fills_on_current_span + 1,
            "filler_receipt": dict(result.receipt or {}),
            _END_DISPATCH_CONTEXT_FINALIZER_KEY_V1: (
                _generated_dispatch_context_finalizer_v1(
                    config=config,
                )
            ),
        }

        scope = (
            event_scope_factory(**dispatch_context)
            if callable(event_scope_factory)
            else nullcontext()
        )

        with scope:
            packet = dispatch_fn(
                session_id=str(session_id),
                action="STEP",
                user_fill=dict(result.fill or {}),
                user_signal=(
                    dict(result.signal)
                    if isinstance(result.signal, Mapping)
                    else None
                ),
                role=role,
                threaded_callbacks=threaded_callbacks,
                dispatch_context=dispatch_context,
            )

        state.generated_fills_e2e += 1
        state.fills_on_current_span += 1
        state.roles_used.append(role)
        state.dispatch_receipts.append(
            {
                "role": role,
                "version": version_spec.name,
                "receipt": dict(result.receipt or {}),
            }
        )

        last_packet = dict(packet or {})
        after_ctx = raw_api.get_session_context(str(session_id))
        last_error = after_ctx.get("last_error")

        if _generated_dispatch_had_fresh_semantic_error(
            before_ctx=raw_ctx,
            after_ctx=after_ctx,
        ):
            state.active_semantic_error = dict(last_error)
            state.semantic_errors_in_row += 1

            if config.on_semantic_error == "raise":
                raise FunkInputSemanticError(
                    "chainreactionTM generated semantic error for role "
                    f"{role!r}: {last_error}"
                )

            if (
                state.semantic_errors_in_row
                > config.max_semantic_errors_in_a_row
            ):
                raise FunkMaxSemanticErrorsExceeded(
                    "max_semantic_errors_in_a_row exceeded: "
                    f"{config.max_semantic_errors_in_a_row}"
                )

            continue

        state.active_semantic_error = None
        state.semantic_errors_in_row = 0

    out = dict(last_packet)
    out["chainreactionTM_receipt"] = build_receipt(state)
    return out