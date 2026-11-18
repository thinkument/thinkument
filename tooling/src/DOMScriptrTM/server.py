"""Framework-agnostic server contracts and normalization."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from types import MappingProxyType
from typing import Any, Mapping, TypeAlias

from .errors import ServerContractError

ServerValue: TypeAlias = "Server | Mapping[str, str] | str"
# Kept intentionally broad: Run normalizes callables, awaitables, sync context
# managers, async context managers, and direct ServerValue objects at runtime.
ServerStarter: TypeAlias = Any


@dataclass(frozen=True, **({"slots": True} if sys.version_info >= (3, 10) else {}))
class Server:
    """A ready server represented only by its named public URLs."""

    urls: Mapping[str, str]

    def __post_init__(self) -> None:
        normalized = _normalize_urls(self.urls)
        object.__setattr__(self, "urls", MappingProxyType(normalized))

    @classmethod
    def coerce(cls, value: ServerValue) -> "Server":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls({"web": value})
        if isinstance(value, Mapping):
            return cls(value)
        raise ServerContractError(
            "server starter must yield/return Server, Mapping[str, str], or str; "
            f"got {type(value).__name__}"
        )


def _normalize_urls(urls: Mapping[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in urls.items():
        if not isinstance(key, str) or not key:
            raise ServerContractError("server URL names must be non-empty strings")
        if not isinstance(value, str) or not value:
            raise ServerContractError(f"server URL {key!r} must be a non-empty string")
        normalized[key] = value
    return normalized
