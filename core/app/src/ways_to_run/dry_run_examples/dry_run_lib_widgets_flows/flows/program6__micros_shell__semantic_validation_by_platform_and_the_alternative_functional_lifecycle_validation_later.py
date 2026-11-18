from __future__ import annotations

"""P6 — platform semantic validation versus lifecycle functional validation.

The program removes composition noise: one authoritative datum, one step, and
one current-effective shell.

A0 mount
    The widget authors a shell whose integer micro has min/max platform
    validators. Mount emits one ordinary datum.message.

A1 signal only
    Required micros are blank. Partial platform validation does not enforce
    requiredness, so the signal catcher runs.

A2 invalid platform fill plus signal
    Platform validation stops before the fill handler or signal catcher. The
    informative middle is exactly empty; controller end exposes last_error.

A3 platform-valid, lifecycle-invalid
    The widget handler emits an observation and domain error, then reexplodes.

A4 fully valid
    Both layers accept and the program completes.
"""

from ways_to_run.dry_run_examples.dry_run_standard_lingo import datum_event_v1

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import STEP, message_event, program, trident
from ..widgets.semantic_validation_widgets import WF_WIDGET


WIDGETS = {
    "semantic_probe": {
        "widget": WF_WIDGET,
        "title": "Semantic validation layers",
        "args": {
            "platform_minimum": 10,
            "platform_maximum": 20,
            "lifecycle_prefix": "LIFE-",
        },
        "lifecycle": {
            "max_reexplosions": 12,
            "max_messages": 24,
            "max_proc_notes": 0,
            "exhausted_means_satisfied": False,
        },
        "wires": {},
        "tags": ["p6", "semantic-validation", "proof"],
        "system_flags": {"guide_surface": "P6"},
        "authoritative": True,
    },
}


PROGRAM = program(
    program_id="dry_run_lib_widgets_flows_p6",
    title="Basic expose P6 — semantic validation layers",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "semantic_validation_layers",
            "title": "Platform wall and lifecycle alternative",
            "widgets": ["semantic_probe"],
            "authoritative": [True],
        },
    ],
)

PUPPET = None


def _observed(*, branch: str, signal_kind: str) -> dict:
    return datum_event_v1(
        "semantic_probe",
        name="semantic_validation.lifecycle_observed",
        payload_needles={
            "payload.proof.branch": str(branch),
            "payload.proof.signal_kind": str(signal_kind),
        },
    )


def _semantic_envelope(
    *middle: dict,
    event_kind: str = "MANUALFILLNEEDEDSTEP",
    finished: bool = False,
    exact_middle: bool = False,
) -> dict:
    return trident(
        *middle,
        event_kind=event_kind,
        finished=finished,
        exact_middle=exact_middle,
    )


_platform_rejected = _semantic_envelope(exact_middle=True)
_platform_rejected["Eend"][
    "payload.result.last_error.semantic_probe__contains"
] = "must be"


expected_unrolling = [
    STEP(
        expect=_semantic_envelope(
            message_event(
                "semantic_probe",
                level="info",
                contains="platform-validated",
            ),
        ),
        note=(
            "Mount authors the current-effective shell and attached platform "
            "validators."
        ),
    ),
    STEP(
        signal={
            "datum_id": "semantic_probe",
            "kind": "explain",
            "info": {"lesson": "signals are commands"},
        },
        expect=_semantic_envelope(
            _observed(
                branch="signal_catcher",
                signal_kind="explain",
            ),
            message_event(
                "semantic_probe",
                level="info",
                contains="signals themselves are not micro values",
            ),
        ),
        note=(
            "Signal-only dispatch reaches the catcher despite blank required "
            "micros because partial validation does not enforce requiredness."
        ),
    ),
    STEP(
        fill={
            "semantic_probe": {
                "platform_number": 5,
                "lifecycle_code": "LIFE-would-have-been-valid",
            }
        },
        signal={
            "datum_id": "semantic_probe",
            "kind": "explain",
            "info": {"should_reach_handler": False},
        },
        expect=_platform_rejected,
        note=(
            "The platform rejects before either lifecycle branch. Exact-empty "
            "middle proves that no widget event was emitted."
        ),
    ),
    STEP(
        fill={
            "semantic_probe": {
                "platform_number": 12,
                "lifecycle_code": "wrong-prefix",
            }
        },
        expect=_semantic_envelope(
            _observed(
                branch="fill_handler",
                signal_kind="fill",
            ),
            message_event(
                "semantic_probe",
                level="error",
                contains="lifecycle_code must start",
            ),
        ),
        note=(
            "Platform validators pass; lifecycle code then rejects within the "
            "widget and reexplodes with ordinary informative events."
        ),
    ),
    STEP(
        fill={
            "semantic_probe": {
                "platform_number": 12,
                "lifecycle_code": "LIFE-accepted",
            }
        },
        expect=_semantic_envelope(
            _observed(
                branch="fill_handler",
                signal_kind="fill",
            ),
            message_event(
                "semantic_probe",
                level="success",
                contains="both platform and lifecycle validation accepted",
            ),
            event_kind="ATCOMPLETION",
            finished=True,
        ),
        note="Both layers accept and the authoritative datum completes P6.",
    ),
]


__all__ = ["PROGRAM", "PUPPET", "expected_unrolling"]
