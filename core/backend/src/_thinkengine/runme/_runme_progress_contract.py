"""
Central scripted/session progress contract.

This adjacent module owns scripting-specific rollout mechanics:

    - public progress signatures
    - derived step budgets
    - durable stop-kind policy
    - loud no-progress / budget-exhaustion errors

It deliberately imports no UI renderer, no launch layer, and no concrete session
API implementation.
"""

from typing import Any, Mapping, Sequence, Tuple

from ._errors import ProgramRunStallError
from _thinkprogram._iomicrosTM.tiny_helpers import mapping_from_any_v1, json_sanitize_v1



PROGRAM_DURABLE_STOP_KINDS: Tuple[str, ...] = (
    "MANUALFILLNEEDEDSTEP",
    "ATCOMPLETION",
)

PROGRAM_UNDO_DURABLE_STOP_KINDS_V1: Tuple[str, ...] = (
    "ATSTART",
    "MANUALFILLNEEDEDSTEP",
    "ATCOMPLETION",
)

PROGRAM_AUTO_ADVANCE_KINDS_V1: Tuple[str, ...] = (
    "ATSTART",
    "STEPFNSTEP",
    "FORMEXPANSIONSTEP",
)

PROGRAM_DEFAULT_MAX_STEP_UNTIL_STOP_STEPS_V1 = 48
PROGRAM_DEFAULT_MAX_STEPS_V1 = 256
PROGRAM_ROLLOUT_MAX_EXPLICIT_STEPS_V1 = 4096
PROGRAM_ROLLOUT_BUDGET_FLOOR_V1 = 16
PROGRAM_ROLLOUT_BUDGET_PER_PROGRAM_STEP_V1 = 8


def _int_or_default_v1(value: Any, default: int) -> int:
    if value is None:
        return int(default)
    try:
        return int(value)
    except Exception:
        return int(default)


def program_progress_signature_v1(
    ctx: Mapping[str, Any],
) -> Tuple[Any, ...]:
    """
    Cheap public progress fingerprint.

    Zero is a valid cursor index and total. Never use `value or -1`, because
    that maps a legitimate zero to the missing-value sentinel.
    """
    cursor = mapping_from_any_v1(ctx.get("cursor"))
    state = mapping_from_any_v1(ctx.get("state"))
    lifecycle_epoch = state.get("datum_lifecycle_epoch")

    return (
        _int_or_default_v1(cursor.get("index"), -1),
        _int_or_default_v1(cursor.get("total"), -1),
        str(ctx.get("kind") or ""),
        tuple(
            str(x)
            for x in list(ctx.get("datum_widgets_on_this_span") or ())
        ),
        repr(ctx.get("last_error")),
        repr(state.get("pending_multiframespec_id")),
        repr(lifecycle_epoch),
        tuple(
            str(x)
            for x in list(
                state.get("forms_emitted_order") or ()
            )
        ),
    )


def program_response_signature_v1(resp: Mapping[str, Any]) -> Tuple[Any, ...]:
    ctx = resp.get("ctx")
    ctx_sig = program_progress_signature_v1(ctx) if isinstance(ctx, Mapping) else ()
    return (
        str(resp.get("event_kind") or ""),
        str(resp.get("ui_mode") or ""),
        tuple(str(x) for x in list(resp.get("datum_widgets_on_this_span") or ())),
        ctx_sig,
    )


def program_len_from_api_snapshot_v1(api: Any, session_id: str) -> int:
    try:
        exporter = getattr(api, "export_session_snapshot", None)
        if callable(exporter):
            snap = exporter(session_id)
            if isinstance(snap, Mapping):
                program = snap.get("program")
                if isinstance(program, Sequence) and not isinstance(
                    program,
                    (str, bytes, bytearray),
                ):
                    return len(program)
    except Exception:
        return 0
    return 0


def derived_program_budget_v1(
    *,
    program_len: int = 0,
    explicit_max_steps: Any = None,
    default_max_steps: int = PROGRAM_DEFAULT_MAX_STEPS_V1,
    floor: int = PROGRAM_ROLLOUT_BUDGET_FLOOR_V1,
    per_program_step: int = PROGRAM_ROLLOUT_BUDGET_PER_PROGRAM_STEP_V1,
    cap: int = PROGRAM_ROLLOUT_MAX_EXPLICIT_STEPS_V1,
    reject_excessive_explicit: bool = True,
) -> int:
    if explicit_max_steps is not None:
        try:
            value = int(explicit_max_steps)
        except Exception as exc:
            raise ValueError(
                f"max_steps must be an integer-like value, got {explicit_max_steps!r}"
            ) from exc
        if value <= 0:
            raise ValueError(f"max_steps must be > 0, got {value!r}")
        if reject_excessive_explicit and value > int(cap):
            raise ProgramRunStallError(
                "script action requested an excessive max_steps budget; "
                f"max_steps={value!r}, absolute_cap={int(cap)!r}. "
                "This is rejected before rollout so scripts cannot turn bounded "
                "progress checks into long-running loops."
            )
        return min(value, int(cap))

    derived = int(program_len) * int(per_program_step) + int(floor)
    return min(
        int(cap),
        max(int(floor), int(default_max_steps), int(derived)),
    )


def derived_program_budget_from_api_v1(
    *,
    api: Any,
    session_id: str,
    explicit_max_steps: Any = None,
    default_max_steps: int = PROGRAM_DEFAULT_MAX_STEPS_V1,
    floor: int = PROGRAM_ROLLOUT_BUDGET_FLOOR_V1,
    per_program_step: int = PROGRAM_ROLLOUT_BUDGET_PER_PROGRAM_STEP_V1,
    cap: int = PROGRAM_ROLLOUT_MAX_EXPLICIT_STEPS_V1,
    reject_excessive_explicit: bool = True,
) -> int:
    program_len = program_len_from_api_snapshot_v1(api, session_id)
    return derived_program_budget_v1(
        program_len=program_len,
        explicit_max_steps=explicit_max_steps,
        default_max_steps=default_max_steps,
        floor=floor,
        per_program_step=per_program_step,
        cap=cap,
        reject_excessive_explicit=reject_excessive_explicit,
    )


def durable_stop_kinds_from_action_v1(
    action: Mapping[str, Any],
    *,
    default_stop_kinds: Sequence[str] = PROGRAM_DURABLE_STOP_KINDS,
) -> set[str]:
    raw = action.get("stop_kinds", default_stop_kinds)
    if raw is None:
        out = set(str(x) for x in default_stop_kinds)
    elif isinstance(raw, str):
        out = {raw}
    elif isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        out = {str(x) for x in raw}
    else:
        out = {str(raw)}
    out.update(PROGRAM_DURABLE_STOP_KINDS)
    return out


def raise_no_progress_v1(
    *,
    label: str,
    stop_kinds: Sequence[str],
    ctx: Mapping[str, Any],
    mode: str,
) -> None:
    raise ProgramRunStallError(
        f"{label}: {mode} made no public progress before durable stop kinds "
        f"{sorted(set(str(x) for x in stop_kinds))!r}; "
        f"kind={str(ctx.get('kind') or '')!r}; "
        f"cursor={mapping_from_any_v1(ctx.get('cursor'))!r}; "
        f"datum_widgets_on_this_span={list(ctx.get('datum_widgets_on_this_span') or [])!r}; "
        f"last_error={ctx.get('last_error')!r}"
    )


def raise_budget_exhausted_v1(
    *,
    label: str,
    max_steps: int,
    stop_kinds: Sequence[str],
    ctx: Mapping[str, Any],
) -> None:
    raise ProgramRunStallError(
        f"{label}: max_steps={max_steps} exhausted before durable stop kinds "
        f"{sorted(set(str(x) for x in stop_kinds))!r}; "
        f"last_kind={str(ctx.get('kind') or '')!r}; "
        f"cursor={mapping_from_any_v1(ctx.get('cursor'))!r}; "
        f"datum_widgets_on_this_span={list(ctx.get('datum_widgets_on_this_span') or [])!r}; "
        f"last_error={ctx.get('last_error')!r}"
    )


__all__ = [
    "PROGRAM_AUTO_ADVANCE_KINDS_V1",
    "PROGRAM_DEFAULT_MAX_STEPS_V1",
    "PROGRAM_DEFAULT_MAX_STEP_UNTIL_STOP_STEPS_V1",
    "PROGRAM_DURABLE_STOP_KINDS",
    "PROGRAM_ROLLOUT_BUDGET_FLOOR_V1",
    "PROGRAM_ROLLOUT_BUDGET_PER_PROGRAM_STEP_V1",
    "PROGRAM_ROLLOUT_MAX_EXPLICIT_STEPS_V1",
    "PROGRAM_UNDO_DURABLE_STOP_KINDS_V1",
    "derived_program_budget_from_api_v1",
    "derived_program_budget_v1",
    "durable_stop_kinds_from_action_v1",
    "program_len_from_api_snapshot_v1",
    "raise_budget_exhausted_v1",
    "raise_no_progress_v1",
    "program_progress_signature_v1",
    "program_response_signature_v1",
]