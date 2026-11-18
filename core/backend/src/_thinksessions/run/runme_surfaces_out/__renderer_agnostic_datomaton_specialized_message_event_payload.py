from __future__ import annotations

import copy
from typing import Any, Dict, Mapping

from _thinkprogram._iomicrosTM.tiny_helpers import (
    DeadJSONError,
    assert_dead_json,
)


RENDERER_AGNOSTIC_DATOMATON_SPECIALIZED_MESSAGE_EVENT_PAYLOAD_SHAPE_V1 = {
    "kind": (
        "renderer_agnostic_datomaton_specialized_message_event_payload_v1"
    ),
    "description": (
        "Public renderer-agnostic specialized payload surface accepted from "
        "datum lifecycle widgets before canonical session-event payload "
        "normalization."
    ),
    "accepted_input": "any dead-json value",
    "session_event_normalization": {
        "none": "normalized by the session-event builder to an empty dict",
        "mapping": (
            "copied by the session-event builder as the event payload mapping"
        ),
        "scalar_or_sequence": (
            "normalized by the session-event builder to {'value': input}"
        ),
    },
}


def renderer_agnostic_datomaton_specialized_message_event_payload_shape_v1(
) -> Dict[str, Any]:
    """
    Return public documentation-as-data for datomaton event payload values.

    A copy is returned so callers cannot mutate the shared public surface.
    """
    return copy.deepcopy(
        RENDERER_AGNOSTIC_DATOMATON_SPECIALIZED_MESSAGE_EVENT_PAYLOAD_SHAPE_V1
    )


def ensure_renderer_agnostic_datomaton_specialized_message_event_payload_v1(
    payload: Any,
) -> Any:
    """
    Validate one datomaton specialized-message event payload value.

    Datomaton payloads may be any dead-json value. Canonical conversion into
    the final session-event payload mapping remains the responsibility of
    build_session_event.
    """
    try:
        assert_dead_json(
            payload,
            path="datomaton_specialized_message_event_payload",
        )
    except DeadJSONError as exc:
        raise ValueError(str(exc)) from exc

    if isinstance(payload, Mapping):
        return dict(payload)

    if isinstance(payload, list):
        return list(payload)

    return payload


def check_renderer_agnostic_datomaton_specialized_message_event_payload_v1(
    payload: Any,
) -> bool:
    """
    Return whether a value satisfies the public datomaton payload contract.
    """
    try:
        ensure_renderer_agnostic_datomaton_specialized_message_event_payload_v1(
            payload
        )
    except ValueError:
        return False

    return True


__all__ = [
    (
        "RENDERER_AGNOSTIC_DATOMATON_SPECIALIZED_MESSAGE_EVENT_"
        "PAYLOAD_SHAPE_V1"
    ),
    (
        "renderer_agnostic_datomaton_specialized_message_event_"
        "payload_shape_v1"
    ),
    (
        "ensure_renderer_agnostic_datomaton_specialized_message_event_"
        "payload_v1"
    ),
    (
        "check_renderer_agnostic_datomaton_specialized_message_event_"
        "payload_v1"
    ),
]