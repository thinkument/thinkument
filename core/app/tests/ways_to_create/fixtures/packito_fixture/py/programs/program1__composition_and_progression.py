from __future__ import annotations

"""P1 — composition, reexplosion, signals, non-authoritative background work."""

from copy import deepcopy

from ._shared import base_sm, board_widget, choice_widget, program


WIDGETS = {
    "opening": choice_widget(
        title="Opening choice",
        prompt="Choose an opening direction",
    ),
    "board": board_widget(title="Background score board", authoritative=False),
    "closing": choice_widget(
        title="Closing choice",
        prompt="Choose a closing direction",
        wires={
            "source": {
                "from": "opening",
                "history": {
                    "select": "latest",
                    "required": True,
                    "max_results": 20,
                },
            }
        },
    ),
}

# The same widget class can appear as independent logical widgets.  The board is
# non-authoritative on the mixed span, so it may remain open while closing gates
# progression.
PROGRAM = program(
    program_id="packito_p1_composition",
    title="Packito P1 — composition and progression",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "opening",
            "title": "One authoritative widget",
            "widgets": ["opening"],
            "authoritative": [True],
        },
        {
            "id": "mixed",
            "title": "Background widget beside the next gate",
            "widgets": ["board", "closing"],
            "authoritative": [False, True],
            "overrides": {
                "args": {
                    "closing": {"appearance_label": "mixed-step"},
                }
            },
        },
    ],
)

SESSION_METADATA = base_sm(
    app_args={
        "lesson": "composition",
        "show_inspector": True,
    }
)
PUPPET = None

# A second importable object is useful in notebooks/tests that want to mutate a
# copy without ever mutating the canonical teaching program.
PROGRAM_COPY = deepcopy(PROGRAM)

__all__ = ["PROGRAM", "PROGRAM_COPY", "PUPPET", "SESSION_METADATA"]
