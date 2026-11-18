from __future__ import annotations

"""Versioned event-needle constructors for strategy-agnostic dry runs.

The returned mappings are expectation data, not runtime event builders. Keys
without a suffix mean equality. ``__contains`` and ``__absent`` are interpreted
by the dry-run runner's standard needle matcher.
"""

from typing import Any, Dict, Mapping, Optional

from .protocol_v1 import (
    CONTROLLER_LOOP_EVENT_KIND_V1,
    SESSION_EVENT_KIND_V1,
)


def datum_event_v1(
    datum_id: str,
    *,
    name: str,
    payload_needles: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "kind": SESSION_EVENT_KIND_V1,
        "datum_id": str(datum_id),
        "name": str(name),
    }
    out.update(dict(payload_needles or {}))
    return out


def datum_message_event_v1(
    datum_id: str,
    *,
    level: str,
    contains: str,
) -> Dict[str, Any]:
    return datum_event_v1(
        datum_id,
        name="datum.message",
        payload_needles={
            "payload.message.level": str(level),
            "payload.message.text__contains": str(contains),
        },
    )


def controller_start_event_v1(*, action: str = "STEP") -> Dict[str, Any]:
    return {
        "kind": CONTROLLER_LOOP_EVENT_KIND_V1,
        "phase": "start",
        "name": "controller.loop.start",
        "action": str(action),
    }


def controller_end_event_v1(
    *,
    action: str = "STEP",
    event_kind: Optional[str] = None,
    finished: Optional[bool] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "kind": CONTROLLER_LOOP_EVENT_KIND_V1,
        "phase": "end",
        "name": "controller.loop.end",
        "action": str(action),
    }
    if event_kind is not None:
        out["payload.result.event_kind"] = str(event_kind)
    if finished is not None:
        out["payload.result.finished"] = bool(finished)
    return out


def controller_system_error_end_event_v1(
    *,
    action: str = "STEP",
    exception_type: str,
    contains: str,
) -> Dict[str, Any]:
    return {
        "kind": CONTROLLER_LOOP_EVENT_KIND_V1,
        "phase": "end",
        "name": "controller.loop.end",
        "action": str(action),
        "payload.outcome": "system_error",
        "payload.system_error.kind": "controller_dispatch_system_error_v1",
        "payload.system_error.exception_type": str(exception_type),
        "payload.system_error.message__contains": str(contains),
    }


def controller_envelope_v1(
    *middle: Mapping[str, Any],
    action: str = "STEP",
    event_kind: Optional[str] = None,
    finished: Optional[bool] = None,
    exact_middle: bool = False,
) -> Dict[str, Any]:
    return {
        "Estart": controller_start_event_v1(action=action),
        "Edatums": [dict(needle) for needle in middle],
        "Edatums_exact": bool(exact_middle),
        "Eend": controller_end_event_v1(
            action=action,
            event_kind=event_kind,
            finished=finished,
        ),
    }


def controller_system_error_envelope_v1(
    *,
    exception_type: str,
    contains: str,
    action: str = "STEP",
    exact_middle: bool = True,
) -> Dict[str, Any]:
    return {
        "Estart": controller_start_event_v1(action=action),
        "Edatums": [],
        "Edatums_exact": bool(exact_middle),
        "Eend": controller_system_error_end_event_v1(
            action=action,
            exception_type=exception_type,
            contains=contains,
        ),
    }


message_event = datum_message_event_v1
start_event = controller_start_event_v1
end_event = controller_end_event_v1
system_error_end = controller_system_error_end_event_v1
trident = controller_envelope_v1
system_error_trident = controller_system_error_envelope_v1


__all__ = [
    "controller_end_event_v1",
    "controller_envelope_v1",
    "controller_start_event_v1",
    "controller_system_error_end_event_v1",
    "controller_system_error_envelope_v1",
    "datum_event_v1",
    "datum_message_event_v1",
    "end_event",
    "message_event",
    "start_event",
    "system_error_end",
    "system_error_trident",
    "trident",
]
