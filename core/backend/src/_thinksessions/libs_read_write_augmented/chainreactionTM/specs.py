from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional


ArgsValidator = Callable[[Mapping[str, Any]], Dict[str, Any]]
VersionFn = Callable[["FunkTMRequest"], "FunkTMResult"]


@dataclass(frozen=True)
class RegisteredFillerFunktion:
    name: str
    run: VersionFn
    validate_args: ArgsValidator


@dataclass(frozen=True)
class FunkTMRequest:
    session_id: str
    role: str
    args: Dict[str, Any]
    ctx: Dict[str, Any]
    pending_datums: list[Dict[str, Any]]
    history: Dict[str, Any]
    last_error: Optional[Dict[str, Any]]
    semantic_errors_in_row: int
    events: list[Dict[str, Any]] = field(default_factory=list)

    @property
    def recent_events(self) -> list[Dict[str, Any]]:
        """Compatibility/readability alias for the event queue tail."""
        return list(self.events)


@dataclass(frozen=True)
class FunkTMResult:
    fill: Dict[str, Any]
    signal: Optional[Dict[str, Any]]
    receipt: Dict[str, Any]

