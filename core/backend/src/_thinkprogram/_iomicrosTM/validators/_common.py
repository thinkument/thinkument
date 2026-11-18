from __future__ import annotations

from typing import Any

from _thinkprogram._iomicrosTM.core.value_semantics import unbox_leaf


def unwrap(value: Any) -> Any:
    return unbox_leaf(value)


def nonblank_string(value: Any) -> str | None:
    value = unwrap(value)
    if not isinstance(value, str):
        return None
    return value if value.strip() else None


__all__ = ["nonblank_string", "unwrap"]
