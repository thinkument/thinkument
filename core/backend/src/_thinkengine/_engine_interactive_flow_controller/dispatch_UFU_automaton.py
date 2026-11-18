from __future__ import annotations

"""
Internal page-flow controller.

Controller-loop event law
-------------------------
When controller event delivery is enabled, a normal dispatch emits one
controller start, zero or more informative events, and one matching controller
end:

    controller.loop.start
        payload.U is the current entry universal UI context.
        payload.A is the authoritative normalized submitted action packet.
        payload.fill and payload.signal are compatibility mirrors of A.
        payload.timestamp is the event timestamp.

    controller.loop.end
        payload.U is the final or recovered universal UI context.
        payload.A identifies the original submitted action and is repeated
        unchanged on the canonical end packet. payload.fill/payload.signal are
        compatibility mirrors.

        On successful controller completion:

            payload.outcome == "success"
            payload.result summarizes the resolved controller result.

        On an ordinary in-process systematic failure after start:

            payload.outcome == "system_error"
            payload.system_error describes the caught exception.

Semantic rejection remains a successful controller outcome and is represented
by payload.result.last_error.

The start and end packets share one dispatch_id, dispatcher_identity_id, and
dispatcher_role, and have distinct event_ids.

Controller-loop events are emitted when either:
- a controller callback is supplied; or
- the session liaison exposes a controller-event session-queue sink.

In the normal concrete session APIs the sink exists, so controller-loop events
are recorded in the bounded transient session event queue even when no callback
is supplied.

Dispatcher identity validation occurs before request-boundary validation,
liaison-owned authorization preflight, controller entry, event emission, or
callback invocation. A missing dispatcher identity is therefore eventless.

Request-boundary validation and liaison-owned authorization preflight happen
before the controller start is emitted. Failures there remain ordinary caller
exceptions and do not create a controller trident.

Once a start has been successfully recorded, ordinary Python Exception
instances raised by controller routing, liaison operations, U recovery, or
result construction are converted into one matching systematic-error end before
control returns. Callback exceptions are isolated by the event delivery layer
after canonical queue delivery.

This is an in-process safety guarantee, not a crash-liveness guarantee.
KeyboardInterrupt, SystemExit, hard process death, machine loss, and canonical
event-sink failure remain external interruption classes. A sink may commit and
then raise, so the controller deliberately does not retry end emission.

Controller event packet mechanics live in the adjacent _events.py module.
"""

from typing import Callable, Mapping

from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    CONTROLLER_EVENTS_CALLBACK_KEY,
    EXPLOSION_EVENTS_CALLBACK_KEY,
)

from ._api import (
    Any,
    ControllerSessionOps,
    Dict,
    Optional,
    SystemAction,
    UIMode,
    UserAction,
    _map_event_kind,
    _normalize_for_composite_platform,
    _normalize_repeated_submit_values,
    _perform_redo,
    _perform_step,
    _perform_undo,
    controller_signal_to_engine_dict_v1,
    get_routing_map,
    normalize_controller_action_packet_v1,
    warnings,
)
from ._events import (
    ControllerEventCallback,
    ControllerEventSink,
    controller_event_callback_v1,
    emit_controller_loop_event_v1,
    new_controller_dispatch_id_v1,
    normalize_dispatcher_identity_id_v1,
    normalize_dispatcher_role_v1,
)


ControllerDispatchCallbacks = Dict[str, Optional[ControllerEventCallback]]

# Private in-process hook. It is stripped before dispatch_context is emitted.
# The hook receives (base_dispatch_context, canonical_end_U) and must return
# the finalized dead-JSON dispatch context for controller.loop.end.
_END_DISPATCH_CONTEXT_FINALIZER_KEY_V1 = (
    "__controller_end_dispatch_context_finalizer_v1__"
)
ControllerEndDispatchContextFinalizer = Callable[
    [Mapping[str, Any], Mapping[str, Any]],
    Mapping[str, Any],
]


def _split_dispatch_context_v1(
    dispatch_context: Optional[Mapping[str, Any]],
) -> tuple[
    Optional[Dict[str, Any]],
    Optional[ControllerEndDispatchContextFinalizer],
]:
    if not isinstance(dispatch_context, Mapping):
        return None, None

    out = dict(dispatch_context)
    raw_finalizer = out.pop(
        _END_DISPATCH_CONTEXT_FINALIZER_KEY_V1,
        None,
    )
    finalizer = raw_finalizer if callable(raw_finalizer) else None
    return out, finalizer


def _finalize_dispatch_context_v1(
    *,
    base_dispatch_context: Optional[Mapping[str, Any]],
    finalizer: Optional[ControllerEndDispatchContextFinalizer],
    end_U: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    if not isinstance(base_dispatch_context, Mapping):
        return None

    base = dict(base_dispatch_context)
    if not callable(finalizer):
        return base

    finalized = finalizer(base, dict(end_U))
    if not isinstance(finalized, Mapping):
        raise TypeError(
            "controller end dispatch-context finalizer must return a mapping"
        )
    return dict(finalized)


def _safe_entry_U_v1(
    session_ops: ControllerSessionOps,
    session_id: str,
) -> Dict[str, Any]:
    U = session_ops.get_session_context(session_id)
    if not isinstance(U, dict):
        raise TypeError(
            "controller session liaison get_session_context(...) "
            f"must return dict, got {type(U)!r}"
        )
    return dict(U)


def _controller_event_U_v1(
    session_ops: ControllerSessionOps,
    session_id: str,
    *,
    fallback_U: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Return the canonical unmodulated context used only for controller events.

    Public role-aware session liaisons may return a viewer-modulated context
    from their ordinary methods. They may additionally expose the most recent
    raw context through

        get_unmodulated_session_context_for_controller_event(...)

    The controller uses that raw context only for its canonical audit packet.
    Its ordinary return value remains the role-modulated context.

    Roleless/custom liaisons need not implement the optional method; for them
    the ordinary context is already canonical and is used as the fallback.

    The optional method is deliberately cache-backed by the role-aware liaison.
    It must not cause an extra engine context evaluation, datum mount, lifecycle
    transition, or event emission.
    """
    getter = getattr(
        session_ops,
        "get_unmodulated_session_context_for_controller_event",
        None,
    )

    if not callable(getter):
        return dict(fallback_U)

    U = getter(str(session_id))
    if not isinstance(U, Mapping):
        raise TypeError(
            "controller session liaison "
            "get_unmodulated_session_context_for_controller_event(...) "
            f"must return a mapping, got {type(U)!r}"
        )

    return dict(U)


def _controller_event_sink_v1(
    session_ops: ControllerSessionOps,
    session_id: str,
) -> Optional[ControllerEventSink]:
    """
    Return the optional session-queue sink for controller-loop events.

    The controller stays engine-agnostic: it does not know where the queue
    lives. A concrete liaison may expose:

        emit_controller_loop_event_to_session_v1(session_id, event)

    The event packet is already built and validated by _events.py.
    """
    sink = getattr(
        session_ops,
        "emit_controller_loop_event_to_session_v1",
        None,
    )

    if not callable(sink):
        return None

    def deliver(event: Mapping[str, Any]) -> None:
        sink(str(session_id), dict(event))

    return deliver


def normalize_controller_dispatch_callbacks_v1(
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
) -> ControllerDispatchCallbacks:
    out: ControllerDispatchCallbacks = {
        EXPLOSION_EVENTS_CALLBACK_KEY: None,
        CONTROLLER_EVENTS_CALLBACK_KEY: None,
    }

    if isinstance(threaded_callbacks, Mapping):
        for key, value in threaded_callbacks.items():
            key_s = str(key)
            out[key_s] = value if callable(value) else None

    return out


def _preflight_controller_dispatch_v1(
    session_ops: ControllerSessionOps,
    session_id: str,
    *,
    action: UserAction,
    submitted_fill: Mapping[str, Any],
    submitted_signal: Optional[Mapping[str, Any]],
) -> None:
    """
    Run an optional liaison-owned request preflight before controller start.

    This hook exists for checks that belong to the public façade liaison rather
    than to controller execution itself. The primary example is role-bound
    submission authorization: a reviewer must not be able to submit a datum
    writable only by a maker.

    A role-aware liaison may expose:

        preflight_controller_dispatch_v1(
            session_id,
            *,
            action,
            submitted_fill,
            submitted_signal,
        )

    Any exception raised by that hook is intentionally allowed to propagate.
    Because the hook runs before the start event, an authorization or request
    validation failure creates no partial controller trident.

    Roleless and custom liaisons are not required to implement the hook.
    """
    preflight = getattr(
        session_ops,
        "preflight_controller_dispatch_v1",
        None,
    )

    if not callable(preflight):
        return

    preflight(
        str(session_id),
        action=action,
        submitted_fill=dict(submitted_fill),
        submitted_signal=(
            dict(submitted_signal)
            if isinstance(submitted_signal, Mapping)
            else None
        ),
    )


def _safe_exception_message_v1(exc: Exception) -> str:
    """
    Return a boundedly safe exception message.

    An Exception subclass may itself have a broken ``__str__`` implementation.
    Error-packet construction must not become a second exception path after a
    canonical controller start has already been recorded.
    """
    try:
        return str(exc)
    except Exception:
        return "<exception message unavailable>"


def _system_error_packet_v1(exc: Exception) -> Dict[str, Any]:
    return {
        "kind": "controller_dispatch_system_error_v1",
        "exception_type": type(exc).__name__,
        "message": _safe_exception_message_v1(exc),
    }


def _dead_json_event_U_or_fallback_v1(
    candidate_U: Mapping[str, Any],
    *,
    fallback_U: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Return a dead-JSON-safe controller-event U.

    A successfully emitted start proves that ``fallback_U`` was accepted by
    the controller event builder. Recovery may inspect a newer liaison context,
    but malformed recovery state must never prevent construction of the
    systematic-error end packet.
    """
    from _thinkprogram._iomicrosTM.tiny_helpers import (
        DeadJSONError,
        assert_dead_json,
    )

    candidate = dict(candidate_U)

    try:
        assert_dead_json(candidate, path="controller_event.payload.U")
    except (DeadJSONError, TypeError, ValueError):
        return dict(fallback_U)

    return candidate


def _safe_recovery_event_U_v1(
    session_ops: ControllerSessionOps,
    session_id: str,
    *,
    fallback_U: Mapping[str, Any],
) -> Dict[str, Any]:
    try:
        recovery_U = _safe_entry_U_v1(session_ops, session_id)
        recovery_event_U = _controller_event_U_v1(
            session_ops,
            session_id,
            fallback_U=recovery_U,
        )
    except Exception:
        return dict(fallback_U)

    return _dead_json_event_U_or_fallback_v1(
        recovery_event_U,
        fallback_U=fallback_U,
    )


def dispatch_page_flow_controller_automaton(
    session_id: str,
    *,
    action: UserAction = UserAction.STEP,
    user_fill: Optional[Dict[str, Any]] = None,
    user_signal: Optional[Dict[str, Any]] = None,
    dispatcher_identity_id: str = None,
    dispatcher_role: Optional[str] = None,
    session_ops: ControllerSessionOps,
    threaded_callbacks: Optional[Dict[str, Any]] = None,
    dispatch_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run one page-flow cycle and return one bounded controller result packet.

    Identity failures
    -----------------
    Dispatcher identity normalization occurs before request normalization,
    authorization preflight, controller entry, and event delivery. A missing or
    blank dispatcher identity raises ValueError and emits no event.

    Boundary failures
    -----------------
    Request normalization and liaison-owned preflight occur before the
    controller start. Their exceptions propagate and emit no controller event.

    Controller failures
    -------------------
    Once the start packet has been committed, every ordinary ``Exception``
    produced while executing or resolving the controller is converted into:

        controller.loop.end
        payload.outcome == "system_error"

    and a bounded return packet carrying the same structured error.

    Sink failures
    -------------
    Canonical event-sink failure is outside the controller execution envelope.
    An end event is attempted exactly once. A sink exception propagates and is
    never converted into a second competing end packet.
    """
    base_dispatch_context, end_dispatch_context_finalizer = (
        _split_dispatch_context_v1(dispatch_context)
    )

    normalized_dispatcher_identity_id = (
        normalize_dispatcher_identity_id_v1(dispatcher_identity_id)
    )
    normalized_dispatcher_role = normalize_dispatcher_role_v1(
        dispatcher_role
    )

    callbacks = normalize_controller_dispatch_callbacks_v1(
        threaded_callbacks,
    )
    controller_callback = controller_event_callback_v1(
        callbacks,
        callback_key=CONTROLLER_EVENTS_CALLBACK_KEY,
    )
    controller_event_sink = _controller_event_sink_v1(
        session_ops,
        session_id,
    )
    controller_events_enabled = (
        controller_callback is not None
        or controller_event_sink is not None
    )

    if user_fill is None:
        user_fill = {}

    if not isinstance(action, UserAction):
        raise NotImplementedError(f"No handler for action={action!r}")

    if not isinstance(user_fill, dict):
        raise TypeError("user_fill must be a dict")

    if user_signal is not None and action is not UserAction.STEP:
        warnings.warn(
            "dispatch_ui_action: user_signal provided on non-STEP; "
            "ignoring signal.",
            stacklevel=2,
        )
        user_signal = None

    if user_fill and action is not UserAction.STEP:
        warnings.warn(
            "dispatch_ui_action: user_fill provided on non-STEP; "
            "ignoring fill data.",
            stacklevel=2,
        )
        user_fill = {}

    if user_fill:
        user_fill = _normalize_repeated_submit_values(user_fill)
        user_fill = _normalize_for_composite_platform(user_fill)

    action_packet = normalize_controller_action_packet_v1(
        fill=user_fill,
        signal=user_signal,
    )
    user_fill = dict(action_packet.fill)
    engine_signal = controller_signal_to_engine_dict_v1(
        action_packet.signal
    )

    submitted_fill = dict(user_fill)
    submitted_signal = (
        dict(engine_signal)
        if isinstance(engine_signal, dict)
        else None
    )

    # Identity validation deliberately precedes request authorization,
    # entry-U evaluation, dispatch-id creation, and event emission.
    _preflight_controller_dispatch_v1(
        session_ops,
        session_id,
        action=action,
        submitted_fill=submitted_fill,
        submitted_signal=submitted_signal,
    )

    dispatch_id = new_controller_dispatch_id_v1()
    entry_U: Dict[str, Any] = {}
    entry_event_U: Dict[str, Any] = {}

    if controller_events_enabled:
        entry_U = _safe_entry_U_v1(session_ops, session_id)
        entry_event_U = _controller_event_U_v1(
            session_ops,
            session_id,
            fallback_U=entry_U,
        )

        emit_controller_loop_event_v1(
            callback=controller_callback,
            event_sink=controller_event_sink,
            phase="start",
            dispatch_id=dispatch_id,
            dispatcher_identity_id=normalized_dispatcher_identity_id,
            dispatcher_role=normalized_dispatcher_role,
            session_id=session_id,
            action_name=action.name,
            U=entry_event_U,
            submitted_fill=submitted_fill,
            submitted_signal=submitted_signal,
        )

    packet: Dict[str, Any]
    end_event_U: Dict[str, Any]
    end_result: Optional[Dict[str, Any]] = None
    end_system_error: Optional[Dict[str, Any]] = None

    try:
        entry_action: UserAction | SystemAction = action
        next_action: UserAction | SystemAction = entry_action
        ctx: Dict[str, Any] | None = None
        finished = False
        at_start = False
        ui_mode: Optional[UIMode] = None

        while True:
            match next_action:
                case UserAction.STEP:
                    ctx, finished = _perform_step(
                        session_ops,
                        session_id,
                        user_fill,
                        engine_signal,
                        threaded_callbacks=callbacks,
                    )

                case UserAction.UNDO:
                    ctx, at_start = _perform_undo(
                        session_ops,
                        session_id,
                    )

                case UserAction.REDO:
                    ctx, finished = _perform_redo(
                        session_ops,
                        session_id,
                    )

                case SystemAction.KEEP_STEPPING:
                    ctx, finished = _perform_step(
                        session_ops,
                        session_id,
                        None,
                        None,
                        threaded_callbacks=callbacks,
                    )

                case SystemAction.KEEP_UNDOING:
                    ctx, at_start = _perform_undo(
                        session_ops,
                        session_id,
                    )

                case _:
                    raise NotImplementedError(
                        f"Unknown action: {next_action!r}"
                    )

            if not isinstance(ctx, dict):
                raise TypeError(
                    "Expected dict context from session liaison, "
                    f"got {type(ctx)!r}"
                )

            if at_start:
                entry_action = UserAction.STEP

            ui_config = ctx.get("session_metadata") or {}
            routing_map = get_routing_map(ui_config)
            routed = routing_map[entry_action][
                _map_event_kind(str(ctx["kind"]))
            ]

            if isinstance(routed, UIMode):
                ui_mode = routed
                break

            next_action = routed
            user_fill = {}
            engine_signal = None

        if ui_mode is None:
            raise RuntimeError(
                "internal invariant: page flow did not resolve a UIMode"
            )

        packet = {
            "session_id": str(session_id),
            "dispatcher_identity_id": normalized_dispatcher_identity_id,
            "dispatcher_role": normalized_dispatcher_role,
            "ui_mode": ui_mode.name,
            "ui_config": ctx.get("session_metadata"),
            "ctx": ctx,
            "event_kind": ctx["kind"],
            "finished": bool(finished),
            "last_error": ctx.get("last_error"),
            "system_error": None,
        }

        end_result = {
            "event_kind": packet["event_kind"],
            "ui_mode": packet["ui_mode"],
            "finished": packet["finished"],
            "last_error": packet["last_error"],
        }

        if controller_events_enabled:
            raw_end_event_U = _controller_event_U_v1(
                session_ops,
                session_id,
                fallback_U=ctx,
            )
            end_event_U = _dead_json_event_U_or_fallback_v1(
                raw_end_event_U,
                fallback_U=entry_event_U,
            )
        else:
            end_event_U = dict(ctx)

    except Exception as exc:
        end_system_error = _system_error_packet_v1(exc)
        end_event_U = _safe_recovery_event_U_v1(
            session_ops,
            session_id,
            fallback_U=entry_event_U or entry_U,
        )

        packet = {
            "session_id": str(session_id),
            "dispatcher_identity_id": normalized_dispatcher_identity_id,
            "dispatcher_role": normalized_dispatcher_role,
            "ui_mode": None,
            "ui_config": end_event_U.get("session_metadata"),
            "ctx": end_event_U,
            "event_kind": (
                "SYSTEM_ERRORED_WHEN_PROCESSING_ACTION_DISPATCH"
            ),
            "finished": False,
            "last_error": None,
            "system_error": end_system_error,
        }

    # Deliberately outside the controller execution try/except.
    #
    # Exactly one end is attempted. Canonical sink failure is not retried as a
    # competing system-error end because the sink may already have committed
    # the first packet before raising.
    if controller_events_enabled:
        finalized_dispatch_context = _finalize_dispatch_context_v1(
            base_dispatch_context=base_dispatch_context,
            finalizer=end_dispatch_context_finalizer,
            end_U=end_event_U,
        )
        emit_controller_loop_event_v1(
            callback=controller_callback,
            event_sink=controller_event_sink,
            phase="end",
            dispatch_id=dispatch_id,
            dispatcher_identity_id=normalized_dispatcher_identity_id,
            dispatcher_role=normalized_dispatcher_role,
            session_id=session_id,
            action_name=action.name,
            U=end_event_U,
            submitted_fill=submitted_fill,
            submitted_signal=submitted_signal,
            result=end_result,
            system_error=end_system_error,
            dispatch_context=finalized_dispatch_context,
        )

    return packet


__all__ = [
    "ControllerSessionOps",
    "dispatch_page_flow_controller_automaton",
]