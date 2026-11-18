from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ._helpers import require_nonempty_str


@dataclass(frozen=True)
class AppearanceV1:
    logical_widget_id: str
    step_id: str
    datum_id: str


def source_logical_widget_ids_v1(
    *,
    source: Any,
    current_logical_widget_id: str,
    path: str,
) -> list[str]:
    if isinstance(source, str):
        return [source]

    if isinstance(source, list):
        if not source or not all(isinstance(x, str) and x for x in source):
            raise ValueError(f"{path}.from list must be non-empty list[str]")
        return list(source)

    if isinstance(source, Mapping):
        source_map = dict(source)

        if source_map == {"self": "previous"}:
            return [current_logical_widget_id]

        if set(source_map) == {"widget", "occurrence"}:
            occurrence = str(source_map["occurrence"])
            if occurrence != "previous":
                raise ValueError(f"{path}.from.occurrence supports only 'previous'")
            return [require_nonempty_str(source_map["widget"], f"{path}.from.widget")]

    raise ValueError(f"{path}.from has unsupported source form")


def safe_alias_v1(*parts: str) -> str:
    raw = "_".join(str(p) for p in parts if str(p))
    out = []
    for ch in raw:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    return "_".join("".join(out).split("_"))


def unique_alias_v1(
    base_alias: str,
    existing: Mapping[str, Any],
) -> str:
    """
    Deterministic collision-safe aliasing.

    The normal alias includes logical widget, wire, source id, selector, and
    source step id. This suffix guard protects unusual ids that sanitize to the
    same string.
    """
    candidate = require_nonempty_str(base_alias, "history alias")
    if candidate not in existing:
        return candidate

    i = 2
    while True:
        suffixed = f"{candidate}_{i}"
        if suffixed not in existing:
            return suffixed
        i += 1