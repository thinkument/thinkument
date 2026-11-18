from __future__ import annotations

"""
P8 — session metadata as the scalable activation/modulation head.

ThinkProgramTM owns the semantic program:

    widgets
    flow
    symbols
    puppeteering

Session metadata is supplied once when the live session is created. It does not
create another program or another state machine. It activates orthogonal runtime
policies around the same run.

This executable guide proves only public, app-facing effects:

* full-create metadata is normalized and retained as dead JSON;
* manual_io and session_storage are visible in controller payload.U;
* an inert app-owned top-level pocket survives full-create coercion;
* the effective metadata is stable across controller start/end packets;
* widget lifecycle and program progression remain ordinary ThinkProgramTM
  behavior.

P8 intentionally does not interpret role modulation. P9 zooms into that one
session-metadata sub-surface.
"""

from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._shared import (
    STEP,
    base_widgets,
    message_event,
    program,
    trident,
)


ACTIVATION_POCKET = "dry_run_lib_widgets_flows_activation"

SESSION_METADATA = {
    "manual_io": {
        "persistence": "disabled",
        "profile": True,
        "include_full_multiframespec_in_ctx": True,
        "include_global_fill_keys_in_ctx": False,
        "include_field_value_keys_in_ctx": False,
        "include_forms_emitted_order_in_ctx": True,
        "max_fields_per_submit": 64,
        "max_payload_chars": 100_000,
    },
    "session_storage": {
        "events_snapshot_window": 64,
        "forms_emitted_snapshot_window": 8,
        "redo_max_depth": 4,
        "redo_action_max_payload_chars": 20_000,
    },
    ACTIVATION_POCKET: {
        "kind": "dry_run_lib_widgets_flows_activation_v1",
        "lesson": "session metadata is an orthogonal activation head",
        "features": [
            "manual_io",
            "session_storage",
            "app_owned_dead_json_pocket",
        ],
        "enabled": True,
    },
}


def _metadata_needles(*, phase: str) -> dict:
    return {
        "kind": "controller_loop_event_v1",
        "phase": phase,
        "payload.U.session_metadata.manual_io.persistence": "disabled",
        "payload.U.session_metadata.manual_io.profile": True,
        (
            "payload.U.session_metadata.manual_io."
            "include_full_multiframespec_in_ctx"
        ): True,
        (
            "payload.U.session_metadata.manual_io."
            "include_forms_emitted_order_in_ctx"
        ): True,
        "payload.U.session_metadata.manual_io.max_fields_per_submit": 64,
        "payload.U.session_metadata.manual_io.max_payload_chars": 100_000,
        (
            "payload.U.session_metadata.session_storage."
            "events_snapshot_window"
        ): 64,
        (
            "payload.U.session_metadata.session_storage."
            "forms_emitted_snapshot_window"
        ): 8,
        "payload.U.session_metadata.session_storage.redo_max_depth": 4,
        (
            "payload.U.session_metadata.session_storage."
            "redo_action_max_payload_chars"
        ): 20_000,
        (
            f"payload.U.session_metadata.{ACTIVATION_POCKET}.kind"
        ): "dry_run_lib_widgets_flows_activation_v1",
        (
            f"payload.U.session_metadata.{ACTIVATION_POCKET}.lesson"
        ): "session metadata is an orthogonal activation head",
        (
            f"payload.U.session_metadata.{ACTIVATION_POCKET}.features"
        ): [
            "manual_io",
            "session_storage",
            "app_owned_dead_json_pocket",
        ],
        (
            f"payload.U.session_metadata.{ACTIVATION_POCKET}.enabled"
        ): True,
    }


def metadata_trident(
    *middle: dict,
    event_kind: str,
    finished: bool,
) -> dict:
    expected = trident(
        *middle,
        event_kind=event_kind,
        finished=finished,
    )
    expected["Estart"].update(_metadata_needles(phase="start"))
    expected["Eend"].update(_metadata_needles(phase="end"))
    return expected


WIDGETS = base_widgets()

PROGRAM = program(
    program_id="dry_run_lib_widgets_flows_p8",
    title="Basic expose P8 — session metadata activation head",
    symbols={},
    puppeteering={},
    widgets=WIDGETS,
    flow=[
        {
            "id": "metadata_daily",
            "title": "Ordinary widget under activated session policy",
            "widgets": ["daily"],
            "authoritative": [True],
        },
        {
            "id": "metadata_guess",
            "title": "Program semantics continue under the same metadata",
            "widgets": ["guess"],
            "authoritative": [True],
        },
    ],
)

PUPPET = None

expected_unrolling = [
    STEP(
        expect=metadata_trident(
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note=(
            "Create one ordinary ThinkProgram session under explicit manual_io, "
            "session_storage, and inert app-owned activation metadata."
        ),
    ),
    STEP(
        fill={
            "daily": {
                "representative_number": 11,
                "good_day": True,
            }
        },
        expect=metadata_trident(
            message_event("daily", level="success", contains="believe"),
            message_event("guess", level="info", contains="started"),
            message_event("guess", level="info", contains="hint"),
            event_kind="MANUALFILLNEEDEDSTEP",
            finished=False,
        ),
        note=(
            "Metadata remains stable while ordinary lifecycle events are "
            "sandwiched inside the controller envelope."
        ),
    ),
    STEP(
        fill={
            "guess": {
                "guess_1_1": 17,
                "guess_1_2": 3,
                "guess_1_3": 5,
            }
        },
        expect=metadata_trident(
            message_event("guess", level="success", contains="correct"),
            event_kind="ATCOMPLETION",
            finished=True,
        ),
        note=(
            "The activation head does not replace widget/program semantics; "
            "the same flow completes normally."
        ),
    ),
]


__all__ = [
    "ACTIVATION_POCKET",
    "PROGRAM",
    "PUPPET",
    "SESSION_METADATA",
    "expected_unrolling",
]