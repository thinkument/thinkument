from __future__ import annotations

"""
Controller-loop event packets.

This module owns every event-specific concern for the page-flow controller:

- callback lookup;
- packet construction;
- timestamps and ids;
- start/end payload construction;
- session-queue delivery;
- synchronous callback delivery.

Controller-loop events are first-class live session events. They are appended to
the same bounded transient session event queue as datum lifecycle events, and
then synchronously forwarded to the dispatch callback when one is supplied.

They are still not durable state. They do not enter snapshots, outputs, datum
lifecycle rows, runtime indexes, or persisted engine state.

The queue/callback consumer decides whether to persist, forward, render, index,
or discard each packet.
"""

import warnings
from typing import Any, Callable, Dict, Mapping, Optional
from uuid import uuid4

from _thinkprogram._iomicrosTM.tiny_helpers import (
    DeadJSONError,
    _utc_now_iso_v1,
    assert_dead_json,
)


CONTROLLER_LOOP_EVENT_KIND_V1 = "controller_loop_event_v1"
CONTROLLER_LOOP_EVENT_SOURCE_V1 = "page_flow_controller"

CONTROLLER_LOOP_START_EVENT_NAME_V1 = "controller.loop.start"
CONTROLLER_LOOP_END_EVENT_NAME_V1 = "controller.loop.end"

ControllerEventCallback = Callable[[Mapping[str, Any]], None]
ControllerEventSink = Callable[[Mapping[str, Any]], None]


def new_controller_dispatch_id_v1() -> str:
    return str(uuid4())


def normalize_dispatcher_identity_id_v1(value: Any) -> str:
    """
    Normalize the externally supplied identity of one dispatcher.

    Dispatcher identity is required before controller entry. It is distinct
    from dispatch_id:

        dispatcher_identity_id
            Stable higher-application actor/client identity.

        dispatch_id
            Unique identity of one controller execution envelope.
    """
    identity_id = str(value or "").strip()
    if not identity_id:
        identity_id = ""
    return identity_id


def normalize_dispatcher_role_v1(value: Any) -> Optional[str]:
    """
    Normalize the role acting through one dispatch.

    Roleless dispatch is represented by JSON null, never by "", "None", or
    "null".
    """
    if value is None:
        return None

    role = str(value).strip()
    if not role or role.lower() in {"none", "null"}:
        return None
    return role


def controller_event_callback_v1(
    callbacks: Mapping[str, Any],
    *,
    callback_key: str,
) -> Optional[ControllerEventCallback]:
    callback = callbacks.get(callback_key)
    return callback if callable(callback) else None


def _controller_loop_payload_v1(
    *,
    U: Mapping[str, Any],
    timestamp: str,
    submitted_fill: Mapping[str, Any],
    submitted_signal: Optional[Mapping[str, Any]],
    result: Optional[Mapping[str, Any]] = None,
    system_error: Optional[Mapping[str, Any]] = None,
    dispatch_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    action_packet = {
        "fill": dict(submitted_fill),
        "signal": (
            dict(submitted_signal)
            if isinstance(submitted_signal, Mapping)
            else None
        ),
    }
    payload: Dict[str, Any] = {
        "U": dict(U),
        # A is the authoritative normalized controller action packet and is
        # present on both start and end. fill/signal remain compatibility
        # mirrors and must be projected together with A at release time.
        "A": action_packet,
        "fill": dict(action_packet["fill"]),
        "signal": (
            dict(action_packet["signal"])
            if isinstance(action_packet["signal"], Mapping)
            else None
        ),
        "timestamp": str(timestamp),
    }

    if isinstance(result, Mapping):
        payload["outcome"] = "success"
        payload["result"] = dict(result)
    elif isinstance(system_error, Mapping):
        payload["outcome"] = "system_error"
        payload["system_error"] = dict(system_error)

    if isinstance(dispatch_context, Mapping):
        payload["dispatch_context"] = dict(dispatch_context)

    return payload


def build_controller_loop_event_v1(
    *,
    phase: str,
    dispatch_id: str,
    dispatcher_identity_id: str,
    dispatcher_role: Optional[str],
    session_id: str,
    action_name: str,
    U: Mapping[str, Any],
    submitted_fill: Mapping[str, Any],
    submitted_signal: Optional[Mapping[str, Any]],
    result: Optional[Mapping[str, Any]] = None,
    system_error: Optional[Mapping[str, Any]] = None,
    dispatch_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    phase_name = str(phase).strip().lower()
    if phase_name not in {"start", "end"}:
        raise ValueError(
            "controller loop event phase must be 'start' or 'end'"
        )

    emitted_at = _utc_now_iso_v1()
    normalized_identity_id = normalize_dispatcher_identity_id_v1(
        dispatcher_identity_id
    )
    normalized_role = normalize_dispatcher_role_v1(dispatcher_role)

    event = {
        "kind": CONTROLLER_LOOP_EVENT_KIND_V1,
        "event_id": str(uuid4()),
        "dispatch_id": str(dispatch_id),
        "dispatcher_identity_id": normalized_identity_id,
        "dispatcher_role": normalized_role,
        "emitted_at": emitted_at,
        "source": CONTROLLER_LOOP_EVENT_SOURCE_V1,
        "name": (
            CONTROLLER_LOOP_START_EVENT_NAME_V1
            if phase_name == "start"
            else CONTROLLER_LOOP_END_EVENT_NAME_V1
        ),
        "phase": phase_name,
        "session_id": str(session_id),
        "action": str(action_name),
        "payload": _controller_loop_payload_v1(
            U=U,
            timestamp=emitted_at,
            submitted_fill=submitted_fill,
            submitted_signal=submitted_signal,
            result=result,
            system_error=system_error,
            dispatch_context=(
                dispatch_context
                if phase_name == "end"
                else None
            ),
        ),
    }

    try:
        assert_dead_json(event, path="controller_loop_event")
    except DeadJSONError as exc:
        raise TypeError(str(exc)) from exc

    return event


def emit_controller_loop_event_v1(
    *,
    callback: Optional[ControllerEventCallback],
    event_sink: Optional[ControllerEventSink] = None,
    phase: str,
    dispatch_id: str,
    dispatcher_identity_id: str,
    dispatcher_role: Optional[str],
    session_id: str,
    action_name: str,
    U: Mapping[str, Any],
    submitted_fill: Mapping[str, Any],
    submitted_signal: Optional[Mapping[str, Any]],
    result: Optional[Mapping[str, Any]] = None,
    system_error: Optional[Mapping[str, Any]] = None,
    dispatch_context: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Build and synchronously deliver one controller-loop event.

    Delivery order:
        1. authoritative session-local transient queue sink;
        2. best-effort dispatch callback.

    The canonical sink is authoritative. A canonical sink failure propagates
    to the caller.

    Callback exceptions are isolated after canonical queue delivery so a
    best-effort consumer cannot break the controller start/end invariant.

    If neither sink nor callback exists, no packet is constructed.
    """
    if not callable(callback) and not callable(event_sink):
        return None

    event = build_controller_loop_event_v1(
        phase=phase,
        dispatch_id=dispatch_id,
        dispatcher_identity_id=dispatcher_identity_id,
        dispatcher_role=dispatcher_role,
        session_id=session_id,
        action_name=action_name,
        U=U,
        submitted_fill=submitted_fill,
        submitted_signal=submitted_signal,
        result=result,
        system_error=system_error,
        dispatch_context=dispatch_context,
    )

    if callable(event_sink):
        event_sink(event)

    if callable(callback):
        try:
            callback(event)
        except Exception as exc:
            # Callback failure is observational only. It must remain isolated
            # even when the host has configured RuntimeWarning as an exception;
            # otherwise a failed start callback could escape after the
            # canonical start was already recorded and prevent the matching end.
            try:
                warnings.warn(
                    "controller event callback raised and was isolated: "
                    f"{type(exc).__name__}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
            except Exception:
                pass

    return event


__all__ = [
    "CONTROLLER_LOOP_END_EVENT_NAME_V1",
    "CONTROLLER_LOOP_EVENT_KIND_V1",
    "CONTROLLER_LOOP_EVENT_SOURCE_V1",
    "CONTROLLER_LOOP_START_EVENT_NAME_V1",
    "ControllerEventCallback",
    "ControllerEventSink",
    "build_controller_loop_event_v1",
    "controller_event_callback_v1",
    "emit_controller_loop_event_v1",
    "new_controller_dispatch_id_v1",
    "normalize_dispatcher_identity_id_v1",
    "normalize_dispatcher_role_v1",
]