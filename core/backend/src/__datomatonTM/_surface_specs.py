from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from _thinksessions.run.runme_surfaces_out.__renderer_agnostic_datomaton_specialized_message_event_payload import (
    renderer_agnostic_datomaton_specialized_message_event_payload_shape_v1,
)

from ._globals import (
    Q_SIGNAL_CONTROLLER,
    Q_SIGNAL_FILL,
    Q_STATUS_BLOCKED,
    Q_STATUS_DONE,
    Q_STATUS_REEXPLODE,
)


DATUM_LIFECYCLE_RESERVED_RESULT_KEYS = frozenset(
    {
        "status",
        "message",
        "messages",
        "core",
        "fill",
        "prefill",
        "state",
        "proc_notes",
    }
)

DATUM_WIDGET_INPUT_REQUIRED_KEYS_V1 = (
    "form_id",
    "frame_id",
    "span_id",
    "datum_id",
    "datum",
    "raw_fill",
    "partial_fill",
    "prefill",
    "state",
    "messages",
    "proc_notes",
    "structurally_satisfied",
    "reexplode_count",
    "max_reexplosions",
    "max_proc_notes",
    "max_messages",
    "signal",
    "signal_kind",
    "signal_info",
    "ctx",
    "emit",
)

DATUM_WIDGET_INPUT_SURFACE_SHAPE_V1 = {
    "kind": "datum_widget_input_observation_v1",
    "description": (
        "Engine -> widget observation packet. This is not the same shape as "
        "the widget result packet."
    ),
    "identity": {
        "form_id": "str",
        "frame_id": "str",
        "span_id": "str",
        "datum_id": "str",
    },
    "current_surfaces": {
        "datum": (
            "dict dead-json current-effective datum surface. After a "
            "reexplode commit this is the previous reexplode result.datum."
        ),
        "raw_fill": "original/manual fill payload supplied for this step",
        "partial_fill": (
            "datum-local/current fill value. After a reexplode commit this "
            "may come from the previous reexplode result.fill overlay."
        ),
        "prefill": (
            "current prefill/default value. After a reexplode commit this may "
            "come from the previous reexplode result.prefill overlay."
        ),
    },
    "lifecycle_memory": {
        "state": (
            "dict dead-json previous committed widget state. This comes from "
            "the previous result.state."
        ),
        "messages": (
            "list[message] bounded lifecycle message history. This comes from "
            "previous result.messages/result.message entries."
        ),
        "proc_notes": (
            "list[dict] bounded lifecycle proc_notes history. This comes from "
            "previous reexplode result.proc_notes entries."
        ),
        "reexplode_count": "int",
        "max_reexplosions": "int",
        "max_proc_notes": "int",
        "max_messages": "int",
    },
    "signal": {
        "structurally_satisfied": "bool",
        "signal": {"kind": "fill | mount | str", "info": "dict"},
        "signal_kind": "fill | mount | str",
        "signal_info": "dict",
        "ctx": "small convenience context; not durable lifecycle state",
    },
    "events": {
        "emit": (
            'callable: q["emit"](payload=None, *, name="datum.event") '
            "-> event packet"
        ),
        "payload_surface": (
            renderer_agnostic_datomaton_specialized_message_event_payload_shape_v1()
        ),
    },
}

DATUM_WIDGET_RESULT_STATUSES_V1 = (
    Q_STATUS_DONE,
    Q_STATUS_BLOCKED,
    Q_STATUS_REEXPLODE,
)

DATUM_WIDGET_RESULT_COMMON_SHAPE_V1 = {
    "status": "done | blocked | reexplode",
    "state": "dict dead-json",
    "message": {
        "level": "success | info | warning | error",
        "text": "str",
        "compatibility": (
            "singular message is accepted as a compatibility alias; engine "
            "normalizes internally to messages=[message]"
        ),
    },
    "messages": [
        {
            "level": "success | info | warning | error",
            "text": "str",
        }
    ],
    "events": [
        {
            "name": "str optional",
            "payload": (
                "any dead-json value conforming to the public "
                "renderer-agnostic datomaton specialized-message event "
                "payload surface"
            ),
        }
    ],
}

DATUM_WIDGET_RESULT_NONMUTATING_SHAPE_V1 = {
    "kind": "datum_widget_result_nonmutating_v1",
    "description": (
        "Widget -> engine lifecycle decision packet for status=done or "
        "status=blocked. It does not replace the current-effective datum "
        "surface."
    ),
    "required": {
        "status": "done | blocked",
    },
    "optional": {
        "state": (
            "dict dead-json next widget state. Becomes q['state'] on the next "
            "evaluation of the same lifecycle datum."
        ),
        "message": (
            "single lifecycle message compatibility alias. Prefer messages "
            "for new widgets."
        ),
        "messages": (
            "list[message] lifecycle messages to append to q['messages'] "
            "history, bounded by max_messages."
        ),
        "events": (
            "list[event spec] live transient events emitted after widget "
            "return; never durable lifecycle state."
        ),
    },
    "commit_effect": {
        "done": (
            "marks datum satisfied and persists final form fill through the "
            "normal manual-IO commit path"
        ),
        "blocked": (
            "keeps the manual span open/unsatisfied and records lifecycle "
            "state/messages for the next evaluation"
        ),
    },
}

DATUM_WIDGET_RESULT_MUTATING_SHAPE_V1 = {
    "kind": "datum_widget_result_mutating_reexplode_v1",
    "description": (
        "Widget -> engine lifecycle decision packet for status=reexplode. "
        "This is the only result shape that may replace the current-effective "
        "datum surface."
    ),
    "required": {
        "status": "reexplode",
        "datum": (
            "dict dead-json replacement current-effective datum surface for "
            "this logical datum id"
        ),
    },
    "optional": {
        "state": (
            "dict dead-json next widget state. Becomes q['state'] on the next "
            "evaluation of the same lifecycle datum."
        ),
        "fill": (
            "working fill overlay for the replacement datum. Becomes the "
            "next q['partial_fill'] / rendered field value overlay."
        ),
        "prefill": (
            "working prefill overlay for the replacement datum. Becomes the "
            "next q['prefill'] / fallback field value overlay."
        ),
        "message": (
            "single lifecycle message compatibility alias. Prefer messages "
            "for new widgets."
        ),
        "messages": (
            "list[message] lifecycle messages to append to q['messages'] "
            "history, bounded by max_messages."
        ),
        "proc_notes": (
            "dict dead-json compact carry item appended to q['proc_notes'] "
            "history, bounded by max_proc_notes."
        ),
        "events": (
            "list[event spec] live transient events emitted after widget "
            "return; never durable lifecycle state."
        ),
    },
}

DATUM_WIDGET_REEXPLODE_MUTABLE_FIELDS_V1 = {
    "datum": (
        "replacement current-effective datum surface. This is the structural "
        "mutation. The logical lifecycle row remains keyed by the original "
        "datum_id."
    ),
    "fill": "optional working fill overlay for this span/datum",
    "prefill": "optional working prefill overlay for this span/datum",
    "state": "next compact widget state",
    "message/messages": "bounded lifecycle message history additions",
    "proc_notes": "bounded compact proc_notes history addition",
    "events": "transient live events only; no durable state effect",
}

DATUM_WIDGET_RESULT_TO_NEXT_INPUT_V1 = {
    "result.state": "next q['state']",
    "result.message": "normalized to one entry in next q['messages']",
    "result.messages": "entries appended to next q['messages']",
    "result.proc_notes": (
        "only on reexplode; appended as one entry in next q['proc_notes']"
    ),
    "result.datum": (
        "only on reexplode; becomes next q['datum'] current-effective surface"
    ),
    "result.fill": (
        "only on reexplode; becomes working fill overlay and next "
        "q['partial_fill'] / rendered value source"
    ),
    "result.prefill": (
        "only on reexplode; becomes working prefill overlay and next "
        "q['prefill'] / rendered fallback source"
    ),
    "result.events": (
        "emitted live after return; never appears in next q input, durable "
        "state, outputs, or runtime write index"
    ),
}

DATUM_WIDGET_REEXPLODE_RESULT_EXTRA_SHAPE_V1 = {
    "datum": "dict dead-json replacement current-effective datum surface",
    "fill": "optional working fill overlay",
    "prefill": "optional working prefill overlay",
    "proc_notes": "optional dict dead-json bounded lifecycle proc_notes item",
}


def datum_widget_contract_shape_v1() -> Dict[str, Any]:
    """
    Public documentation-as-data for datum lifecycle widget authors.

    Runtime validation remains normalize_q_result_v1 plus dead-JSON checks.
    This helper is intentionally stable and importable by docs/tests/tooling.
    """
    return {
        "input_required_keys": list(DATUM_WIDGET_INPUT_REQUIRED_KEYS_V1),
        "input_surface_shape": copy.deepcopy(
            DATUM_WIDGET_INPUT_SURFACE_SHAPE_V1
        ),
        "result_statuses": list(DATUM_WIDGET_RESULT_STATUSES_V1),
        "result_common_shape": copy.deepcopy(
            DATUM_WIDGET_RESULT_COMMON_SHAPE_V1
        ),
        "result_nonmutating_shape": copy.deepcopy(
            DATUM_WIDGET_RESULT_NONMUTATING_SHAPE_V1
        ),
        "result_mutating_shape": copy.deepcopy(
            DATUM_WIDGET_RESULT_MUTATING_SHAPE_V1
        ),
        "reexplode_extra_shape": copy.deepcopy(
            DATUM_WIDGET_REEXPLODE_RESULT_EXTRA_SHAPE_V1
        ),
        "reexplode_mutable_fields": copy.deepcopy(
            DATUM_WIDGET_REEXPLODE_MUTABLE_FIELDS_V1
        ),
        "result_to_next_input": copy.deepcopy(
            DATUM_WIDGET_RESULT_TO_NEXT_INPUT_V1
        ),
        "signals": {
            "fill": "normal manual submit",
            "mount": "pre-render mount signal when lifecycle.mount_explode=True",
            "controller": (
                "optional higher/controller-origin datum-targeted signal. "
                "The concrete signal kind is open-ended and arrives in "
                "q['signal']['kind']; Q_SIGNAL_CONTROLLER is only the "
                "documentation name for this artery."
            ),
        },
        "event_emit": {
            "call": (
                'q["emit"](payload=None, *, name="datum.event")'
            ),
            "timing": "synchronous/immediate during widget function execution",
            "packet_kind": "datum_lifecycle_event_v1",
            "payload_shape": (
                renderer_agnostic_datomaton_specialized_message_event_payload_shape_v1()
            ),
            "validation": (
                "The same public renderer-agnostic payload checker is applied "
                "before both immediate q['emit'] events and returned "
                "result.events entries are passed to the canonical "
                "session-event builder."
            ),
        },
    }


@dataclass(frozen=True, slots=True)
class DatumQEvalV1:
    datum_id: str
    status: str
    message: Dict[str, str]
    state: Dict[str, Any]
    messages: Tuple[Dict[str, str], ...] = ()
    reexplode_datum: Optional[Dict[str, Any]] = None
    working_fill: Any = None
    has_working_fill: bool = False
    working_prefill: Any = None
    has_working_prefill: bool = False
    proc_notes: Optional[Dict[str, Any]] = None
    forced_done: bool = False
    signal_kind: str = Q_SIGNAL_FILL
    signal_info: Optional[Dict[str, Any]] = None
    emitted_events: Tuple[Dict[str, Any], ...] = ()


DatumWidgetFnV1 = Callable[[Mapping[str, Any]], Mapping[str, Any]]


__all__ = [
    "DATUM_LIFECYCLE_RESERVED_RESULT_KEYS",
    "DATUM_WIDGET_INPUT_REQUIRED_KEYS_V1",
    "DATUM_WIDGET_INPUT_SURFACE_SHAPE_V1",
    "DATUM_WIDGET_RESULT_STATUSES_V1",
    "DATUM_WIDGET_RESULT_COMMON_SHAPE_V1",
    "DATUM_WIDGET_RESULT_NONMUTATING_SHAPE_V1",
    "DATUM_WIDGET_RESULT_MUTATING_SHAPE_V1",
    "DATUM_WIDGET_REEXPLODE_MUTABLE_FIELDS_V1",
    "DATUM_WIDGET_RESULT_TO_NEXT_INPUT_V1",
    "DATUM_WIDGET_REEXPLODE_RESULT_EXTRA_SHAPE_V1",
    "datum_widget_contract_shape_v1",
    "DatumQEvalV1",
    "DatumWidgetFnV1",
]