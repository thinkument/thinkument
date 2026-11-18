from __future__ import annotations

"""Copy/paste template: one registered FunkTM filler version.

The filler receives only the current role-projected request and returns one
bounded proposal for the next ordinary STEP. It never mutates session/widget
objects directly and routes writes only through request.pending_datums.
"""

from typing import Any, Dict, Mapping

from _thinksessions.libs_read_write_augmented.chainreactionTM._autoregistry import (
    FunkTMRequest,
    FunkTMResult,
    register_chainreactiontm_version,
)


FUNK_VERSION: str = "my_app.funk.semantic_filler.v1"


def validate_args(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate inert per-role SM args before any chain mutation occurs."""
    default_text = str(raw.get("default_text", "Generated value")).strip()
    if not default_text:
        raise ValueError("default_text must be non-empty")

    max_datums = int(raw.get("max_datums_per_iteration", 8))
    if max_datums < 1:
        raise ValueError("max_datums_per_iteration must be >= 1")

    return {
        "default_text": default_text,
        "max_datums_per_iteration": max_datums,
    }


def _active_micros(decl: Mapping[str, Any]) -> list[Dict[str, Any]]:
    """Read the current active micro grammar in documented compatibility order."""
    datum_args = (
        decl.get("datum_args")
        if isinstance(decl.get("datum_args"), Mapping)
        else {}
    )
    for candidate in (
        datum_args.get("micro_input_fields"),
        datum_args.get("micros"),
        decl.get("micro_input_fields"),
        decl.get("micros"),
    ):
        if isinstance(candidate, list):
            rows = [
                dict(row)
                for row in candidate
                if isinstance(row, Mapping)
            ]
            if rows:
                return rows
    return []


def _first_allowed_choice(micro: Mapping[str, Any]) -> Any | None:
    options = micro.get("options")
    if isinstance(options, list) and options:
        return options[0]

    for validator in list(micro.get("validators") or []):
        if not isinstance(validator, Mapping):
            continue
        path = str(validator.get("path") or "")
        if not path.endswith("validators.choice:in_allowed"):
            continue
        args = validator.get("args")
        args = args if isinstance(args, Mapping) else {}
        allowed = args.get("options")
        if isinstance(allowed, list) and allowed:
            return allowed[0]
    return None


def _value_for_micro(
    micro: Mapping[str, Any],
    *,
    default_text: str,
) -> Any:
    """Generic starter policy. Replace with app/domain semantics."""
    micro_type = str(micro.get("type") or micro.get("kind") or "text").lower()

    if micro_type == "select":
        allowed = _first_allowed_choice(micro)
        return default_text if allowed is None else allowed
    if micro_type in {"integer", "int"}:
        return 1
    if micro_type in {"number", "float"}:
        return 1.0
    if micro_type in {"boolean", "bool", "checkbox", "hidden-pause"}:
        return True
    if micro_type == "object-json":
        return {}
    return default_text


def run(request: FunkTMRequest) -> FunkTMResult:
    """One generated iteration for request.role."""
    fill: Dict[str, Any] = {}
    max_datums = int(request.args["max_datums_per_iteration"])

    # request.pending_datums is the exact generated-write authority.
    for pending in request.pending_datums[:max_datums]:
        datum_id = str(pending["datum_id"])
        decl = pending.get("decl")
        decl = decl if isinstance(decl, Mapping) else {}

        macro: Dict[str, Any] = {}
        for micro in _active_micros(decl):
            name = str(micro.get("name") or "").strip()
            if not name:
                continue
            macro[name] = _value_for_micro(
                micro,
                default_text=str(request.args["default_text"]),
            )

        if macro:
            fill[datum_id] = macro

    # request.ctx is the current role-projected whole U.
    # request.history and request.events are already bounded/projected.
    # request.last_error + semantic_errors_in_row support semantic retry logic.
    return FunkTMResult(
        fill=fill,
        signal=None,
        receipt={
            "kind": "my_app_funk_receipt_v1",
            "role": request.role,
            "filled_datums": sorted(fill),
            "retrying_after_semantic_error": bool(
                request.last_error or request.semantic_errors_in_row > 0
            ),
            "semantic_errors_in_row_seen": int(
                request.semantic_errors_in_row
            ),
            "history_rows_seen": len(request.history.get("rows") or []),
            "events_seen": len(request.events),
        },
    )


def register_funked_filler_v1(*, replace: bool = True) -> None:
    """Call once from app startup registration before launching referenced SM."""
    register_chainreactiontm_version(
        name=FUNK_VERSION,
        run=run,
        validate_args=validate_args,
        replace=replace,
    )


__all__ = [
    "FUNK_VERSION",
    "register_funked_filler_v1",
    "run",
    "validate_args",
]
