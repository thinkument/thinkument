from __future__ import annotations

"""P5 — generated segment -> human barrier -> generated semantic retry."""

from ._shared import (
    base_sm,
    program,
    puzzle_answer_widget,
    puzzle_seed_widget,
    role_gate_widget,
)
from ..funks import PUZZLE_SEED_FUNK_V1, PUZZLE_SOLVER_FUNK_V1


ROLE_GENERATOR = "generator"
ROLE_HUMAN = "human_reviewer"
ROLE_SOLVER = "solver"

PROGRAM = program(
    program_id="packito_p5_funked_collaboration",
    title="Packito P5 — funked + human collaboration",
    symbols={},
    puppeteering={},
    widgets={
        "seed": puzzle_seed_widget(role=ROLE_GENERATOR),
        "review": role_gate_widget(
            title="Human reviewer admits generated continuation",
            role=ROLE_HUMAN,
        ),
        "answer": puzzle_answer_widget(
            role=ROLE_SOLVER,
            source="seed",
        ),
    },
    flow=[
        {
            "id": "seed",
            "title": "Generated role authors a puzzle",
            "widgets": ["seed"],
            "authoritative": [True],
        },
        {
            "id": "human",
            "title": "Manual synchronization barrier",
            "widgets": ["review"],
            "authoritative": [True],
        },
        {
            "id": "answer",
            "title": "Generated solver retries after semantic feedback",
            "widgets": ["answer"],
            "authoritative": [True],
        },
    ],
)

SESSION_METADATA = base_sm(
    app_args={
        "lesson": "funked-human-collaboration",
        "show_inspector": True,
    }
)
SESSION_METADATA.update(
    {
        "roles": {
            ROLE_GENERATOR: {
                "label": "Generator",
                "read_roles": [],
                "chainreactionTM_config": {
                    "version": PUZZLE_SEED_FUNK_V1,
                    "args": {
                        "puzzle_text": "What is 6 x 7?",
                        "answer_key": 42,
                    },
                },
            },
            ROLE_HUMAN: {
                "label": "Human Reviewer",
                "read_roles": [ROLE_GENERATOR],
                "chainreactionTM_config": None,
            },
            ROLE_SOLVER: {
                "label": "Solver",
                "read_roles": [ROLE_GENERATOR, ROLE_HUMAN],
                "chainreactionTM_config": {
                    "version": PUZZLE_SOLVER_FUNK_V1,
                    "args": {
                        "wrong_first": True,
                        "wrong_answer": "__wrong__",
                    },
                },
            },
        },
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                ROLE_GENERATOR: "redacted",
                ROLE_HUMAN: "redacted",
                ROLE_SOLVER: "redacted",
            },
        },
        "chainreactionTM_config": {
            "version": "chainreaction1.0",
            "roles_ordered": [ROLE_GENERATOR, ROLE_HUMAN, ROLE_SOLVER],
            "expect_all_roles_chainreactioned": False,
            "on_semantic_error": "retry_w_error_awareness",
            "max_semantic_errors_in_a_row": 2,
            "max_fills_on_a_span": 8,
            "max_fills_e2e": 16,
            "history_tail_cap": 4,
            "history_size_cap": 25_000,
            "events_queue_length": 8,
        },
    }
)
PUPPET = None

__all__ = [
    "PROGRAM",
    "PUPPET",
    "ROLE_GENERATOR",
    "ROLE_HUMAN",
    "ROLE_SOLVER",
    "SESSION_METADATA",
]
