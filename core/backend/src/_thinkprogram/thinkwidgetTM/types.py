from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True, slots=True)
class Reexplode:
    next_fill_shell: Mapping[str, Any]
    pre_computed_fills: Optional[Mapping[str, Any]] = None
    prefill_hints: Optional[Mapping[str, Any]] = None