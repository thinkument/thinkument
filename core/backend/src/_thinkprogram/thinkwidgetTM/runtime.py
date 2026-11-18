from __future__ import annotations

from typing import Any, Dict, Mapping

from .constants import ADAPTER_RESERVED_STATE_KEY
from .types import Reexplode


def _state_reserved(state: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(dict(state or {}).get(ADAPTER_RESERVED_STATE_KEY) or {})


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _value_delta(
    current: Mapping[str, Any],
    previous: Mapping[str, Any],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in dict(current or {}).items():
        if key not in previous or previous.get(key) != value:
            out[str(key)] = value
    return out


def _adapter_inputs_from_q(
    q: Mapping[str, Any],
    state: Mapping[str, Any],
):
    signal = dict(q.get("signal") or {})
    signal_kind = str(signal.get("kind") or q.get("signal_kind") or "fill")
    signal_info = dict(signal.get("info") or q.get("signal_info") or {})

    position = {
        "form_id": str(q["form_id"]),
        "frame_id": str(q["frame_id"]),
        "span_id": str(q["span_id"]),
        "datum_id": str(q["datum_id"]),
    }

    reserved = _state_reserved(state)
    last_precomputed = _dict_or_empty(reserved.get("last_precomputed_fills"))
    current_fills = _dict_or_empty(q.get("partial_fill"))

    fill_data = {
        "fill_shell": dict(q.get("datum") or {}),
        "current_fills": current_fills,
        "prefill_hints": _dict_or_empty(q.get("prefill")),
        "pre_computed_fills": last_precomputed,
        "changed_fills": (
            {}
            if signal_kind == "mount"
            else _value_delta(current_fills, last_precomputed)
        ),
        "shell_satisfaction_check": bool(q.get("structurally_satisfied")),
    }

    limits = {
        "max_reexplosions": int(q.get("max_reexplosions", 0) or 0),
        "max_messages": int(q.get("max_messages", 0) or 0),
    }

    stats = {
        "reexplode_count": int(q.get("reexplode_count", 0) or 0),
        "num_messages": len(list(q.get("messages") or [])),
    }

    signal_out = {
        "kind": signal_kind,
        "info": signal_info,
    }

    return position, fill_data, limits, stats, signal_out


def _preserve_pre_mount_controller_metadata_on_reexplode(
    *,
    prior_shell: Mapping[str, Any],
    next_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Reexplode replaces the widget-authored datum shell, but it must not erase
    controller/compiler-owned metadata assigned before mount.

    Role mismatch modulation depends on datum.roles surviving mount-shelling.
    Tags, system flags, and authoritative markers are the same kind of
    shell-level platform metadata.

    Intentionally not otherwise preserved:
      - ordinary args
      - lifecycle
      - micros
      - title

    Those are the widget-authored shell surface that Reexplode is allowed to
    replace.
    """
    out = dict(next_shell)
    prior = dict(prior_shell or {})

    for protected_key in (
        "roles",
        "role",
        "tags",
        "system_flags",
        "authoritative",
    ):
        if protected_key in prior and protected_key not in out:
            out[protected_key] = prior[protected_key]

    prior_args_raw = prior.get("args")
    next_args_raw = out.get("args")

    prior_args = (
        dict(prior_args_raw)
        if isinstance(prior_args_raw, Mapping)
        else {}
    )
    next_args = (
        dict(next_args_raw)
        if isinstance(next_args_raw, Mapping)
        else {}
    )

    return out


def adapter_result_to_platform_result(
    instance: Any,
    ergonomic_result: Any,
) -> Dict[str, Any]:
    messages = [dict(x) for x in instance._messages]
    state = dict(instance._state)

    if ergonomic_result is True:
        return {
            "status": "done",
            "state": state,
            "messages": messages,
        }

    if isinstance(ergonomic_result, Reexplode):
        next_shell = _preserve_pre_mount_controller_metadata_on_reexplode(
            prior_shell=dict(instance._q.get("datum") or {}),
            next_shell=dict(ergonomic_result.next_fill_shell),
        )
        precomputed = _dict_or_empty(ergonomic_result.pre_computed_fills)
        prefill_hints = _dict_or_empty(ergonomic_result.prefill_hints)

        reserved = dict(state.get(ADAPTER_RESERVED_STATE_KEY) or {})
        reserved["last_precomputed_fills"] = dict(precomputed)
        state[ADAPTER_RESERVED_STATE_KEY] = reserved

        out: Dict[str, Any] = {
            "status": "reexplode",
            "datum": next_shell,
            "state": state,
            "messages": messages,
        }

        if ergonomic_result.pre_computed_fills is not None:
            out["fill"] = precomputed

        if ergonomic_result.prefill_hints is not None:
            out["prefill"] = prefill_hints

        return out

    raise TypeError(
        "datum widget class handlers must return True or Reexplode(...); "
        f"got {type(ergonomic_result).__name__}"
    )