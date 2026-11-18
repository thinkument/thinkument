from __future__ import annotations

"""Dead-JSON-like dry-run action-attempt specification helpers, version 1.

These helpers describe what a downstream dispatcher attempts. They do not
create sessions, dispatch actions, read events, or know any application widget.
The mappings they return are consumed by ``live_session_dry_run_v1``.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping, Optional


DRY_RUN_ACTION_KIND_ORDINARY_V1 = "ordinary"
DRY_RUN_ACTION_KIND_PREFLIGHT_EXCEPTION_V1 = "preflight_exception"
DRY_RUN_ACTION_KIND_PREFLIGHT_REJECTION_V1 = "preflight_rejection"


def _role_or_none(role: Any) -> Optional[str]:
    return None if role is None else str(role)


def _identity_or_none(identity_id: Any) -> Optional[str]:
    return None if identity_id is None else str(identity_id)


def _ordinary_action_v1(
    *,
    action: str,
    fill: Any = None,
    signal: Any = None,
    expect: Optional[Mapping[str, Any]] = None,
    role: Any = None,
    identity_id: Any = None,
    views: Any = None,
    note: str = "",
    cursor: Any = None,
    save_cursor: Optional[str] = None,
    blanket: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    A: Dict[str, Any] = {
        "action": str(action),
        "role": _role_or_none(role),
        "identity_id": _identity_or_none(identity_id),
        "my_current_event_seq_number": deepcopy(cursor),
    }

    if str(action).upper() == "STEP":
        A["user_fill"] = {} if fill is None else deepcopy(fill)
        A["user_signal"] = deepcopy(signal)

    return {
        "kind": DRY_RUN_ACTION_KIND_ORDINARY_V1,
        "A": A,
        "E": deepcopy(dict(expect or {})),
        "views": deepcopy(list(views or [])),
        "blanket": deepcopy(dict(blanket or {})),
        "save_cursor": None if save_cursor is None else str(save_cursor),
        "note": str(note),
    }


def STEP(
    *,
    fill: Any = None,
    signal: Any = None,
    expect: Optional[Mapping[str, Any]] = None,
    role: Any = None,
    identity_id: Any = None,
    views: Any = None,
    note: str = "",
    cursor: Any = None,
    save_cursor: Optional[str] = None,
    blanket: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Describe one admitted-or-expected-to-be-admitted STEP attempt."""
    return _ordinary_action_v1(
        action="STEP",
        fill=fill,
        signal=signal,
        expect=expect,
        role=role,
        identity_id=identity_id,
        views=views,
        note=note,
        cursor=cursor,
        save_cursor=save_cursor,
        blanket=blanket,
    )


def UNDO(
    *,
    expect: Optional[Mapping[str, Any]] = None,
    role: Any = None,
    identity_id: Any = None,
    views: Any = None,
    note: str = "",
    cursor: Any = None,
    save_cursor: Optional[str] = None,
    blanket: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Describe one admitted-or-expected-to-be-admitted UNDO attempt."""
    return _ordinary_action_v1(
        action="UNDO",
        expect=expect,
        role=role,
        identity_id=identity_id,
        views=views,
        note=note,
        cursor=cursor,
        save_cursor=save_cursor,
        blanket=blanket,
    )


def REDO(
    *,
    expect: Optional[Mapping[str, Any]] = None,
    role: Any = None,
    identity_id: Any = None,
    views: Any = None,
    note: str = "",
    cursor: Any = None,
    save_cursor: Optional[str] = None,
    blanket: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Describe one admitted-or-expected-to-be-admitted REDO attempt."""
    return _ordinary_action_v1(
        action="REDO",
        expect=expect,
        role=role,
        identity_id=identity_id,
        views=views,
        note=note,
        cursor=cursor,
        save_cursor=save_cursor,
        blanket=blanket,
    )


def PREFLIGHT_EXCEPTION(
    *,
    action: Any = "STEP",
    fill: Any = None,
    signal: Any = None,
    role: Any = None,
    identity_id: Any = None,
    cursor: Any = None,
    exception_type: str,
    contains: str,
    note: str = "",
) -> Dict[str, Any]:
    """Describe an attempt expected to raise before controller entry.

    ``fill`` and ``signal`` are intentionally preserved exactly. This permits
    malformed request-shape lessons to exercise the real public normalizer.
    """
    return {
        "kind": DRY_RUN_ACTION_KIND_PREFLIGHT_EXCEPTION_V1,
        "A": {
            "action": action,
            "user_fill": deepcopy(fill),
            "user_signal": deepcopy(signal),
            "role": _role_or_none(role),
            "identity_id": _identity_or_none(identity_id),
            "my_current_event_seq_number": deepcopy(cursor),
        },
        "exception": {
            "type": str(exception_type),
            "contains": str(contains),
        },
        "note": str(note),
    }


def PREFLIGHT_REJECTION(
    *,
    action: Any = "STEP",
    fill: Any = None,
    signal: Any = None,
    role: Any = None,
    identity_id: Any = None,
    cursor: Any = None,
    rejection_kind: str,
    note: str = "",
) -> Dict[str, Any]:
    """Describe an eventless structured highest-facade rejection."""
    return {
        "kind": DRY_RUN_ACTION_KIND_PREFLIGHT_REJECTION_V1,
        "A": {
            "action": action,
            "user_fill": {} if fill is None else deepcopy(fill),
            "user_signal": deepcopy(signal),
            "role": _role_or_none(role),
            "identity_id": _identity_or_none(identity_id),
            "my_current_event_seq_number": deepcopy(cursor),
        },
        "rejection_kind": str(rejection_kind),
        "note": str(note),
    }


__all__ = [
    "DRY_RUN_ACTION_KIND_ORDINARY_V1",
    "DRY_RUN_ACTION_KIND_PREFLIGHT_EXCEPTION_V1",
    "DRY_RUN_ACTION_KIND_PREFLIGHT_REJECTION_V1",
    "PREFLIGHT_EXCEPTION",
    "PREFLIGHT_REJECTION",
    "REDO",
    "STEP",
    "UNDO",
]