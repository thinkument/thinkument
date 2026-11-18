
from __future__ import annotations

"""
P1 — widget play, one primary widget per step, then a mixed step.

The sequence is deliberately human-readable:

    daily
      -> guess wired to daily
      -> cumulative board beside a required daily datum
      -> guess wired to its previous invocation

Wc is non-authoritative in the mixed step, so it can keep reexploding without
blocking progression once the authoritative Wb datum is done.
"""

from copy import deepcopy

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import (
    STEP,
    base_widgets,
    message_event,
    program,
    trident,
)


WIDGETS = base_widgets()

# Use two explicit logical Wa declarations. A widget appearance should not have
# to infer which of two optional histories is semantically intended.
_guess_template = WIDGETS.pop("guess")
WIDGETS["guess_daily"] = deepcopy(_guess_template)
WIDGETS["guess_daily"]["wires"] = {
    "daily_number": {
        "from": "daily",
        "history": {
            "select": "latest",
            "required": False,
            "max_results": 20,
        },
    },
}
WIDGETS["guess_previous"] = deepcopy(_guess_template)
WIDGETS["guess_previous"]["wires"] = {
    "previous_game": {
        "from": "guess_daily",
        "history": {
            "select": "latest",
            "required": True,
            "max_results": 20,
        },
    },
}


PROGRAM = program(
    program_id="dry_run_lib_widgets_flows_p1",
    title="Basic expose P1 — widget play",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "daily",
            "title": "Pick today's number",
            "widgets": ["daily"],
            "authoritative": [True],
        },
        {
            "id": "guess_from_daily",
            "title": "Guess the number supplied by daily",
            "widgets": ["guess_daily"],
            "authoritative": [True],
        },
        {
            "id": "board_and_daily",
            "title": "Use an endless board without blocking the flow",
            "widgets": ["board", "daily"],
            "authoritative": [False, True],
            "overrides": {
                "args": {
                    "daily": {
                        "response_mode": "paragraph",
                        "paragraph_must_contain": "forward",
                    }
                }
            },
        },
        {
            "id": "guess_again",
            "title": "Reuse the previous game",
            "widgets": ["guess_previous"],
            "authoritative": [True],
        },
    ],
)

PUPPET = None

expected_unrolling = [
    STEP(
        expect=trident(
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="Enter the flow; mount daily.",
    ),
    STEP(
        fill={
            "daily": {
                "representative_number": 9,
                "good_day": True,
            }
        },
        expect=trident(
            message_event("daily", level="success", contains="believe"),
            message_event("guess_daily", level="info", contains="started"),
            message_event("guess_daily", level="info", contains="hint"),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="Complete Wb, transition, and mount Wa in the same dispatch.",
    ),
    STEP(
        fill={
            "guess_daily": {
                "guess_1_1": 1,
                "guess_1_2": 5,
                "guess_1_3": 7,
            }
        },
        expect=trident(
            message_event("guess_daily", level="info", contains="closest"),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="First failed Wa round reexplodes to two guesses.",
    ),
    STEP(
        fill={
            "guess_daily": {
                "guess_2_1": 9,
                "guess_2_2": 10,
            }
        },
        expect=trident(
            message_event("guess_daily", level="success", contains="correct"),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="Finish Wa and mount the mixed Wc/Wb step.",
    ),
    STEP(
        fill={
            "board": {"new_1": 1, "new_2": 3, "new_3": 5},
        },
        expect=trident(
            message_event("board", level="info", contains="cumulative total"),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="Exercise non-authoritative infinite reexplosion.",
    ),
    STEP(
        fill={
            "daily": {
                "representative_number": 12,
                "day_reflection": "moving forward with care",
            }
        },
        expect=trident(
            message_event("daily", level="success", contains="believe"),
            message_event("guess_previous", level="info", contains="started"),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="Authoritative Wb completes the mixed span and mounts final Wa.",
    ),
    STEP(
        fill={
            "guess_previous": {
                "guess_1_1": 9,
                "guess_1_2": 2,
                "guess_1_3": 3,
            }
        },
        expect=trident(
            message_event("guess_previous", level="success", contains="correct"),
            event_kind="ATCOMPLETION",
            finished=True,
        ),
        note="Previous-game wire reuses the number and completes P1.",
    ),
]


__all__ = ["PROGRAM", "PUPPET", "expected_unrolling"]
