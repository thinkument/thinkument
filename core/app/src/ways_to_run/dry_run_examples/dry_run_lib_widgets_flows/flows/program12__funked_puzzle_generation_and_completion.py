from __future__ import annotations

"""P12 — generated puzzle flows across widgets, roles, and human barriers.

This module is declarative. It owns program graphs and session metadata only.
Execution expectations live in ``dry_run_cases_funked.py`` so adding a new
scenario does not require editing the runner.

Formal collaboration unit:

    generated segment -> zero or more human barriers -> generated segment
"""

from copy import deepcopy
from typing import Any, Dict, Mapping

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.funks.funked_fillers import (
    PUZZLE_GENERATOR_FUNK_V1,
    PUZZLE_SOLVER_FUNK_V1,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.widgets.funked_fill_widgets import (
    PUZZLE_ANSWER_WIDGET,
    PUZZLE_CHECKPOINT_WIDGET,
    PUZZLE_GENERATOR_WIDGET,
)

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import program


def _answer_widget(
    *,
    role: str,
    source: str | None = None,
) -> Dict[str, Any]:
    wires: Dict[str, Any] = {}
    if source is not None:
        wires["puzzle_source"] = {
            "from": source,
            "history": {
                "select": "latest",
                "required": True,
                "max_results": 20,
            },
        }

    return {
        "widget": PUZZLE_ANSWER_WIDGET,
        "title": "Solve the puzzle",
        "args": {},
        "lifecycle": {
            "max_reexplosions": 12,
            "max_messages": 12,
            "max_proc_notes": 0,
        },
        "wires": wires,
        "roles": [role],
        "tags": ["p12", "puzzle", "answer"],
        "system_flags": {"guide_surface": "P12"},
        "authoritative": True,
    }


def _generator_widget(*, role: str) -> Dict[str, Any]:
    return {
        "widget": PUZZLE_GENERATOR_WIDGET,
        "title": "Generate puzzle",
        "args": {},
        "lifecycle": {
            "max_reexplosions": 8,
            "max_messages": 8,
            "max_proc_notes": 0,
        },
        "wires": {},
        "roles": [role],
        "tags": ["p12", "puzzle", "generator"],
        "system_flags": {"guide_surface": "P12"},
        "authoritative": True,
    }


def _checkpoint_widget(
    *,
    role: str,
    label: str,
) -> Dict[str, Any]:
    return {
        "widget": PUZZLE_CHECKPOINT_WIDGET,
        "title": str(label),
        "args": {
            "checkpoint_label": str(label),
        },
        "lifecycle": {
            "max_reexplosions": 8,
            "max_messages": 8,
            "max_proc_notes": 0,
        },
        "wires": {},
        "roles": [role],
        "tags": ["p12", "human-barrier"],
        "system_flags": {"guide_surface": "P12"},
        "authoritative": True,
    }


def _metadata(
    *,
    role_configs: Mapping[str, Mapping[str, Any] | None],
    roles_ordered: list[str],
) -> Dict[str, Any]:
    roles: Dict[str, Any] = {}

    for role_index, role in enumerate(roles_ordered):
        role_config = role_configs.get(role)

        roles[role] = {
            "label": role.replace("_", " ").title(),
            "read_roles": list(roles_ordered[:role_index]),
            "chainreactionTM_config": (
                deepcopy(dict(role_config))
                if role_config is not None
                else None
            ),
        }

    return {
        "roles": roles,
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                role: "redacted"
                for role in roles_ordered
            },
        },
        "chainreactionTM_config": {
            "version": "chainreaction1.0",
            "roles_ordered": list(roles_ordered),
            "expect_all_roles_chainreactioned": False,
            "on_semantic_error": "retry_w_error_awareness",
            "max_semantic_errors_in_a_row": 2,
            "max_fills_on_a_span": 8,
            "max_fills_e2e": 32,
            "history_tail_cap": 4,
            "history_size_cap": 25_000,
            "events_queue_length": 4,
        },
    }


def _solver_config(*, wrong_first: bool) -> Dict[str, Any]:
    return {
        "version": PUZZLE_SOLVER_FUNK_V1,
        "args": {
            "wrong_first": bool(wrong_first),
            "wrong_answer": "__wrong__",
        },
    }


GENERATOR_CONFIG = {
    "version": PUZZLE_GENERATOR_FUNK_V1,
    "args": {
        "puzzle_text": "What is 6 × 7?",
        "answer_key": 42,
    },
}


PROGRAM_START_TO_FINISH = program(
    program_id="dry_run_lib_widgets_flows_p12_start_to_finish",
    title="P12 — funk start to finish",
    symbols={},
    puppeteering={},
    widgets={
        "answer": _answer_widget(role="solver"),
    },
    flow=[
        {
            "id": "answer",
            "title": "Generated solver completes one widget",
            "widgets": ["answer"],
            "authoritative": [True],
        }
    ],
)

SESSION_METADATA_START_TO_FINISH = _metadata(
    role_configs={
        "solver": _solver_config(wrong_first=False),
    },
    roles_ordered=["solver"],
)


PROGRAM_ONE_WIDGET_RETRY = program(
    program_id="dry_run_lib_widgets_flows_p12_one_widget_retry",
    title="P12 — one widget semantic convergence",
    symbols={},
    puppeteering={},
    widgets={
        "answer": _answer_widget(role="solver"),
    },
    flow=[
        {
            "id": "answer",
            "title": "Wrong generated answer converges to the right answer",
            "widgets": ["answer"],
            "authoritative": [True],
        }
    ],
)

SESSION_METADATA_ONE_WIDGET_RETRY = _metadata(
    role_configs={
        "solver": _solver_config(wrong_first=True),
    },
    roles_ordered=["solver"],
)


PROGRAM_MANY_WIDGETS_MANY_ROLES = program(
    program_id="dry_run_lib_widgets_flows_p12_many_widgets_many_roles",
    title="P12 — generated puzzle plus many role-specific solvers",
    symbols={},
    puppeteering={},
    widgets={
        "generator": _generator_widget(role="generator"),
        "answer_a": _answer_widget(
            role="solver_a",
            source="generator",
        ),
        "answer_b": _answer_widget(
            role="solver_b",
            source="generator",
        ),
    },
    flow=[
        {
            "id": "generator",
            "title": "Generate the puzzle",
            "widgets": ["generator"],
            "authoritative": [True],
        },
        {
            "id": "answer_a",
            "title": "First role solves with semantic convergence",
            "widgets": ["answer_a"],
            "authoritative": [True],
        },
        {
            "id": "answer_b",
            "title": "Second role solves with semantic convergence",
            "widgets": ["answer_b"],
            "authoritative": [True],
        },
    ],
)

SESSION_METADATA_MANY_WIDGETS_MANY_ROLES = _metadata(
    role_configs={
        "generator": GENERATOR_CONFIG,
        "solver_a": _solver_config(wrong_first=True),
        "solver_b": _solver_config(wrong_first=True),
    },
    roles_ordered=[
        "generator",
        "solver_a",
        "solver_b",
    ],
)


PROGRAM_FUNKED_AND_HUMAN_COLLABORATION = program(
    program_id="dry_run_lib_widgets_flows_p12_funked_human_collaboration",
    title="P12 — generated and human roles collaborate",
    symbols={},
    puppeteering={},
    widgets={
        "generator": _generator_widget(role="generator"),
        "checkpoint": _checkpoint_widget(
            role="human_reviewer",
            label="Human reviewer checkpoint",
        ),
        "answer": _answer_widget(
            role="solver",
            source="generator",
        ),
    },
    flow=[
        {
            "id": "generator",
            "title": "Generated role authors the puzzle",
            "widgets": ["generator"],
            "authoritative": [True],
        },
        {
            "id": "checkpoint",
            "title": "Human role admits continuation",
            "widgets": ["checkpoint"],
            "authoritative": [True],
        },
        {
            "id": "answer",
            "title": "Generated role resumes and solves",
            "widgets": ["answer"],
            "authoritative": [True],
        },
    ],
)

SESSION_METADATA_FUNKED_AND_HUMAN_COLLABORATION = _metadata(
    role_configs={
        "generator": GENERATOR_CONFIG,
        "human_reviewer": None,
        "solver": _solver_config(wrong_first=False),
    },
    roles_ordered=[
        "generator",
        "human_reviewer",
        "solver",
    ],
)


PROGRAM_MULTI_HUMAN_MULTI_FUNKED_COLLABORATION = program(
    program_id=(
        "dry_run_lib_widgets_flows_p12_multi_human_multi_funked_collaboration"
    ),
    title="P12 — multiple human and generated roles collaborate",
    symbols={},
    puppeteering={},
    widgets={
        "generator": _generator_widget(role="generator"),
        "checkpoint_a": _checkpoint_widget(
            role="human_reviewer_a",
            label="First human review",
        ),
        "answer_a": _answer_widget(
            role="solver_a",
            source="generator",
        ),
        "checkpoint_b": _checkpoint_widget(
            role="human_reviewer_b",
            label="Second human review",
        ),
        "answer_b": _answer_widget(
            role="solver_b",
            source="generator",
        ),
    },
    flow=[
        {
            "id": "generator",
            "title": "Generated role authors the shared puzzle",
            "widgets": ["generator"],
            "authoritative": [True],
        },
        {
            "id": "checkpoint_a",
            "title": "First human admits the first solver",
            "widgets": ["checkpoint_a"],
            "authoritative": [True],
        },
        {
            "id": "answer_a",
            "title": "First generated solver converges",
            "widgets": ["answer_a"],
            "authoritative": [True],
        },
        {
            "id": "checkpoint_b",
            "title": "Second human admits the second solver",
            "widgets": ["checkpoint_b"],
            "authoritative": [True],
        },
        {
            "id": "answer_b",
            "title": "Second generated solver converges and completes",
            "widgets": ["answer_b"],
            "authoritative": [True],
        },
    ],
)

SESSION_METADATA_MULTI_HUMAN_MULTI_FUNKED_COLLABORATION = _metadata(
    role_configs={
        "generator": GENERATOR_CONFIG,
        "human_reviewer_a": None,
        "solver_a": _solver_config(wrong_first=True),
        "human_reviewer_b": None,
        "solver_b": _solver_config(wrong_first=True),
    },
    roles_ordered=[
        "generator",
        "human_reviewer_a",
        "solver_a",
        "human_reviewer_b",
        "solver_b",
    ],
)


PROGRAM12_SCENARIOS = {
    "start_to_finish": {
        "program": PROGRAM_START_TO_FINISH,
        "session_metadata": SESSION_METADATA_START_TO_FINISH,
    },
    "one_widget_retry": {
        "program": PROGRAM_ONE_WIDGET_RETRY,
        "session_metadata": SESSION_METADATA_ONE_WIDGET_RETRY,
    },
    "many_widgets_many_roles": {
        "program": PROGRAM_MANY_WIDGETS_MANY_ROLES,
        "session_metadata": SESSION_METADATA_MANY_WIDGETS_MANY_ROLES,
    },
    "funked_and_human_collaboration": {
        "program": PROGRAM_FUNKED_AND_HUMAN_COLLABORATION,
        "session_metadata": SESSION_METADATA_FUNKED_AND_HUMAN_COLLABORATION,
    },
    "multi_human_multi_funked_collaboration": {
        "program": PROGRAM_MULTI_HUMAN_MULTI_FUNKED_COLLABORATION,
        "session_metadata": (
            SESSION_METADATA_MULTI_HUMAN_MULTI_FUNKED_COLLABORATION
        ),
    },
}


PUPPET = None


__all__ = [
    "PROGRAM12_SCENARIOS",
    "PROGRAM_FUNKED_AND_HUMAN_COLLABORATION",
    "PROGRAM_MANY_WIDGETS_MANY_ROLES",
    "PROGRAM_MULTI_HUMAN_MULTI_FUNKED_COLLABORATION",
    "PROGRAM_ONE_WIDGET_RETRY",
    "PROGRAM_START_TO_FINISH",
    "PUPPET",
    "SESSION_METADATA_FUNKED_AND_HUMAN_COLLABORATION",
    "SESSION_METADATA_MANY_WIDGETS_MANY_ROLES",
    "SESSION_METADATA_MULTI_HUMAN_MULTI_FUNKED_COLLABORATION",
    "SESSION_METADATA_ONE_WIDGET_RETRY",
    "SESSION_METADATA_START_TO_FINISH",
]