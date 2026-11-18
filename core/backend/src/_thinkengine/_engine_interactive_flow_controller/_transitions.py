from __future__ import annotations

from typing import Mapping, Union, Dict, Any

from ._states import UIMode, EventKind
from ._actions import SystemAction, UserAction


RouteTarget = Union[UIMode, SystemAction]
RoutingMap = Mapping[UserAction, Mapping[EventKind, RouteTarget]]


# ---------------------------------------------------------------------------
# Default routing (production behavior)
# ---------------------------------------------------------------------------

BASE_ROUTING_MAP: Dict[UserAction, Dict[EventKind, RouteTarget]] = {
    UserAction.STEP: {
        EventKind.ATSTART:               SystemAction.KEEP_STEPPING,
        EventKind.STEPFNSTEP:            SystemAction.KEEP_STEPPING,
        EventKind.FORMEXPANSIONSTEP:     SystemAction.KEEP_STEPPING,
        EventKind.MANUALFILLNEEDEDSTEP:  UIMode.FORM_FILL,
        EventKind.ATCOMPLETION:          UIMode.RUN_COMPLETED_SUMMARY,
    },
    UserAction.UNDO: {
        EventKind.ATSTART:               SystemAction.KEEP_STEPPING,
        EventKind.STEPFNSTEP:            SystemAction.KEEP_UNDOING,
        EventKind.FORMEXPANSIONSTEP:     SystemAction.KEEP_UNDOING,
        EventKind.MANUALFILLNEEDEDSTEP:  UIMode.FORM_FILL,
        EventKind.ATCOMPLETION:          UIMode.RUN_COMPLETED_SUMMARY,
    },
    UserAction.REDO: {
        EventKind.ATSTART:               SystemAction.KEEP_STEPPING,
        EventKind.STEPFNSTEP:            SystemAction.KEEP_STEPPING,
        EventKind.FORMEXPANSIONSTEP:     SystemAction.KEEP_STEPPING,
        EventKind.MANUALFILLNEEDEDSTEP:  UIMode.FORM_FILL,
        EventKind.ATCOMPLETION:          UIMode.RUN_COMPLETED_SUMMARY,
    },
}


# ---------------------------------------------------------------------------
# Opt-in routing variants (tests / experiments)
# ---------------------------------------------------------------------------

def get_routing_map(ui_config: Mapping[str, Any] | None = None) -> RoutingMap:
    """
    Return the routing map for this session.
    """
    ui_config = ui_config or {}

    return BASE_ROUTING_MAP


__all__ = [
    "RouteTarget",
    "RoutingMap",
    "get_routing_map",
]