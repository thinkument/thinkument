from __future__ import annotations

import warnings
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Tuple

from __exceptions.engine import (
    ProgramEndReachedError,
    ProgramStartReachedError,
)

from _thinksessions.run.runme_surfaces_in.controller_apis_action_packet import (
    controller_signal_to_engine_dict_v1,
    normalize_controller_action_packet_v1,
)

from ._events import (
    ControllerEventCallback,
)

from ._actions import (
    SystemAction,
    UserAction,
)
from ._states import (
    EventKind,
    UIMode,
)
from ._transitions import (
    get_routing_map,
)
from ._normalize_external_fills import (
    _collapse_composite_keys,
    _normalize_for_composite_platform,
    _normalize_repeated_submit_values,
)
from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    EXPLOSION_EVENTS_CALLBACK_KEY,
    CONTROLLER_EVENTS_CALLBACK_KEY,
)


ControllerDispatchCallbacks = Dict[str, Optional[ControllerEventCallback]]


def normalize_controller_dispatch_callbacks_v1(
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
) -> ControllerDispatchCallbacks:
    out: ControllerDispatchCallbacks = {
        EXPLOSION_EVENTS_CALLBACK_KEY: None,
        CONTROLLER_EVENTS_CALLBACK_KEY: None,
    }

    if isinstance(threaded_callbacks, Mapping):
        for key, value in threaded_callbacks.items():
            key_s = str(key)
            out[key_s] = value if callable(value) else None

    return out


class ControllerSessionOps(Protocol):
    """
    Minimal liaison surface required by the page-flow controller.

    The public session API injects an object implementing this protocol. The
    controller remains unaware of any request validation, authorization, or
    context modulation performed before this boundary.
    """

    def step_session(
        self,
        session_id: str,
        fill: Optional[Dict[str, Any]] = None,
        signal: Optional[Dict[str, Any]] = None,
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...

    def undo_last_step(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        ...

    def redo_last_step(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        ...

    def get_session_context(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        ...

    def get_outputs(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        ...


# ---------------------------------------------------------------------------
# Injected-session-operation execution
# ---------------------------------------------------------------------------


def _perform_step(
    session_ops: ControllerSessionOps,
    session_id: str,
    fill: Optional[Dict[str, Any]],
    signal: Optional[Dict[str, Any]] = None,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Execute one liaison STEP.

    Returns
    -------
    ``(ctx, at_completion)``

    Recovery
    --------
    ``ProgramEndReachedError`` causes a context fetch through the same injected
    liaison and marks the flow complete.
    """
    try:
        ctx = session_ops.step_session(
            session_id,
            fill=fill,
            signal=signal,
            threaded_callbacks=threaded_callbacks,
        )
        at_completion = (ctx or {}).get("kind") == "ATCOMPLETION"
        return ctx, bool(at_completion)

    except ProgramEndReachedError:
        ctx = session_ops.get_session_context(session_id)
        return ctx, True


def _perform_undo(
    session_ops: ControllerSessionOps,
    session_id: str,
) -> Tuple[Dict[str, Any], bool]:
    """
    Execute one liaison UNDO.

    Returns
    -------
    ``(ctx, at_start)``

    Recovery
    --------
    ``ProgramStartReachedError`` causes a context fetch through the same
    injected liaison and marks the flow as being at program start.
    """
    try:
        ctx = session_ops.undo_last_step(session_id)
        at_start = (ctx or {}).get("kind") == "ATSTART"
        return ctx, bool(at_start)

    except ProgramStartReachedError:
        ctx = session_ops.get_session_context(session_id)
        return ctx, True


def _perform_redo(
    session_ops: ControllerSessionOps,
    session_id: str,
) -> Tuple[Dict[str, Any], bool]:
    """
    Execute one liaison REDO.

    Returns
    -------
    ``(ctx, at_completion)``
    """
    redo = getattr(
        session_ops,
        "redo_last_step",
        None,
    )
    if not callable(redo):
        raise NotImplementedError(
            "session ops does not support redo_last_step"
        )

    ctx = redo(session_id)
    at_completion = (ctx or {}).get("kind") == "ATCOMPLETION"
    return ctx, bool(at_completion)


def _map_event_kind(
    kind_str: str,
) -> EventKind:
    """Convert a raw context kind into a validated EventKind."""
    try:
        return EventKind[kind_str.upper()]
    except KeyError:
        raise RuntimeError(
            f"Unknown event kind: {kind_str!r}"
        ) from None


__all__ = [
    "Any",
    "Callable",
    "Dict",
    "Mapping",
    "Optional",
    "Protocol",
    "Tuple",
    "warnings",
    "EventKind",
    "SystemAction",
    "UIMode",
    "UserAction",
    "EXPLOSION_EVENTS_CALLBACK_KEY",
    "CONTROLLER_EVENTS_CALLBACK_KEY",
    "get_routing_map",
    "ControllerSessionOps",
    "controller_signal_to_engine_dict_v1",
    "normalize_controller_action_packet_v1",
    "_collapse_composite_keys",
    "_normalize_repeated_submit_values",
    "_normalize_for_composite_platform",
    "_perform_step",
    "_perform_undo",
    "_perform_redo",
    "_map_event_kind",
]