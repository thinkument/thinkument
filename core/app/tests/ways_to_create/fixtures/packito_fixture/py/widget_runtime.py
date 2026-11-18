from __future__ import annotations

"""Small public lifecycle helpers used by Packito widgets.

The helpers intentionally read only the documented lifecycle surface delivered
through ``fill_data[\"fill_shell\"]``. They are app-local conveniences, not a
second widget runtime API.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping


def authored_args_v1(fill_shell: Mapping[str, Any]) -> Dict[str, Any]:
    raw = dict(fill_shell or {}).get("args")
    args = dict(raw or {}) if isinstance(raw, Mapping) else {}
    args.pop("__kernel", None)
    return deepcopy(args)


def past_wires_v1(fill_shell: Mapping[str, Any]) -> Dict[str, Any]:
    raw_args = dict(fill_shell or {}).get("args")
    args = dict(raw_args or {}) if isinstance(raw_args, Mapping) else {}
    kernel = args.get("__kernel")
    kernel = kernel if isinstance(kernel, Mapping) else {}
    raw = kernel.get("past_wires")
    return deepcopy(dict(raw or {})) if isinstance(raw, Mapping) else {}


def wire_rows_v1(
    fill_shell: Mapping[str, Any],
    wire_name: str,
) -> list[Dict[str, Any]]:
    raw = past_wires_v1(fill_shell).get(str(wire_name))
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        return [deepcopy(dict(raw))]
    if isinstance(raw, list):
        if not all(isinstance(row, Mapping) for row in raw):
            raise TypeError(f"wire {wire_name!r} must contain mapping rows")
        return [deepcopy(dict(row)) for row in raw]
    raise TypeError(
        f"wire {wire_name!r} must materialize as a mapping or list[mapping]"
    )


def runtime_state_from_row_v1(row: Mapping[str, Any]) -> Dict[str, Any]:
    value = row.get("value")
    if not isinstance(value, Mapping):
        return {}
    state = value.get("state")
    return deepcopy(dict(state or {})) if isinstance(state, Mapping) else {}


def wire_state_index_v1(fill_shell: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for wire_name in sorted(past_wires_v1(fill_shell)):
        rows = wire_rows_v1(fill_shell, wire_name)
        out[wire_name] = {
            "row_count": len(rows),
            "states": [runtime_state_from_row_v1(row) for row in rows],
            "sources": [
                {
                    "public_step_name": row.get("public_step_name"),
                    "datum_id": row.get("key"),
                }
                for row in rows
            ],
        }
    return out


def lifecycle_shell_v1(
    prior: Mapping[str, Any],
    *,
    title: str,
    micros: list[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return the next current-effective shell without erasing platform data.

    A re-explosion owns the next title/micro grammar, but it must not silently
    discard unrelated authored or kernel-owned shell fields. In particular,
    Packito relies on ``args.hai_renderer`` as the small stable Python -> JS
    renderer selector, while ``args.__kernel`` carries runtime wire history.

    This follows the same safe pattern used by the established dry-run widgets:
    copy the current shell, then replace only the fields this helper owns.
    """

    shell = deepcopy(dict(prior or {}))
    shell["title"] = str(title)
    shell["micros"] = deepcopy(micros)
    return shell


__all__ = [
    "authored_args_v1",
    "lifecycle_shell_v1",
    "past_wires_v1",
    "runtime_state_from_row_v1",
    "wire_rows_v1",
    "wire_state_index_v1",
]
