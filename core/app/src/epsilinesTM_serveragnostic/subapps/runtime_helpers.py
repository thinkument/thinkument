from __future__ import annotations

"""Public ThinkWidget runtime-argument and history-wire authoring helpers.

These helpers read only the public lifecycle-handler seam:

    fill_data["fill_shell"]["args"]
    fill_data["fill_shell"]["args"]["__kernel"]["past_wires"]

They know no application widget and are safe to reuse across app packs.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping


def authored_widget_args_v1(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    raw = dict(fill_shell or {}).get("args")
    args = dict(raw or {}) if isinstance(raw, Mapping) else {}
    args.pop("__kernel", None)
    return deepcopy(args)


def authored_widget_arg_v1(
    fill_shell: Mapping[str, Any],
    name: str,
) -> Any:
    args = authored_widget_args_v1(fill_shell)
    key = str(name)
    if key not in args:
        raise KeyError(f"authored widget arg is absent: {key!r}")
    return deepcopy(args[key])


def kernel_observation_v1(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    raw_args = dict(fill_shell or {}).get("args")
    if not isinstance(raw_args, Mapping):
        raise TypeError("fill shell args must be a mapping")

    raw_kernel = raw_args.get("__kernel")
    if not isinstance(raw_kernel, Mapping):
        raise TypeError("fill shell args.__kernel must be a mapping")

    return deepcopy(dict(raw_kernel))


def past_wires_v1(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    kernel = kernel_observation_v1(fill_shell)
    raw = kernel.get("past_wires")
    if not isinstance(raw, Mapping):
        raise TypeError("__kernel.past_wires must be a mapping")
    return deepcopy(dict(raw))


def wire_rows_v1(
    fill_shell: Mapping[str, Any],
    wire_name: str,
) -> list[Dict[str, Any]]:
    """Normalize one public wire slot to ``list[row]``."""
    wires = past_wires_v1(fill_shell)
    key = str(wire_name)

    if key not in wires:
        return []

    raw = wires[key]
    if isinstance(raw, Mapping):
        return [deepcopy(dict(raw))]

    if isinstance(raw, list):
        if not all(isinstance(row, Mapping) for row in raw):
            raise TypeError(f"wire {key!r} list must contain mapping rows")
        return [deepcopy(dict(row)) for row in raw]

    raise TypeError(
        f"wire {key!r} must materialize as mapping or list[mapping]"
    )


def wire_container_kind_v1(
    fill_shell: Mapping[str, Any],
    wire_name: str,
) -> str:
    wires = past_wires_v1(fill_shell)
    key = str(wire_name)

    if key not in wires:
        return "absent"
    if isinstance(wires[key], Mapping):
        return "one_row"
    if isinstance(wires[key], list):
        return "row_list"
    raise TypeError(
        f"wire {key!r} has unsupported container "
        f"{type(wires[key]).__name__}"
    )


def runtime_write_row_state_v1(
    row: Mapping[str, Any],
) -> Dict[str, Any]:
    """Read the exact ``row['value']['state']`` lifecycle-state pocket."""
    if "value" not in row:
        raise KeyError("runtime write row is missing exact key 'value'")
    value = row["value"]
    if not isinstance(value, Mapping):
        raise TypeError("runtime write row['value'] must be a mapping")

    if "state" not in value:
        raise KeyError("runtime write row['value'] is missing exact key 'state'")
    state = value["state"]
    if not isinstance(state, Mapping):
        raise TypeError("runtime write row['value']['state'] must be a mapping")
    return deepcopy(dict(state))


def runtime_write_row_identity_v1(
    row: Mapping[str, Any],
) -> Dict[str, str]:
    """Read exact source identity fields from one kernel history row."""
    public_step_name = row.get("public_step_name")
    datum_id = row.get("key")
    value_ref = row.get("value_ref")

    if not isinstance(public_step_name, str) or not public_step_name:
        raise TypeError(
            "runtime write row['public_step_name'] must be non-empty str"
        )
    if not isinstance(datum_id, str) or not datum_id:
        raise TypeError("runtime write row['key'] must be non-empty str")
    if not isinstance(value_ref, Mapping):
        raise TypeError("runtime write row['value_ref'] must be a mapping")

    ref_datum_id = value_ref.get("datum_id")
    if ref_datum_id != datum_id:
        raise ValueError(
            "runtime write row identity mismatch: "
            "row['value_ref']['datum_id'] != row['key']"
        )

    return {
        "public_step_name": public_step_name,
        "datum_id": datum_id,
    }


def wire_state_index_v1(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build a uniform wire-name -> ordered source-state observation."""
    wires = past_wires_v1(fill_shell)
    out: Dict[str, Any] = {}

    for wire_name in sorted(wires):
        rows = wire_rows_v1(fill_shell, wire_name)
        out[wire_name] = {
            "container_kind": wire_container_kind_v1(fill_shell, wire_name),
            "row_count": len(rows),
            "rows": [
                {
                    "source": runtime_write_row_identity_v1(row),
                    "state": runtime_write_row_state_v1(row),
                }
                for row in rows
            ],
        }

    return out


def one_wire_state_v1(
    fill_shell: Mapping[str, Any],
    wire_name: str,
) -> Dict[str, Any]:
    rows = wire_rows_v1(fill_shell, wire_name)
    if len(rows) != 1:
        raise ValueError(
            f"wire {wire_name!r} expected exactly one row; got {len(rows)}"
        )
    return runtime_write_row_state_v1(rows[0])


def many_wire_states_v1(
    fill_shell: Mapping[str, Any],
    wire_name: str,
) -> list[Dict[str, Any]]:
    return [
        runtime_write_row_state_v1(row)
        for row in wire_rows_v1(fill_shell, wire_name)
    ]


__all__ = [
    "authored_widget_arg_v1",
    "authored_widget_args_v1",
    "kernel_observation_v1",
    "many_wire_states_v1",
    "one_wire_state_v1",
    "past_wires_v1",
    "runtime_write_row_identity_v1",
    "runtime_write_row_state_v1",
    "wire_container_kind_v1",
    "wire_rows_v1",
    "wire_state_index_v1",
]
