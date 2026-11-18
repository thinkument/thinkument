from __future__ import annotations

"""Copy/paste template: complete role + chainreactionTM session metadata.

Use this as the role surface when chainreactionTM is enabled, because every
session role must explicitly include chainreactionTM_config (a filler config or
None for a deliberate human barrier).
"""

from typing import Any, Dict


FUNK_VERSION: str = "my_app.funk.semantic_filler.v1"  # registered before launch

ROLE_GENERATOR: str = "generator"
ROLE_HUMAN_REVIEWER: str = "human_reviewer"
ROLE_SOLVER: str = "solver"


SESSION_METADATA_FUNKED: Dict[str, Any] = {
    "roles": {
        ROLE_GENERATOR: {
            "label": "Generator",
            "read_roles": [],
            "chainreactionTM_config": {
                "version": FUNK_VERSION,
                "args": {
                    "default_text": "Generated value",
                    "max_datums_per_iteration": 8,
                },
            },
        },
        ROLE_HUMAN_REVIEWER: {
            "label": "Human Reviewer",
            "read_roles": [ROLE_GENERATOR],
            # None is an intentional manual synchronization barrier.
            "chainreactionTM_config": None,
        },
        ROLE_SOLVER: {
            "label": "Solver",
            "read_roles": [ROLE_GENERATOR, ROLE_HUMAN_REVIEWER],
            "chainreactionTM_config": {
                "version": FUNK_VERSION,
                "args": {
                    "default_text": "Generated value",
                    "max_datums_per_iteration": 8,
                },
            },
        },
    },
    "role_mismatch_policy": {
        "default": "redacted",
        "role_modes": {
            ROLE_GENERATOR: "redacted",
            ROLE_HUMAN_REVIEWER: "redacted",
            ROLE_SOLVER: "redacted",
        },
    },
    "chainreactionTM_config": {
        "version": "chainreaction1.0",
        # Must flatten to every session role exactly once.
        "roles_ordered": [
            ROLE_GENERATOR,
            ROLE_HUMAN_REVIEWER,
            ROLE_SOLVER,
        ],
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


__all__ = [
    "FUNK_VERSION",
    "ROLE_GENERATOR",
    "ROLE_HUMAN_REVIEWER",
    "ROLE_SOLVER",
    "SESSION_METADATA_FUNKED",
]
