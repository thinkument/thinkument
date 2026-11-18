from __future__ import annotations

"""Static/runtime contract helpers for one-shot fully-funked black-box runs."""

from copy import deepcopy
from typing import Any, Dict, Mapping, Sequence


BLACK_BOX_CONTRACT_KIND_V1 = "funked_black_box_contract_v1"
BLACK_BOX_RESULT_KIND_V1 = "funked_black_box_run_result_v1"
BLACK_BOX_ERROR_REPORT_KIND_V1 = "funked_black_box_run_error_report_v1"


class FunkedBlackBoxContractError(ValueError):
    """The resolved P/SM pair cannot represent a fully-funked run."""

    def __init__(self, message: str, *, report: Mapping[str, Any]) -> None:
        self.report = deepcopy(dict(report))
        super().__init__(str(message))


class FunkedBlackBoxRunIncompleteError(RuntimeError):
    """A valid fully-funked contract failed to reach ATCOMPLETION."""

    def __init__(self, message: str, *, report: Mapping[str, Any]) -> None:
        self.report = deepcopy(dict(report))
        super().__init__(str(message))


def _roles_from_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (bytes, bytearray, str),
    ):
        values = list(value)
    else:
        values = [value]

    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        role = str(raw or "").strip()
        if role and role not in seen:
            seen.add(role)
            out.append(role)
    return out


def _stable_unique_text(values: Sequence[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def think_program_role_names_v1(program: Mapping[str, Any]) -> list[str]:
    """Return every role name authored on the resolved ThinkProgram surface.

    Current public programs put role declarations on logical widgets. The
    step/override scans are intentionally included as a compatibility seam for
    step-local role declarations so black-box validation cannot become weaker
    merely because authoring grammar moves an existing role declaration from a
    logical widget to one appearance.
    """
    if not isinstance(program, Mapping):
        raise TypeError("program must be a mapping")

    run = program.get("run")
    run = run if isinstance(run, Mapping) else {}
    p = run.get("program")
    p = p if isinstance(p, Mapping) else {}

    roles: set[str] = set()
    widgets = p.get("widgets")
    widgets = widgets if isinstance(widgets, Mapping) else {}
    for raw_widget in widgets.values():
        if not isinstance(raw_widget, Mapping):
            continue
        roles.update(_roles_from_value(raw_widget.get("roles")))
        roles.update(_roles_from_value(raw_widget.get("role")))

    flow = p.get("flow")
    flow = flow if isinstance(flow, list) else []
    for raw_step in flow:
        if not isinstance(raw_step, Mapping):
            continue
        roles.update(_roles_from_value(raw_step.get("roles")))
        roles.update(_roles_from_value(raw_step.get("role")))

        overrides = raw_step.get("overrides")
        overrides = overrides if isinstance(overrides, Mapping) else {}
        for key in ("roles", "role"):
            raw_role_overrides = overrides.get(key)
            if isinstance(raw_role_overrides, Mapping):
                for value in raw_role_overrides.values():
                    roles.update(_roles_from_value(value))
            elif raw_role_overrides is not None:
                roles.update(_roles_from_value(raw_role_overrides))

    return sorted(roles)


def validate_funked_black_box_contract_v1(
    *,
    program: Mapping[str, Any],
    resolved_session_metadata: Mapping[str, Any],
    normalized_chainreaction_config: Any,
) -> Dict[str, Any]:
    """Assert the static resolved P/SM role contract for a black-box run.

    This validation is intentionally stronger than an ordinary funked manual
    run: every role used by P must exist in SM, occur in the effective role
    schedule, and have a non-null normalized filler configuration. Runtime
    completion is still checked separately because a role-complete static
    contract cannot prove that every filler will make semantic progress.
    """
    program_roles = think_program_role_names_v1(program)
    metadata_roles_raw = resolved_session_metadata.get("roles")
    metadata_roles = (
        dict(metadata_roles_raw)
        if isinstance(metadata_roles_raw, Mapping)
        else {}
    )
    metadata_role_names = sorted(str(key) for key in metadata_roles)

    config = normalized_chainreaction_config
    enabled = bool(getattr(config, "enabled", False))
    scheduled_roles_ordered = _stable_unique_text(
        list(getattr(config, "flat_roles_ordered", ()) or ())
    )
    scheduled_roles = set(scheduled_roles_ordered)
    role_configs = getattr(config, "role_configs", None)
    role_configs = role_configs if isinstance(role_configs, Mapping) else {}

    missing_from_sm = sorted(
        role for role in program_roles if role not in metadata_roles
    )
    missing_from_schedule = sorted(
        role for role in program_roles if role not in scheduled_roles
    )
    unfunkable_roles = sorted(
        role for role in program_roles if role_configs.get(role) is None
    )

    extra_sm_roles = sorted(
        role for role in metadata_role_names if role not in set(program_roles)
    )
    extra_scheduled_roles = [
        role for role in scheduled_roles_ordered if role not in set(program_roles)
    ]

    report = {
        "kind": BLACK_BOX_CONTRACT_KIND_V1,
        "ok": bool(
            enabled
            and not missing_from_sm
            and not missing_from_schedule
            and not unfunkable_roles
        ),
        "chainreaction_enabled": enabled,
        "program_roles": program_roles,
        "session_metadata_roles": metadata_role_names,
        "scheduled_roles": scheduled_roles_ordered,
        "missing_program_roles_from_session_metadata": missing_from_sm,
        "missing_program_roles_from_chainreaction_schedule": (
            missing_from_schedule
        ),
        "unfunkable_program_roles": unfunkable_roles,
        "extra_session_metadata_roles": extra_sm_roles,
        "extra_scheduled_roles": extra_scheduled_roles,
    }

    if not enabled:
        raise FunkedBlackBoxContractError(
            "funked black-box run requires enabled chainreactionTM config",
            report=report,
        )
    if missing_from_sm:
        raise FunkedBlackBoxContractError(
            "every role used by P must exist in resolved SM.roles; missing "
            f"{missing_from_sm}",
            report=report,
        )
    if missing_from_schedule:
        raise FunkedBlackBoxContractError(
            "every role used by P must appear in the resolved chainreactionTM "
            f"role schedule; missing {missing_from_schedule}",
            report=report,
        )
    if unfunkable_roles:
        raise FunkedBlackBoxContractError(
            "every role used by P must have a funk filler configuration in SM; "
            f"unfunkable roles {unfunkable_roles}",
            report=report,
        )

    return report


__all__ = [
    "BLACK_BOX_CONTRACT_KIND_V1",
    "BLACK_BOX_ERROR_REPORT_KIND_V1",
    "BLACK_BOX_RESULT_KIND_V1",
    "FunkedBlackBoxContractError",
    "FunkedBlackBoxRunIncompleteError",
    "think_program_role_names_v1",
    "validate_funked_black_box_contract_v1",
]
