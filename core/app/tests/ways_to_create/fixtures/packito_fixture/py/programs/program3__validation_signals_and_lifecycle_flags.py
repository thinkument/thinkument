from __future__ import annotations

"""P3 — platform semantic validation, lifecycle validation, signals, caps."""

from ._shared import base_sm, board_widget, choice_widget, lifecycle, program


WIDGETS = {
    "validated": choice_widget(
        title="Two validation layers",
        prompt="Only alpha/beta pass platform validation",
    ),
    "forced_board": board_widget(
        title="One-reexplosion forced-satisfaction board",
        authoritative=True,
    ),
}

PROGRAM = program(
    program_id="packito_p3_validation_flags",
    title="Packito P3 — validation, signals, and lifecycle flags",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "validation",
            "title": "Platform wall then domain rule",
            "widgets": ["validated"],
            "authoritative": [True],
            "overrides": {
                "args": {
                    "validated": {"required_note_prefix": "DOMAIN:"},
                }
            },
        },
        {
            "id": "forced_exhaustion",
            "title": "Lifecycle exhaustion can satisfy by policy",
            "widgets": ["forced_board"],
            "authoritative": [True],
            "overrides": {
                "lifecycle": {
                    "forced_board": lifecycle(
                        max_reexplosions=1,
                        max_messages=8,
                        exhausted_means_satisfied=True,
                    )
                }
            },
        },
    ],
)

SESSION_METADATA = base_sm(
    app_args={
        "lesson": "semantic-vs-functional-validation-and-flags",
        "show_inspector": True,
    }
)
PUPPET = None

__all__ = ["PROGRAM", "PUPPET", "SESSION_METADATA"]
