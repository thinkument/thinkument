from __future__ import annotations

"""Ergonomic flow-authoring facade for ``dry_run_lib_widgets_flows``.

This module intentionally contains no runner, matcher, registration, case
catalog, widget implementation, or program-building logic. It only composes:

The ownership boundary remains visible in the imported modules while existing
flow files keep one compact authoring import surface.
"""

from ways_to_run.dry_run_examples.dry_run_standard_lingo import (
    PREFLIGHT_EXCEPTION,
    PREFLIGHT_REJECTION,
    REDO,
    ROLE_VIEW,
    STEP,
    UNDO,
    end_event,
    message_event,
    projected_U,
    role_projected_trident,
    start_event,
    system_error_end,
    system_error_trident,
    trident,
)
from ways_to_run.dry_run_examples.dry_run_standard_lingo.data_blanket_expectations_v1 import (
    CONTEXT_VIEW,
    DATA_BLANKET,
)



from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows._widget_catalog import (
    fundamentals_base_widgets_v1,
    fundamentals_program_authoring_probe_widget_v1,
    fundamentals_wiring_observer_widget_v1,
)



from copy import deepcopy
from typing import Any, Dict, Mapping, Sequence



"""Application-specific event needles for fundamentals teaching widgets."""

from ways_to_run.dry_run_examples.dry_run_standard_lingo.event_expectations_v1 import datum_event_v1



def fundamentals_wiring_proof_event_v1(
    datum_id: str,
    *,
    self_previous_present: bool,
) -> Dict[str, Any]:
    return datum_event_v1(
        datum_id,
        name="wiring.proof",
        payload_needles={
            "payload.proof.args.lesson_label": "exact-wiring-runtime-view",
            "payload.proof.args.expected_many_count": 2,
            (
                "payload.proof.wire_state_index.one_source.container_kind"
            ): "one_row",
            "payload.proof.wire_state_index.one_source.row_count": 1,
            (
                "payload.proof.wire_state_index.many_sources.container_kind"
            ): "row_list",
            "payload.proof.wire_state_index.many_sources.row_count": 2,
            "payload.proof.self_previous_present": bool(
                self_previous_present
            ),
        },
    )




FUNDAMENTALS_PROGRAM_DESCRIPTION_V1 = (
    "Executable get-started flow for widget lifecycle, dispatch, and "
    "canonical event-stream learning."
)

FUNDAMENTALS_RUN_CONFIG_V1: Dict[str, Any] = {
    "manual_io": {
        "persistence": "disabled",
        "include_full_multiframespec_in_ctx": True,
        "include_forms_emitted_order_in_ctx": True,
    },
    "session_storage": {
        "events_snapshot_window": 256,
    },
}


def program(
    *,
    program_id: str,
    title: str,
    symbols: Mapping[str, Any],
    puppeteering: Mapping[str, Any],
    widgets: Mapping[str, Any],
    flow: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Build one highest-language program using fundamentals-app defaults."""

    return {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": deepcopy(dict(symbols)),
        "puppeteering": deepcopy(dict(puppeteering)),
        "run": {
            "program": {
                "info": {
                    "id": str(program_id),
                    "title": str(title),
                    "description": FUNDAMENTALS_PROGRAM_DESCRIPTION_V1,
                },
                "widgets": deepcopy(dict(widgets)),
                "flow": deepcopy([dict(step) for step in flow]),
            },
            "config": deepcopy(FUNDAMENTALS_RUN_CONFIG_V1),
        },
    }


base_widgets = fundamentals_base_widgets_v1
program_authoring_probe_widget = (
    fundamentals_program_authoring_probe_widget_v1
)
wiring_observer_widget = fundamentals_wiring_observer_widget_v1
wiring_proof_event = fundamentals_wiring_proof_event_v1


__all__ = [
    "CONTEXT_VIEW",
    "DATA_BLANKET",
    "PREFLIGHT_EXCEPTION",
    "PREFLIGHT_REJECTION",
    "REDO",
    "ROLE_VIEW",
    "STEP",
    "UNDO",
    "base_widgets",
    "end_event",
    "message_event",
    "program",
    "program_authoring_probe_widget",
    "projected_U",
    "role_projected_trident",
    "start_event",
    "system_error_end",
    "system_error_trident",
    "trident",
    "wiring_observer_widget",
    "wiring_proof_event",
]