from __future__ import annotations

"""
Highest-façade dispatch staleness prevention.

This module is adjacent to ``_thinksessions.run.run_from_here`` because staleness is an
app-facing dispatch coordination concern, not an AppTable engine concern.

Scope
-----

Every dispatch entering through ``_thinksessions.run.run_from_here`` is serialized by a
per-session reentrant lock and checked against one process-local target-change
index.

The canonical engine queue remains the sole event sequence authority. This
module never assigns, predicts, or increments event sequence values.

Complexity
----------

For a dispatch targeting T unique canonical datums, stale checking is O(|T|):

    max(last_changed_seq[target] for target in T)

No event queue scan is performed. In particular, the implementation never
walks the canonical interval ``(C, A]``. The size of that interval is irrelevant
to dispatch-check cost.

Decision precedence
-------------------

For C < A, active-scope invalidation is checked before target conflict:

    scope_last_changed_seq > C
        -> stale_scope_changed

    otherwise max(last_changed_seq[target] for target in T) > C
        -> stale_conflict

This precedence is intentional. A cursor that predates a form/frame/span
transition no longer identifies the same authored write surface, even when a
datum id is reused.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple


DISPATCH_STALENESS_RECEIPT_KIND_V1 = (
    "live_session_dispatch_staleness_receipt_v1"
)
DISPATCH_STALENESS_REJECTION_KIND_V1 = (
    "live_session_dispatch_rejected_v1"
)
DISPATCH_STALENESS_AUX_NAMESPACE_V1 = (
    "_thinksessions.run.run_from_here.dispatch_staleness.v1"
)

CanonicalWriteTarget = Tuple[str, str, str, str]
CanonicalWriteScope = Tuple[str, str, str]


def _nonempty_text(value: Any) -> str:
    return str(value or "").strip()


def _current_scope_from_U(
    U: Mapping[str, Any],
) -> CanonicalWriteScope:
    step_info = U.get("step") if isinstance(U.get("step"), Mapping) else {}
    step_at = str(step_info.get("at", "0"))
    return (
        _nonempty_text(U.get("form_id") or U.get("app_form_id") or "root"),
        _nonempty_text(U.get("current_frame_id") or U.get("frame_id") or f"frame_{step_at}"),
        _nonempty_text(
            U.get("current_span")
            or U.get("current_span_id")
            or U.get("span_id")
            or f"span_{step_at}"
        ),
    )


def submitted_datum_ids_v1(
    *,
    user_fill: Optional[Mapping[str, Any]],
    user_signal: Optional[Mapping[str, Any]],
) -> list[str]:
    """
    Resolve the submitted datum ids in stable first-occurrence order.

    Dotted fill keys are canonicalized to their macro datum id. A signal datum
    joins the same conflict domain as fill data for that datum.
    """
    out: list[str] = []
    seen: set[str] = set()

    if isinstance(user_fill, Mapping):
        for raw_key in user_fill:
            datum_id = _nonempty_text(raw_key).split(".", 1)[0]
            if datum_id and datum_id not in seen:
                seen.add(datum_id)
                out.append(datum_id)

    if isinstance(user_signal, Mapping):
        datum_id = _nonempty_text(user_signal.get("datum_id"))
        if datum_id and datum_id not in seen:
            seen.add(datum_id)
            out.append(datum_id)

    return out


def resolve_canonical_write_targets_v1(
    U: Mapping[str, Any],
    *,
    user_fill: Optional[Mapping[str, Any]],
    user_signal: Optional[Mapping[str, Any]],
) -> tuple[CanonicalWriteScope, tuple[CanonicalWriteTarget, ...]]:
    """
    Resolve canonical location-qualified targets from the current raw U.

    A datum id by itself is insufficient because authored programs may reuse a
    datum id on later spans. The active form/frame/span is therefore part of
    every target identity.
    """
    scope = _current_scope_from_U(U)
    datum_ids = submitted_datum_ids_v1(
        user_fill=user_fill,
        user_signal=user_signal,
    )

    return (
        scope,
        tuple(
            (
                scope[0],
                scope[1],
                scope[2],
                datum_id,
            )
            for datum_id in datum_ids
        ),
    )


def _normalize_caller_seq(
    value: Optional[int],
) -> Optional[int]:
    if value is None:
        return None

    # This is a versioned API cursor, not a coercion surface. Reject bool,
    # numeric strings, floats, Decimals, and custom int-like objects. Accept
    # exactly Python int so malformed callers cannot silently change position.
    if type(value) is not int:
        raise TypeError(
            "my_current_event_seq_number must be an integer or None"
        )

    if value < 0:
        raise ValueError(
            "my_current_event_seq_number must be >= 0"
        )

    return value


@dataclass
class _SessionDispatchStalenessState:
    lock: RLock = field(default_factory=RLock)
    last_changed_seq_by_target: Dict[CanonicalWriteTarget, int] = field(
        default_factory=dict
    )
    last_scope_changed_seq: int = 0
    last_observed_scope: Optional[CanonicalWriteScope] = None


@dataclass(frozen=True)
class HostedDispatchStalenessBoundaryV1:
    """
    Hosting-layer handle for one locked process-local staleness domain.

    The mutable implementation state remains private. Hosting services may
    persist only the versioned dead-JSON snapshot returned by ``snapshot``.
    """

    _state: _SessionDispatchStalenessState

    def snapshot(self) -> Dict[str, Any]:
        return snapshot_dispatch_staleness_state_v1(self._state)


_STATE_LOCK = RLock()
_STATE_BY_SESSION: Dict[str, _SessionDispatchStalenessState] = {}


def _state_for_session(
    session_id: str,
) -> _SessionDispatchStalenessState:
    sid = str(session_id)

    with _STATE_LOCK:
        state = _STATE_BY_SESSION.get(sid)
        if state is None:
            state = _SessionDispatchStalenessState()
            _STATE_BY_SESSION[sid] = state

        return state


@contextmanager
def serialized_dispatch_boundary_v1(
    session_id: str,
) -> Iterator[_SessionDispatchStalenessState]:
    state = _state_for_session(str(session_id))

    with state.lock:
        yield state


@contextmanager
def hosted_dispatch_staleness_boundary_v1(
    session_id: str,
    *,
    persisted_snapshot: Optional[Mapping[str, Any]],
) -> Iterator[HostedDispatchStalenessBoundaryV1]:
    """
    Hold the core process-local dispatch lock around a hosting transaction.

    The hosting layer must acquire its distributed/session-database boundary
    before entering this context. Nested calls through ``run_from_here`` are
    safe because the underlying lock is reentrant.
    """
    with serialized_dispatch_boundary_v1(
        str(session_id)
    ) as state:
        restore_dispatch_staleness_state_v1(
            state,
            persisted_snapshot,
        )
        yield HostedDispatchStalenessBoundaryV1(state)


def forget_dispatch_staleness_session_v1(
    session_id: str,
) -> None:
    with _STATE_LOCK:
        _STATE_BY_SESSION.pop(str(session_id), None)


def snapshot_dispatch_staleness_state_v1(
    state: _SessionDispatchStalenessState,
) -> Dict[str, Any]:
    """
    Return the complete restart-safe dead-JSON staleness index.

    Tuple dictionary keys are encoded as rows so repository auxiliary JSON
    remains implementation-independent.
    """
    rows = [
        {
            "form_id": target[0],
            "frame_id": target[1],
            "span_id": target[2],
            "datum_id": target[3],
            "last_changed_seq": int(seq),
        }
        for target, seq in sorted(
            state.last_changed_seq_by_target.items()
        )
    ]
    return {
        "kind": "live_session_dispatch_staleness_state_v1",
        "last_scope_changed_seq": int(state.last_scope_changed_seq),
        "last_observed_scope": (
            None
            if state.last_observed_scope is None
            else list(state.last_observed_scope)
        ),
        "targets": rows,
    }


def restore_dispatch_staleness_state_v1(
    state: _SessionDispatchStalenessState,
    payload: Optional[Mapping[str, Any]],
) -> None:
    """
    Replace process-local state from one repository-owned snapshot.

    Missing state means a new session and resets the process-local copy.
    Malformed durable state fails closed instead of silently approving an old
    cursor with an incomplete index.
    """
    state.last_changed_seq_by_target.clear()
    state.last_scope_changed_seq = 0
    state.last_observed_scope = None

    if payload is None:
        return
    if not isinstance(payload, Mapping):
        raise TypeError("persisted dispatch staleness state must be an object")
    if payload.get("kind") != "live_session_dispatch_staleness_state_v1":
        raise ValueError("unknown persisted dispatch staleness state kind")

    scope_seq = payload.get("last_scope_changed_seq", 0)
    if type(scope_seq) is not int or scope_seq < 0:
        raise ValueError("last_scope_changed_seq must be a non-negative int")
    state.last_scope_changed_seq = scope_seq

    observed = payload.get("last_observed_scope")
    if observed is not None:
        if (
            not isinstance(observed, list)
            or len(observed) != 3
            or not all(isinstance(value, str) for value in observed)
        ):
            raise ValueError("last_observed_scope must be null or three strings")
        state.last_observed_scope = (
            observed[0],
            observed[1],
            observed[2],
        )

    targets = payload.get("targets", [])
    if not isinstance(targets, list):
        raise ValueError("targets must be a list")

    for row in targets:
        if not isinstance(row, Mapping):
            raise ValueError("every persisted target must be an object")
        target = (
            _nonempty_text(row.get("form_id") or "root"),
            _nonempty_text(row.get("frame_id") or "frame_0"),
            _nonempty_text(row.get("span_id") or "span_0"),
            _nonempty_text(row.get("datum_id")),
        )
        if not all(target):
            raise ValueError("persisted targets must be fully qualified")
        seq = row.get("last_changed_seq")
        if type(seq) is not int or seq < 0:
            raise ValueError("target last_changed_seq must be non-negative int")
        state.last_changed_seq_by_target[target] = seq


def _receipt(
    *,
    checked: bool,
    outcome: str,
    reason: str,
    supplied_event_seq: Optional[int],
    observed_event_seq: int,
    scope_last_changed_seq: int,
    target_last_changed_seq: int,
    targets: Sequence[CanonicalWriteTarget],
) -> Dict[str, Any]:
    return {
        "kind": DISPATCH_STALENESS_RECEIPT_KIND_V1,
        "checked": bool(checked),
        "outcome": str(outcome),
        "reason": str(reason),
        "supplied_event_seq": supplied_event_seq,
        "observed_event_seq": int(observed_event_seq),
        "scope_last_changed_seq": int(scope_last_changed_seq),
        "target_last_changed_seq": int(target_last_changed_seq),
        "target_count": len(tuple(targets)),
    }


def _check_valid_dispatch_staleness_v1(
    *,
    my_current_event_seq_number: Optional[int],
    actual_latest_event_seq: int,
    targets: Sequence[CanonicalWriteTarget],
    state: _SessionDispatchStalenessState,
) -> Dict[str, Any]:
    """
    Check one already-normalized dispatch cursor without mutating the index.
    """
    C = _normalize_caller_seq(my_current_event_seq_number)
    A = int(actual_latest_event_seq)

    if A < 0:
        raise ValueError("actual_latest_event_seq must be >= 0")

    target_last_changed = max(
        (
            int(state.last_changed_seq_by_target.get(tuple(target), 0))
            for target in targets
        ),
        default=0,
    )
    scope_last_changed = int(state.last_scope_changed_seq)

    if C is None:
        return _receipt(
            checked=False,
            outcome="allowed",
            reason="cursor_not_supplied",
            supplied_event_seq=None,
            observed_event_seq=A,
            scope_last_changed_seq=scope_last_changed,
            target_last_changed_seq=target_last_changed,
            targets=targets,
        )

    if C > A:
        return _receipt(
            checked=True,
            outcome="rejected",
            reason="future_event_cursor",
            supplied_event_seq=C,
            observed_event_seq=A,
            scope_last_changed_seq=scope_last_changed,
            target_last_changed_seq=target_last_changed,
            targets=targets,
        )

    if C == A:
        return _receipt(
            checked=True,
            outcome="allowed",
            reason="at_high_water",
            supplied_event_seq=C,
            observed_event_seq=A,
            scope_last_changed_seq=scope_last_changed,
            target_last_changed_seq=target_last_changed,
            targets=targets,
        )

    # Scope invalidation intentionally has precedence over target conflict.
    # Once the active form/frame/span moved after C, a repeated datum id may
    # refer to a different authored surface and the old client view is no
    # longer a safe basis for dispatch.
    if scope_last_changed > C:
        return _receipt(
            checked=True,
            outcome="rejected",
            reason="stale_scope_changed",
            supplied_event_seq=C,
            observed_event_seq=A,
            scope_last_changed_seq=scope_last_changed,
            target_last_changed_seq=target_last_changed,
            targets=targets,
        )

    if target_last_changed > C:
        return _receipt(
            checked=True,
            outcome="rejected",
            reason="stale_conflict",
            supplied_event_seq=C,
            observed_event_seq=A,
            scope_last_changed_seq=scope_last_changed,
            target_last_changed_seq=target_last_changed,
            targets=targets,
        )

    return _receipt(
        checked=True,
        outcome="allowed",
        reason="stale_but_disjoint",
        supplied_event_seq=C,
        observed_event_seq=A,
        scope_last_changed_seq=scope_last_changed,
        target_last_changed_seq=target_last_changed,
        targets=targets,
    )


def check_dispatch_staleness(
    *,
    my_current_event_seq_number: Optional[int],
    actual_latest_event_seq: int,
    targets: Sequence[CanonicalWriteTarget],
    state: _SessionDispatchStalenessState,
) -> Dict[str, Any]:
    """
    Return one complete allowed/rejected receipt.

    This is the sole staleness decision function used by the highest façade.
    It normalizes malformed cursors into ``invalid_event_cursor`` and otherwise
    applies the formal decision law without mutating state.
    """
    try:
        return _check_valid_dispatch_staleness_v1(
            my_current_event_seq_number=my_current_event_seq_number,
            actual_latest_event_seq=actual_latest_event_seq,
            targets=targets,
            state=state,
        )
    except (TypeError, ValueError):
        # Invalid raw cursors are intentionally not echoed. The stable receipt
        # field remains Optional[int], so malformed strings/bools do not create
        # a second unversioned union type.
        return _receipt(
            checked=True,
            outcome="rejected",
            reason="invalid_event_cursor",
            supplied_event_seq=None,
            observed_event_seq=int(actual_latest_event_seq),
            scope_last_changed_seq=int(state.last_scope_changed_seq),
            target_last_changed_seq=max(
                (
                    int(
                        state.last_changed_seq_by_target.get(
                            tuple(target),
                            0,
                        )
                    )
                    for target in targets
                ),
                default=0,
            ),
            targets=targets,
        )


def dispatch_rejection_packet_v1(
    *,
    session_id: str,
    staleness_receipt: Mapping[str, Any],
) -> Dict[str, Any]:
    reason = str(staleness_receipt.get("reason") or "")

    return {
        "kind": DISPATCH_STALENESS_REJECTION_KIND_V1,
        "ok": False,
        "applied": False,
        "rejected": True,
        "rejection_kind": reason,
        "dispatch_outcome": "stale_rejected",
        "write_committed": False,
        "events_only": False,
        "session_id": str(session_id),
        "event_kind": None,
        "finished": False,
        "last_error": None,
        "dispatch_staleness": dict(staleness_receipt),
    }


def _error_datum_id_v1(
    key: Any,
) -> Optional[str]:
    """
    Resolve a datum id from an ordinary datum-addressed semantic-error key.

    Reserved aggregate keys such as ``__SPAN__`` return None and are handled
    separately as atomic vector/span rejection markers.
    """
    text = str(key or "").strip()
    if not text or text.startswith("__"):
        return None

    return (
        text
        .split(".", 1)[0]
        .split("[", 1)[0]
        .strip()
        or None
    )


def target_datum_ids_v1(
    targets: Sequence[CanonicalWriteTarget],
) -> set[str]:
    return {
        str(tuple(target)[3])
        for target in targets
        if len(tuple(target)) == 4
        and str(tuple(target)[3] or "").strip()
    }


def dispatch_committed_writes_v1(
    packet: Mapping[str, Any],
    *,
    targets: Sequence[CanonicalWriteTarget],
) -> bool:
    """
    Return whether submitted target positions successfully committed.

    ``last_error`` describes the resulting public UI state. It may contain an
    error for a different datum reached after the submitted targets committed.
    Such an unrelated error must not suppress target index movement.

    The returned boolean means "the submitted conflict-set targets committed",
    not merely "the controller admitted the dispatch". Public packets expose
    that distinction as:

        applied=True, write_committed=False,
        dispatch_outcome="semantic_rejected"

    versus:

        applied=True, write_committed=True,
        dispatch_outcome="applied"

    A write is treated as uncommitted when:
      - no canonical target was submitted;
      - the highest facade rejected the dispatch before controller entry;
      - last_error contains a submitted target;
      - last_error contains a reserved aggregate/span key, which conservatively
        denotes atomic vector/span rejection.

    Controller/system exceptions do not return a normal packet and therefore
    never reach this function.
    """
    target_ids = target_datum_ids_v1(targets)
    if not target_ids:
        return False

    if packet.get("rejected") is True:
        return False

    raw_error = packet.get("last_error")
    if not isinstance(raw_error, Mapping) or not raw_error:
        return True

    for raw_key in raw_error:
        key = str(raw_key or "").strip()

        # Reserved aggregate errors conservatively mean that the submitted
        # vector/span did not commit atomically.
        if key.startswith("__"):
            return False

        datum_id = _error_datum_id_v1(key)
        if datum_id in target_ids:
            return False

    # Errors exist, but only for datums outside the submitted conflict set.
    return True


def record_successful_dispatch_v1(
    *,
    state: _SessionDispatchStalenessState,
    before_scope: CanonicalWriteScope,
    after_scope: CanonicalWriteScope,
    after_event_seq: int,
    targets: Sequence[CanonicalWriteTarget],
    committed_writes: bool,
) -> None:
    seq = int(after_event_seq)

    if committed_writes:
        # "changed" is conflict-domain causality, not value-delta detection:
        # an accepted fill or signal targeting t advances L(t), even when the
        # resulting visible value is equal or the widget reexplodes.
        for target in targets:
            state.last_changed_seq_by_target[tuple(target)] = seq

    previous_scope = state.last_observed_scope
    state.last_observed_scope = tuple(after_scope)

    scope_changed = tuple(before_scope) != tuple(after_scope)
    if previous_scope is not None:
        scope_changed = scope_changed or previous_scope != tuple(after_scope)

    if scope_changed:
        state.last_scope_changed_seq = seq


__all__ = [
    "CanonicalWriteScope",
    "CanonicalWriteTarget",
    "DISPATCH_STALENESS_AUX_NAMESPACE_V1",
    "HostedDispatchStalenessBoundaryV1",
    "DISPATCH_STALENESS_RECEIPT_KIND_V1",
    "DISPATCH_STALENESS_REJECTION_KIND_V1",
    "check_dispatch_staleness",
    "dispatch_committed_writes_v1",
    "dispatch_rejection_packet_v1",
    "forget_dispatch_staleness_session_v1",
    "hosted_dispatch_staleness_boundary_v1",
    "record_successful_dispatch_v1",
    "resolve_canonical_write_targets_v1",
    "restore_dispatch_staleness_state_v1",
    "serialized_dispatch_boundary_v1",
    "snapshot_dispatch_staleness_state_v1",
    "submitted_datum_ids_v1",
    "target_datum_ids_v1",
]