from __future__ import annotations

from enum import Enum, auto


class UIMode(Enum):
    """
    Presentation modes for the UI.
    """
    FORM_FILL = auto()
    RUN_COMPLETED_SUMMARY = auto()


class EventKind(Enum):
    """
    Types of events that drive the routing logic.
    """
    ATSTART = auto()
    STEPFNSTEP = auto()
    FORMEXPANSIONSTEP = auto()
    MANUALFILLNEEDEDSTEP = auto()
    ATCOMPLETION = auto()


__all__ = [
    "UIMode",
    "EventKind",
]