from __future__ import annotations

from enum import Enum, auto


class SystemAction(Enum):
    """
    Internal directives for the system flow.
    """
    KEEP_STEPPING = auto()
    KEEP_UNDOING = auto()


class UserAction(Enum):
    """
    User-invoked actions.
    """
    STEP = auto()
    UNDO = auto()
    REDO = auto()


__all__ = [
    "SystemAction",
    "UserAction",
]