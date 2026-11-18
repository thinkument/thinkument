from __future__ import annotations

"""
P2 — ThinkProgramTM as an executable authoring language.

This is not merely a flow that happens to contain symbols and overrides. It
emits mount-time public witnesses proving their resolved runtime meaning.

The two dry-run cases use the same authored program:

``merge_onto``
    Launch values shallowly assign over authored puppeteering. Unmentioned
    authored values survive.

``take_over``
    Launch values replace the entire authored puppeteering pocket. Unmentioned
    symbols fall back to their declared defaults.

The program also proves:

* exact whole-value symbol references, including nested mapping/list lookup;
* longest declared dotted-symbol matching;
* base widget definitions versus per-appearance overrides;
* title/tag replacement and deep system-flag merge;
* repeated logical-widget appearances;
* signal-only and fill-plus-signal dispatches;
* a multi-widget span with an explicit authoritative vector;
* cross-widget latest-history wiring;
* UNDO and REDO as ordinary controller envelopes.
"""

from copy import deepcopy

from _thinkprogram.thinkprogramTM.api import (
    PUPPETEERING_OVERLAY_KEY_V1,
    PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
    PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
)

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import (
    REDO,
    STEP,
    UNDO,
    base_widgets,
    message_event,
    program,
    program_authoring_probe_widget,
    trident,
)


WIDGETS = base_widgets()
WIDGETS["probe"] = program_authoring_probe_widget()

WIDGETS["daily"]["args"] = {
    "response_mode": "$daily.mode",
    "min_number_accepted": "$daily.minimum",
    "paragraph_must_contain": "",
    "adjust_min_seed": 13,
}
WIDGETS["guess"]["args"] = {
    "number": "$guess.number",
    "hint": "$guess.hint",
}
WIDGETS["guess"]["wires"] = {
    "daily_number": {
        "from": "daily",
        "history": {
            "select": "latest",
            "required": True,
            "max_results": 20,
        },
    },
}

PROGRAM = program(
    program_id="dry_run_lib_widgets_flows_p2",
    title="Basic expose P2 — ThinkProgramTM authoring language",
    symbols={
        "daily.mode": {
            "value": "checkbox",
            "parametrize": True,
        },
        "daily.minimum": {
            "value": 2,
            "parametrize": True,
        },
        "guess.number": {
            "value": 23,
            "parametrize": True,
        },
        "guess.hint": {
            "value": "The target is an odd number above 20.",
            "parametrize": False,
        },
        "board.max": {
            "value": 50,
            "parametrize": True,
        },
        "probe.label": {
            "value": "default-probe-label",
            "parametrize": True,
        },
        "probe.payload": {
            "value": {
                "env": "default",
                "features": [
                    "symbols",
                    "puppeteering",
                    "overrides",
                ],
            },
            "parametrize": True,
        },
        "probe.choices": {
            "value": [
                "alpha",
                "beta",
            ],
            "parametrize": False,
        },
    },
    puppeteering={
        "daily.mode": "paragraph",
        "daily.minimum": 3,
        "guess.number": 29,
        "board.max": 41,
        "probe.label": "authored-probe-label",
        "probe.payload": {
            "env": "authored",
            "features": [
                "symbols",
                "puppeteering",
                "overrides",
            ],
        },
    },
    widgets=WIDGETS,
    flow=[
        {
            "id": "authoring_proof",
            "title": "Observe resolved authoring surfaces",
            "widgets": ["probe"],
            "authoritative": [True],
            "overrides": {
                "title": {
                    "probe": (
                        "Appearance title replaces the logical-widget title"
                    ),
                },
                "tags": {
                    "probe": [
                        "program",
                        "authoring",
                        "appearance",
                    ],
                },
                "system_flags": {
                    "probe": {
                        "appearance_only": True,
                        "nested": {
                            "replace_me": "appearance",
                        },
                    },
                },
                "lifecycle": {
                    "probe": {
                        "max_messages": 30,
                    },
                },
            },
        },
        {
            "id": "configured_daily",
            "title": "Symbol-bound daily widget",
            "widgets": ["daily"],
            "authoritative": [True],
            "overrides": {
                "title": {
                    "daily": "Configured daily check-in",
                },
                "tags": {
                    "daily": ["p2", "configured"],
                },
                "system_flags": {
                    "daily": {
                        "appearance": "opening",
                    },
                },
            },
        },
        {
            "id": "signal_adjusted_daily",
            "title": "Signal-controlled repeated Wb",
            "widgets": ["daily"],
            "authoritative": [True],
            "overrides": {
                "args": {
                    "daily": {
                        "response_mode": "paragraph",
                        "paragraph_must_contain": "ready",
                    },
                },
                "lifecycle": {
                    "daily": {
                        "max_messages": 30,
                    },
                },
            },
        },
        {
            "id": "wired_guess_and_board",
            "title": "Cross-widget wire plus non-authoritative board",
            "widgets": ["guess", "board"],
            "authoritative": [True, False],
            "overrides": {
                "args": {
                    "board": {
                        "sum_should_not_exceed": "$board.max",
                    },
                },
                "tags": {
                    "guess": ["p2", "history-consumer"],
                    "board": ["p2", "background-board"],
                },
            },
        },
    ],
)


PUPPET = {
    PUPPETEERING_OVERLAY_KEY_V1: {
        "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
        "strict": True,
    },
    "daily.mode": "checkbox",
    "daily.minimum": 4,
    "guess.number": 27,
    "probe.label": "launch-merge-label",
    "probe.payload": {
        "env": "launch-merge",
        "features": [
            "symbols",
            "puppeteering",
            "overrides",
        ],
    },
}

PUPPET_TAKE_OVER = {
    PUPPETEERING_OVERLAY_KEY_V1: {
        "mode": PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
        "strict": True,
    },
    "daily.minimum": 6,
    "probe.label": "launch-take-over-label",
    "probe.payload": {
        "env": "launch-take-over",
        "features": [
            "symbols",
            "puppeteering",
            "overrides",
        ],
    },
}



from typing import Any, Dict
from ways_to_run.dry_run_examples.dry_run_standard_lingo.event_expectations_v1 import datum_event_v1


def program_authoring_proof_event(
    datum_id: str,
    *,
    label: str,
    minimum: int,
    payload_env: str,
) -> Dict[str, Any]:
    return datum_event_v1(
        datum_id,
        name="program_sessions.proof",
        payload_needles={
            "payload.proof.presentation.title": (
                "Appearance title replaces the logical-widget title"
            ),
            "payload.proof.presentation.tags": [
                "program",
                "authoring",
                "appearance",
            ],
            "payload.proof.presentation.system_flags.guide_surface": "Wp",
            "payload.proof.presentation.system_flags.base_only": True,
            "payload.proof.presentation.system_flags.appearance_only": True,
            "payload.proof.presentation.system_flags.nested.base": True,
            (
                "payload.proof.presentation.system_flags.nested.replace_me"
            ): "appearance",
            "payload.proof.args.lesson_label": str(label),
            "payload.proof.args.structured_payload.env": str(payload_env),
            "payload.proof.args.structured_payload.features": [
                "symbols",
                "puppeteering",
                "overrides",
            ],
            "payload.proof.args.first_choice": "alpha",
            "payload.proof.args.effective_minimum": int(minimum),
            (
                "payload.proof.kernel_flags."
                "copy_form_frame_span_args_into_each_datum"
            ): True,
            "payload.proof.kernel_flags.mount_explode_default": True,
            "payload.proof.authoritative": True,
            "payload.proof.past_wire_keys": [],
        },
    )


def _expected_unrolling(
    *,
    proof_label: str,
    proof_minimum: int,
    proof_env: str,
    first_daily_mode: str,
    first_daily_number: int,
) -> list[dict]:
    first_daily_fill = {
        "representative_number": first_daily_number,
    }
    if first_daily_mode == "paragraph":
        first_daily_fill["day_reflection"] = "authored paragraph mode"
    else:
        first_daily_fill["good_day"] = True

    return [
        STEP(
            expect=trident(
                program_authoring_proof_event(
                    "probe",
                    label=proof_label,
                    minimum=proof_minimum,
                    payload_env=proof_env,
                ),
                message_event(
                    "probe",
                    level="info",
                    contains="program authoring proof mounted",
                ),
                event_kind="MANUALFILLNEEDEDSTEP",
                finished=False,
            ),
            note=(
                "Mount Wp and prove resolved symbols, launch puppeteering, "
                "appearance overrides, and kernel flags."
            ),
        ),
        STEP(
            fill={
                "probe": {
                    "acknowledgement": "authoring surface understood",
                },
            },
            expect=trident(
                message_event(
                    "probe",
                    level="success",
                    contains="authoring proof acknowledged",
                ),
                event_kind="MANUALFILLNEEDEDSTEP",
                finished=False,
            ),
            note="Complete Wp and mount the first repeated daily appearance.",
        ),
        STEP(
            fill={
                "daily": first_daily_fill,
            },
            expect=trident(
                message_event("daily", level="success", contains="believe"),
                event_kind="MANUALFILLNEEDEDSTEP",
                finished=False,
            ),
            note=(
                "The first Wb appearance proves whether authored puppeteering "
                "survived the selected launch overlay mode."
            ),
        ),
        STEP(
            signal={
                "datum_id": "daily",
                "kind": "adjust_min",
                "info": {
                    "mins": [10, 12, 14],
                },
            },
            expect=trident(
                message_event(
                    "daily",
                    level="info",
                    contains="minimum adjusted",
                ),
                event_kind="MANUALFILLNEEDEDSTEP",
                finished=False,
            ),
            note="Signal-only dispatch mutates Wb configuration and reexplodes.",
        ),
        STEP(
            fill={
                "daily": {
                    "representative_number": 20,
                    "day_reflection": "ready for the next step",
                },
            },
            expect=trident(
                message_event("daily", level="success", contains="believe"),
                message_event("guess", level="info", contains="started"),
                event_kind="MANUALFILLNEEDEDSTEP",
                finished=False,
            ),
            note=(
                "Complete repeated Wb; Wa consumes the latest Wb lifecycle row "
                "while Wc mounts beside it."
            ),
        ),
        STEP(
            fill={
                "board": {
                    "new_1": 1,
                    "new_2": 3,
                    "new_3": 5,
                },
                "guess": {
                    "guess_1_1": 3,
                    "guess_1_2": 7,
                    "guess_1_3": 11,
                },
            },
            signal={
                "datum_id": "guess",
                "kind": "do_not_count",
                "info": {
                    "reason": "demonstrate fill-plus-signal",
                },
            },
            expect=trident(
                message_event("guess", level="info", contains="closest"),
                message_event("board", level="info", contains="cumulative"),
                event_kind="MANUALFILLNEEDEDSTEP",
                finished=False,
            ),
            note=(
                "One vector fill targets two datums; only Wa receives the "
                "custom signal. Wc is non-authoritative and remains open."
            ),
        ),
        STEP(
            fill={
                "guess": {
                    "guess_2_1": 20,
                    "guess_2_2": 27,
                },
            },
            expect=trident(
                message_event("guess", level="success", contains="correct"),
                event_kind="ATCOMPLETION",
                finished=True,
            ),
            note=(
                "The latest daily wire supplies target 20, satisfying the "
                "authoritative Wa datum and completing the program."
            ),
        ),
        UNDO(
            expect=trident(
                action="UNDO",
                event_kind="MANUALFILLNEEDEDSTEP",
                finished=False,
            ),
            note="UNDO is an ordinary, fully bracketed controller dispatch.",
        ),
        REDO(
            expect=trident(
                action="REDO",
                event_kind="ATCOMPLETION",
                finished=True,
            ),
            note="REDO restores completion in a fresh controller envelope.",
        ),
    ]


expected_unrolling = _expected_unrolling(
    proof_label="launch-merge-label",
    proof_minimum=4,
    proof_env="launch-merge",
    first_daily_mode="checkbox",
    first_daily_number=8,
)

expected_unrolling_take_over = _expected_unrolling(
    proof_label="launch-take-over-label",
    proof_minimum=6,
    proof_env="launch-take-over",
    first_daily_mode="checkbox",
    first_daily_number=8,
)


PROGRAM_TAKE_OVER = deepcopy(PROGRAM)


__all__ = [
    "PROGRAM",
    "PROGRAM_TAKE_OVER",
    "PUPPET",
    "PUPPET_TAKE_OVER",
    "expected_unrolling",
    "expected_unrolling_take_over",
]