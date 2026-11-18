from __future__ import annotations

"""Declarative funked executable-case catalog.

The catalog owns only app-specific P/SM plus standard A/E-style expectations.
The generic funked runner owns run creation, chain dispatch, committed polling,
queue validation, filler-receipt matching, and generated-end invariants.
"""

from typing import Any, Mapping, Optional, Sequence

from ways_to_run.dry_run_examples.dry_run_standard_lingo.funked_live_session_dry_run_v1 import (
    FunkedDispatchExpectationV1,
    FunkedDryRunCaseV1,
)

from .flows.program12__funked_puzzle_generation_and_completion import (
    PROGRAM12_SCENARIOS,
)


SOLVER_RECEIPT_KIND = "program12_puzzle_solver_receipt_v1"


def _scenario(name: str) -> Mapping[str, Any]:
    return PROGRAM12_SCENARIOS[name]


def _A(
    *,
    role: Optional[str] = None,
    user_fill: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "action": "STEP",
        "role": role,
        "user_fill": {} if user_fill is None else dict(user_fill),
        "user_signal": None,
        "my_current_event_seq_number": None,
    }
    return out


def _packet(
    *,
    event_kind: str,
    roles_used: Sequence[str],
    generated_dispatches_e2e: int,
    stopped_reason: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "event_kind": str(event_kind),
        "chainreactionTM_receipt.roles_used": list(roles_used),
        "chainreactionTM_receipt.generated_dispatches_e2e": int(
            generated_dispatches_e2e
        ),
        "chainreactionTM_receipt.stopped_reason": str(stopped_reason),
    }
    if event_kind == "ATCOMPLETION":
        out["finished"] = True
    return out


def _solver_receipt(*, retrying: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "kind": SOLVER_RECEIPT_KIND,
        "retrying_after_semantic_error": bool(retrying),
    }
    if retrying:
        out["had_last_error"] = True
        out["semantic_errors_in_row_seen"] = 1
    return out


def _generated_end(*, will_funk: bool, reason: str) -> dict[str, Any]:
    prefix = (
        "payload.dispatch_context.filler_receipt."
        "next_U_funkability"
    )
    return {
        f"{prefix}.will_funk_next_dispatch": bool(will_funk),
        f"{prefix}.reason": str(reason),
    }


def _dispatch(
    *,
    event_kind: str,
    roles_used: Sequence[str],
    generated_dispatches_e2e: int,
    stopped_reason: str,
    role: Optional[str] = None,
    user_fill: Optional[Mapping[str, Any]] = None,
    solver_retries: Sequence[bool] = (),
    generated_next: Sequence[tuple[bool, str]] = (),
    note: str = "",
) -> FunkedDispatchExpectationV1:
    return FunkedDispatchExpectationV1(
        A=_A(role=role, user_fill=user_fill),
        packet_expectation=_packet(
            event_kind=event_kind,
            roles_used=roles_used,
            generated_dispatches_e2e=generated_dispatches_e2e,
            stopped_reason=stopped_reason,
        ),
        filler_receipt_expectations=tuple(
            _solver_receipt(retrying=retrying)
            for retrying in solver_retries
        ),
        generated_end_expectations=tuple(
            _generated_end(will_funk=will_funk, reason=reason)
            for will_funk, reason in generated_next
        ),
        note=note,
    )


FUNKED_DRY_RUN_CASES = (
    FunkedDryRunCaseV1(
        name="dry_run_lib_widgets_flows.P12.start_to_finish",
        program=_scenario("start_to_finish")["program"],
        session_metadata=_scenario("start_to_finish")["session_metadata"],
        dispatches=(
            _dispatch(
                event_kind="ATCOMPLETION",
                roles_used=("solver",),
                generated_dispatches_e2e=1,
                stopped_reason="program_complete_or_not_manual",
                solver_retries=(False,),
                generated_next=((False, "program_complete_or_not_manual"),),
                note="One generated solver completes the run.",
            ),
        ),
    ),
    FunkedDryRunCaseV1(
        name="dry_run_lib_widgets_flows.P12.one_widget_retry",
        program=_scenario("one_widget_retry")["program"],
        session_metadata=_scenario("one_widget_retry")["session_metadata"],
        dispatches=(
            _dispatch(
                event_kind="ATCOMPLETION",
                roles_used=("solver", "solver"),
                generated_dispatches_e2e=2,
                stopped_reason="program_complete_or_not_manual",
                solver_retries=(False, True),
                generated_next=(
                    (True, "next_dispatch_funkable"),
                    (False, "program_complete_or_not_manual"),
                ),
                note="Semantic rejection converges through one generated retry.",
            ),
        ),
    ),
    FunkedDryRunCaseV1(
        name="dry_run_lib_widgets_flows.P12.many_widgets_many_roles",
        program=_scenario("many_widgets_many_roles")["program"],
        session_metadata=_scenario("many_widgets_many_roles")["session_metadata"],
        dispatches=(
            _dispatch(
                event_kind="ATCOMPLETION",
                roles_used=(
                    "generator",
                    "solver_a",
                    "solver_a",
                    "solver_b",
                    "solver_b",
                ),
                generated_dispatches_e2e=5,
                stopped_reason="program_complete_or_not_manual",
                solver_retries=(False, True, False, True),
                generated_next=(
                    (True, "next_dispatch_funkable"),
                    (True, "next_dispatch_funkable"),
                    (True, "next_dispatch_funkable"),
                    (True, "next_dispatch_funkable"),
                    (False, "program_complete_or_not_manual"),
                ),
                note="Generator plus two role-specific solvers complete E2E.",
            ),
        ),
    ),
    FunkedDryRunCaseV1(
        name="dry_run_lib_widgets_flows.P12.funked_and_human_collaboration",
        program=_scenario("funked_and_human_collaboration")["program"],
        session_metadata=_scenario("funked_and_human_collaboration")[
            "session_metadata"
        ],
        dispatches=(
            _dispatch(
                event_kind="MANUALFILLNEEDEDSTEP",
                roles_used=("generator",),
                generated_dispatches_e2e=1,
                stopped_reason="next_pending_role_unchainreactioned",
                generated_next=(
                    (False, "next_pending_role_unchainreactioned"),
                ),
                note="Generated segment stops at the human barrier.",
            ),
            _dispatch(
                role="human_reviewer",
                user_fill={"checkpoint.approval": "approve"},
                event_kind="ATCOMPLETION",
                roles_used=("solver",),
                generated_dispatches_e2e=1,
                stopped_reason="program_complete_or_not_manual",
                solver_retries=(False,),
                generated_next=((False, "program_complete_or_not_manual"),),
                note="Human approval resumes generated completion.",
            ),
        ),
    ),
    FunkedDryRunCaseV1(
        name=(
            "dry_run_lib_widgets_flows.P12."
            "multi_human_multi_funked_collaboration"
        ),
        program=_scenario("multi_human_multi_funked_collaboration")["program"],
        session_metadata=_scenario("multi_human_multi_funked_collaboration")[
            "session_metadata"
        ],
        dispatches=(
            _dispatch(
                event_kind="MANUALFILLNEEDEDSTEP",
                roles_used=("generator",),
                generated_dispatches_e2e=1,
                stopped_reason="next_pending_role_unchainreactioned",
                generated_next=(
                    (False, "next_pending_role_unchainreactioned"),
                ),
                note="Initial generated segment stops at reviewer A.",
            ),
            _dispatch(
                role="human_reviewer_a",
                user_fill={"checkpoint_a.approval": "approve"},
                event_kind="MANUALFILLNEEDEDSTEP",
                roles_used=("solver_a", "solver_a"),
                generated_dispatches_e2e=2,
                stopped_reason="next_pending_role_unchainreactioned",
                solver_retries=(False, True),
                generated_next=(
                    (True, "next_dispatch_funkable"),
                    (False, "next_pending_role_unchainreactioned"),
                ),
                note="Reviewer A admits solver A, then reviewer B blocks.",
            ),
            _dispatch(
                role="human_reviewer_b",
                user_fill={"checkpoint_b.approval": "approve"},
                event_kind="ATCOMPLETION",
                roles_used=("solver_b", "solver_b"),
                generated_dispatches_e2e=2,
                stopped_reason="program_complete_or_not_manual",
                solver_retries=(False, True),
                generated_next=(
                    (True, "next_dispatch_funkable"),
                    (False, "program_complete_or_not_manual"),
                ),
                note="Reviewer B admits solver B and the program completes.",
            ),
        ),
    ),
)

FUNKED_DRY_RUN_CASES_BY_NAME = {case.name: case for case in FUNKED_DRY_RUN_CASES}

assert len(FUNKED_DRY_RUN_CASES_BY_NAME) == len(FUNKED_DRY_RUN_CASES)
assert set(PROGRAM12_SCENARIOS) == {
    case.name.rsplit(".", 1)[-1] for case in FUNKED_DRY_RUN_CASES
}


__all__ = [
    "FUNKED_DRY_RUN_CASES",
    "FUNKED_DRY_RUN_CASES_BY_NAME",
]
