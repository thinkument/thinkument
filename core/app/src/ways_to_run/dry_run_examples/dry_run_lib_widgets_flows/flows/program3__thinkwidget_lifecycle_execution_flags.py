from __future__ import annotations

"""
P3 — thinkwidgetTM lifecycle/system execution flags.

The three rows isolate flag behavior:

1. Wc has a high cap and remains a normal non-authoritative reexploder.
2. Wa has enough reexplosions to run its intended lifecycle.
3. A second Wc appearance has max_reexplosions=1 and
   exhausted_means_satisfied=True, proving forced satisfaction at exhaustion.

The sheet asserts public effects, not private lifecycle-store layout.
"""

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import (
    STEP,
    base_widgets,
    message_event,
    program,
    trident,
)


WIDGETS = base_widgets()

PROGRAM = program(
    program_id="dry_run_lib_widgets_flows_p3",
    title="Basic expose P3 — lifecycle flags",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "bounded_board_with_gate",
            "title": "High-cap board with an authoritative gate",
            "widgets": ["board", "daily"],
            "authoritative": [False, True],
            "overrides": {
                "lifecycle": {
                    "board": {
                        "max_reexplosions": 20,
                        "max_messages": 4,
                        "exhausted_means_satisfied": False,
                    }
                }
            },
        },
        {
            "id": "ordinary_game",
            "title": "Ordinary bounded game",
            "widgets": ["guess"],
            "authoritative": [True],
            "overrides": {
                "lifecycle": {
                    "guess": {
                        "max_reexplosions": 8,
                        "max_messages": 6,
                        "max_proc_notes": 2,
                    }
                }
            },
        },
        {
            "id": "forced_board",
            "title": "Exhaustion forces satisfaction",
            "widgets": ["board"],
            "authoritative": [True],
            "overrides": {
                "lifecycle": {
                    "board": {
                        "max_reexplosions": 1,
                        "max_messages": 2,
                        "max_proc_notes": 0,
                        "exhausted_means_satisfied": True,
                    }
                },
                "args": {
                    "board": {
                        "sum_should_not_exceed": 100,
                    }
                },
            },
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
        note="Mount high-cap Wc and the authoritative Wb gate.",
    ),
    STEP(
        fill={
            "board": {"new_1": 1, "new_2": 3, "new_3": 5},
        },
        expect=trident(
            message_event("board", level="info", contains="cumulative"),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="Wc reexplodes without progressing because Wb is still open.",
    ),
    STEP(
        fill={
            "daily": {
                "representative_number": 7,
                "good_day": True,
            }
        },
        expect=trident(
            message_event("daily", level="success", contains="believe"),
            message_event("guess", level="info", contains="started"),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="Gate completion advances and mounts Wa.",
    ),
    STEP(
        fill={
            "guess": {
                "guess_1_1": 1,
                "guess_1_2": 2,
                "guess_1_3": 3,
            }
        },
        expect=trident(
            message_event("guess", level="info", contains="closest"),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="Wa consumes one reexplosion from its generous cap.",
    ),
    STEP(
        fill={
            "guess": {
                "guess_2_1": 17,
                "guess_2_2": 18,
            }
        },
        expect=trident(
            message_event("guess", level="success", contains="correct"),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note="Wa finishes and mounts the authoritative forced-exhaustion Wc.",
    ),
    STEP(
        fill={
            "board": {"new_1": 1, "new_2": 3, "new_3": 5},
        },
        expect=trident(
            message_event("board", level="info", contains="cumulative"),
            event_kind="ATCOMPLETION",
            finished=True,
        ),
        note=(
            "Wc requests another reexplosion after its one allowed mount "
            "reexplosion; engine exhaustion policy forces satisfaction."
        ),
    ),
]


__all__ = ["PROGRAM", "PUPPET", "expected_unrolling"]
