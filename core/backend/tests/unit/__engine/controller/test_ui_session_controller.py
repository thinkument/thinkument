from __future__ import annotations

"""
UI SESSION CONTROLLER INTEGRATION SHEET
=======================================

This sheet proves the current public interactive flow:

    caller
      -> dispatch_ui_action(...)
      -> role-bound public liaison
      -> page-flow controller
      -> roleless session API

Context formalism
-----------------

The interactive boundary distinguishes two context representations:

    U_canonical
        The roleless engine/controller context.

    U_public
        The role-aware public projection released for the requesting viewer.

The flow is:

    roleless backend U_canonical
      -> controller-loop event payload.U as U_canonical
      -> transient session event queue
      -> optional controller callback

    roleless backend U_canonical
      -> public role release / modulation
      -> dispatch result U_public

Controller transition
---------------------

The controller realizes:

    (
        U_canonical_entry,
        action,
        fill,
        signal,
    )
        ->
    (
        U_canonical_final,
        public_result,
    )

where:

    U_canonical_entry
        Roleless context at controller-loop entry.

    action
        STEP | UNDO | REDO.

    fill
        Normalized user fill.

    signal
        Optional normalized datum-targeted signal.

    U_canonical_final
        Roleless context at controller-loop completion.

    public_result
        Renderer-independent public packet whose ``ctx`` is the
        viewer-specific role-released projection of
        ``U_canonical_final``.

The controller owns:

- action routing;
- automatic continuation through internal engine states;
- manual-stop detection;
- start/end recovery;
- dotted-micro fill normalization;
- signal validation and forwarding;
- callback threading;
- controller-loop event delivery;
- session event queue delivery through the role-bound liaison;
- fatal-error surfacing;
- renderer-independent result construction.

Boundary law
------------

Role-aware grammar exists only at the public interactive boundary:

    create_interactive_session(...)
    get_current_ui_state(...)
    dispatch_ui_action(...)
    render_current_ui_state(...)

The reusable session API is roleless:

    step_session(session_id, fill=..., signal=..., threaded_callbacks=...)
    undo_last_step(session_id)
    redo_last_step(session_id)
    get_session_context(session_id)
    get_outputs(session_id)

Neither ``role`` nor ``viewer_role`` may reach the roleless backend.

Controller event law
--------------------

When the role-bound liaison exposes a controller-event queue sink, every
successful dispatch records exactly two controller-loop events into the
session-local transient event queue:

    controller.loop.start
    controller.loop.end

When a controller callback is also installed, those same events are forwarded
synchronously to the callback after queue delivery.

Both events:

- have kind ``controller_loop_event_v1``;
- share one dispatch identifier;
- have distinct event identifiers;
- are appended to the transient session event queue;
- are delivered to the selected callback when supplied;
- carry canonical, roleless controller contexts.

The transient session event queue is not durable engine state. It is not part of
snapshots, outputs, runtime writes, lifecycle rows, or persistence.

The start event contains:

- canonical controller-entry context ``U_canonical_entry``;
- normalized fill;
- normalized signal;
- a timestamp.

The end event contains:

- canonical controller-final context ``U_canonical_final``;
- normalized fill;
- normalized signal;
- a compact identity projection of the public result;
- a timestamp.

The end-event context is intentionally not required to equal
``public_result["ctx"]``. The latter is a viewer-specific role-released
projection and may contain normalized public-boundary metadata and
role-modulation bookkeeping absent from canonical event storage.

The callback remains present in the normalized per-dispatch callback bag
passed through STEP. The roleless backend need not interpret it.

Metadata-pocket law
-------------------

Apps may register validated session-metadata pockets. The controller remains
generic:

- registered pockets are validated by the metadata surface;
- valid pockets remain inside ``ctx["session_metadata"]``;
- pocket values never become backend method arguments;
- registering app pockets does not weaken core role validation.

App-authored pockets remain present in both the canonical context and its
public projection. Public-boundary normalization may add other metadata keys
to the public projection without mutating the canonical context.

This sheet intentionally tests public contracts only. It does not discover,
patch, or depend on private role-modulation helpers.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

import pytest

from __exceptions.engine import (
    FatalEngineError,
    ProgramEndReachedError,
    ProgramStartReachedError,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    UserAction,
)
from _thinksessions.sesh_metadata.sesh_metadata_surface import (
    SessionMetadataSurfaceRegistry,
    coerce_session_metadata,
    session_args_metadata_surface_sheet_v1,
)


ScriptItem = Union[Dict[str, Any], Exception]
Call = Tuple[str, Tuple[Any, ...], Dict[str, Any]]

CONTROLLER_EVENT_KIND = "controller_loop_event_v1"
DATUM_EVENT_KIND = "datum_lifecycle_event_v1"
CONTROLLER_START_EVENT = "controller.loop.start"
CONTROLLER_END_EVENT = "controller.loop.end"


def role_metadata(*roles: str) -> Dict[str, Any]:
    return {
        "roles": {
            role: {
                "test_role": role,
            }
            for role in roles
        },
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                role: "redacted"
                for role in roles
            },
        },
    }


def grading_pocket_schema() -> Dict[str, Any]:
    return {
        "kind": "session_metadata_pocket_schema_v1",
        "label": "Grading",
        "description": "App-owned metadata for grading workflows.",
        "fields": {
            "rubric_id": {
                "type": "string",
                "required": True,
            },
            "grader_role": {
                "type": "string",
                "required": True,
            },
            "max_score": {
                "type": "number",
                "required": False,
                "default": 100,
            },
            "settings": {
                "type": "object",
                "required": False,
                "fields": {
                    "allow_revision": {
                        "type": "boolean",
                        "required": True,
                    },
                    "visibility": {
                        "type": "string",
                        "required": True,
                        "enum": ["private", "team", "public"],
                    },
                },
                "additional_keys": False,
            },
        },
        "additional_keys": False,
        "examples": [
            {
                "rubric_id": "rubric.v1",
                "grader_role": "reviewer",
                "max_score": 100,
                "settings": {
                    "allow_revision": True,
                    "visibility": "team",
                },
            }
        ],
        "laws": [
            "grading metadata is app-owned",
            "the controller does not interpret grading metadata",
            "registered grading metadata is validated at the public boundary",
        ],
    }


def workflow_pocket_schema() -> Dict[str, Any]:
    return {
        "kind": "session_metadata_pocket_schema_v1",
        "label": "Workflow",
        "fields": {
            "workflow_id": {
                "type": "string",
                "required": True,
            },
            "phase": {
                "type": "string",
                "required": True,
                "enum": ["draft", "review", "done"],
            },
        },
        "additional_keys": False,
    }


def role_metadata_with_grading_pocket(*roles: str) -> Dict[str, Any]:
    metadata = role_metadata(*roles)
    metadata["grading"] = {
        "rubric_id": "rubric.controller.v1",
        "grader_role": roles[-1] if roles else "reviewer",
        "max_score": 100,
        "settings": {
            "allow_revision": True,
            "visibility": "team",
        },
    }
    return metadata


def role_metadata_with_two_app_pockets(*roles: str) -> Dict[str, Any]:
    metadata = role_metadata_with_grading_pocket(*roles)
    metadata["workflow"] = {
        "workflow_id": "wf.controller.e2e",
        "phase": "review",
    }
    return metadata


def ctx(
    kind: str,
    *,
    meta: Optional[Mapping[str, Any]] = None,
    last_error: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "kind": kind,
        "session_metadata": deepcopy(dict(meta or {})),
        "last_error": (
            deepcopy(dict(last_error))
            if last_error is not None
            else None
        ),
        "globals": {},
        "datum_widgets_on_this_span": [],
        "datum_widget_decls": {},
        "datum_widget_fills": {},
        "span_to_datum_widgets": {},
        "span_order": [],
        "frames": [],
        "cursor": f"CURSOR.{kind}",
    }


@dataclass
class ScriptedSessionAPI:
    """
    Scriptable roleless session API.

    The method signatures intentionally contain no role-aware arguments.

    The queue methods model the latest concrete session event surface:

        record_session_event(session_id, event)
            Generic transient queue append used by controller-loop events.

        get_session_events(session_id, limit=None)
            Non-destructive queue inspection.

        drain_session_events(session_id)
            Destructive queue drain.

    Datum lifecycle events emitted by this scripted backend are also recorded
    into the same transient queue before callback delivery, mirroring the real
    engine event delivery order.
    """

    initial_ctx: Dict[str, Any]
    step_script: List[ScriptItem] = field(default_factory=list)
    undo_script: List[ScriptItem] = field(default_factory=list)
    redo_script: List[ScriptItem] = field(default_factory=list)
    explosion_events: List[Dict[str, Any]] = field(default_factory=list)
    context_after_end: Optional[Dict[str, Any]] = None
    context_after_start: Optional[Dict[str, Any]] = None

    calls: List[Call] = field(default_factory=list)
    session_event_queue: List[Dict[str, Any]] = field(default_factory=list)

    _end_reached: bool = False
    _start_reached: bool = False

    def _record_event_queue_only(
        self,
        event: Mapping[str, Any],
    ) -> Dict[str, Any]:
        ev = deepcopy(dict(event))
        self.session_event_queue.append(ev)
        return deepcopy(ev)

    def create_VM_session(
        self,
        **kwargs: Any,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        self.calls.append(
            (
                "create_VM_session",
                (),
                deepcopy(dict(kwargs)),
            )
        )
        return {"session_id": "S1"}, {}

    def step_session(
        self,
        session_id: str,
        fill: Optional[Dict[str, Any]] = None,
        signal: Optional[Dict[str, Any]] = None,
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        callback_bag = dict(threaded_callbacks or {})

        self.calls.append(
            (
                "step_session",
                (session_id,),
                {
                    "fill": deepcopy(fill),
                    "signal": deepcopy(signal),
                    "threaded_callbacks": callback_bag,
                },
            )
        )

        explosion_callback = callback_bag.get(
            "explosion_events_callback"
        )
        for event in self.explosion_events:
            self._record_event_queue_only(event)
            if callable(explosion_callback):
                explosion_callback(deepcopy(event))

        if not self.step_script:
            return deepcopy(self.initial_ctx)

        item = self.step_script.pop(0)
        if isinstance(item, Exception):
            if isinstance(item, ProgramEndReachedError):
                self._end_reached = True
            raise item

        return deepcopy(item)

    def undo_last_step(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        self.calls.append(
            (
                "undo_last_step",
                (session_id,),
                {},
            )
        )

        if not self.undo_script:
            return deepcopy(self.initial_ctx)

        item = self.undo_script.pop(0)
        if isinstance(item, Exception):
            if isinstance(item, ProgramStartReachedError):
                self._start_reached = True
            raise item

        return deepcopy(item)

    def redo_last_step(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        self.calls.append(
            (
                "redo_last_step",
                (session_id,),
                {},
            )
        )

        if not self.redo_script:
            return deepcopy(self.initial_ctx)

        item = self.redo_script.pop(0)
        if isinstance(item, Exception):
            raise item

        return deepcopy(item)

    def get_session_context(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        self.calls.append(
            (
                "get_session_context",
                (session_id,),
                {},
            )
        )

        if (
            self._end_reached
            and self.context_after_end is not None
        ):
            return deepcopy(self.context_after_end)

        if (
            self._start_reached
            and self.context_after_start is not None
        ):
            return deepcopy(self.context_after_start)

        return deepcopy(self.initial_ctx)

    def get_outputs(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        self.calls.append(
            (
                "get_outputs",
                (session_id,),
                {},
            )
        )
        return {"ok": True}

    def record_session_event(
        self,
        session_id: str,
        event: Mapping[str, Any],
    ) -> Dict[str, Any]:
        self.calls.append(
            (
                "record_session_event",
                (session_id, deepcopy(dict(event))),
                {},
            )
        )
        return self._record_event_queue_only(event)

    def get_session_events(
        self,
        session_id: str,
        *,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self.calls.append(
            (
                "get_session_events",
                (session_id,),
                {"limit": limit},
            )
        )

        events = list(self.session_event_queue)

        if limit is None:
            return [deepcopy(event) for event in events]

        k = int(limit)
        if k <= 0:
            return []

        return [deepcopy(event) for event in events[-k:]]

    def drain_session_events(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        self.calls.append(
            (
                "drain_session_events",
                (session_id,),
                {},
            )
        )
        events = [deepcopy(event) for event in self.session_event_queue]
        self.session_event_queue.clear()
        return events


@dataclass
class SimpleBackendSlot:
    backend: Optional[ScriptedSessionAPI] = None


@pytest.fixture()
def controller_boundary(monkeypatch):
    from _thinkengine.runme import (
        runme_interactive_w_controller_rolemodulator as session_api,
    )

    backend_slot = SimpleBackendSlot()

    def get_backend() -> ScriptedSessionAPI:
        assert backend_slot.backend is not None, (
            "test must install ScriptedSessionAPI before dispatch"
        )
        return backend_slot.backend

    monkeypatch.setattr(
        session_api,
        "get_concrete_session_api",
        get_backend,
        raising=True,
    )

    return {
        "dispatch": session_api.dispatch_ui_action,
        "backend_slot": backend_slot,
    }


@pytest.fixture()
def clean_session_metadata_pocket_registry():
    SessionMetadataSurfaceRegistry.clear_registered_pockets_for_tests()
    yield
    SessionMetadataSurfaceRegistry.clear_registered_pockets_for_tests()


def install_backend(
    boundary: Mapping[str, Any],
    backend: ScriptedSessionAPI,
) -> None:
    slot = boundary["backend_slot"]
    assert isinstance(slot, SimpleBackendSlot)
    slot.backend = backend


def call_names(
    backend: ScriptedSessionAPI,
) -> List[str]:
    return [
        name
        for name, _, _ in backend.calls
    ]


def calls_named(
    backend: ScriptedSessionAPI,
    name: str,
) -> List[Call]:
    return [
        call
        for call in backend.calls
        if call[0] == name
    ]


def last_call(
    backend: ScriptedSessionAPI,
    name: str,
) -> Call:
    matches = calls_named(backend, name)

    if not matches:
        raise AssertionError(
            f"No {name!r} call found in {backend.calls!r}"
        )

    return matches[-1]


def controller_events_only(
    events: List[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        deepcopy(dict(event))
        for event in events
        if event.get("kind") == CONTROLLER_EVENT_KIND
    ]


def datum_events_only(
    events: List[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        deepcopy(dict(event))
        for event in events
        if event.get("kind") == DATUM_EVENT_KIND
    ]


def event_ids(
    events: List[Mapping[str, Any]],
) -> List[str]:
    return [
        str(event["event_id"])
        for event in events
    ]


def assert_roleless_backend(
    backend: ScriptedSessionAPI,
) -> None:
    for method_name, _, kwargs in backend.calls:
        assert "role" not in kwargs, (
            f"{method_name!r} received forbidden role kwarg: "
            f"{kwargs!r}"
        )
        assert "viewer_role" not in kwargs, (
            f"{method_name!r} received forbidden viewer_role "
            f"kwarg: {kwargs!r}"
        )


def assert_no_app_pocket_kwargs(
    backend: ScriptedSessionAPI,
    *pocket_names: str,
) -> None:
    for method_name, _, kwargs in backend.calls:
        for pocket_name in pocket_names:
            assert pocket_name not in kwargs, (
                f"{method_name!r} received forbidden app-pocket "
                f"kwarg {pocket_name!r}: {kwargs!r}"
            )


def assert_manual_fill_result(
    result: Mapping[str, Any],
) -> None:
    assert result["ui_mode"] == "FORM_FILL"
    assert result["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert result["finished"] is False


def assert_controller_event_pair(
    events: List[Mapping[str, Any]],
    *,
    session_id: str,
    action: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    controller_events = controller_events_only(events)
    assert len(controller_events) == 2

    start_event, end_event = controller_events

    assert start_event["kind"] == CONTROLLER_EVENT_KIND
    assert end_event["kind"] == CONTROLLER_EVENT_KIND

    assert start_event["source"] == "page_flow_controller"
    assert end_event["source"] == "page_flow_controller"

    assert start_event["name"] == CONTROLLER_START_EVENT
    assert end_event["name"] == CONTROLLER_END_EVENT

    assert start_event["phase"] == "start"
    assert end_event["phase"] == "end"

    assert start_event["session_id"] == session_id
    assert end_event["session_id"] == session_id

    assert start_event["action"] == action
    assert end_event["action"] == action

    assert start_event["dispatch_id"]
    assert (
        start_event["dispatch_id"]
        == end_event["dispatch_id"]
    )

    assert start_event["event_id"]
    assert end_event["event_id"]
    assert (
        start_event["event_id"]
        != end_event["event_id"]
    )

    assert start_event["emitted_at"]
    assert end_event["emitted_at"]

    start_payload = start_event["payload"]
    end_payload = end_event["payload"]

    assert start_payload["timestamp"] == start_event["emitted_at"]
    assert end_payload["timestamp"] == end_event["emitted_at"]

    assert isinstance(
        start_payload["U"],
        Mapping,
    )
    assert isinstance(
        end_payload["U"],
        Mapping,
    )

    assert "result" not in start_payload
    assert "error" not in start_payload

    assert isinstance(
        end_payload.get("result"),
        Mapping,
    )

    return start_event, end_event


def assert_queue_and_callback_controller_events_match(
    *,
    queue_events: List[Mapping[str, Any]],
    callback_events: List[Mapping[str, Any]],
) -> None:
    queue_controller = controller_events_only(queue_events)
    callback_controller = controller_events_only(callback_events)

    assert event_ids(queue_controller) == event_ids(callback_controller)
    assert [
        event["dispatch_id"]
        for event in queue_controller
    ] == [
        event["dispatch_id"]
        for event in callback_controller
    ]


def assert_canonical_controller_context(
    actual_ctx: Mapping[str, Any],
    source_ctx: Mapping[str, Any],
) -> None:
    """
    Assert that a controller event carries the canonical roleless context.

    Controller-loop events are part of the canonical event/storage path.
    Their U must therefore equal the roleless backend context rather than the
    viewer-specific public context returned by ``dispatch_ui_action``.
    """
    assert actual_ctx == source_ctx


def assert_public_context_projects_canonical_context(
    public_ctx: Mapping[str, Any],
    canonical_ctx: Mapping[str, Any],
) -> None:
    """
    Assert that a public role-released context preserves canonical content.

    Public release may add normalized metadata defaults, role assignments,
    and role-mismatch modulation bookkeeping. Consequently the public context
    is not required to equal the canonical backend/controller context
    byte-for-byte.
    """
    assert public_ctx["kind"] == canonical_ctx["kind"]
    assert public_ctx["cursor"] == canonical_ctx["cursor"]

    public_metadata = public_ctx.get(
        "session_metadata",
        {},
    )
    canonical_metadata = canonical_ctx.get(
        "session_metadata",
        {},
    )

    assert isinstance(public_metadata, Mapping)
    assert isinstance(canonical_metadata, Mapping)

    for key, value in canonical_metadata.items():
        assert public_metadata.get(key) == value

    for key in (
        "last_error",
        "globals",
        "datum_widgets_on_this_span",
        "datum_widget_decls",
        "datum_widget_fills",
        "span_to_datum_widgets",
        "span_order",
        "frames",
    ):
        assert public_ctx.get(key) == canonical_ctx.get(key)


def assert_controller_result_projection(
    event_result: Mapping[str, Any],
    public_result: Mapping[str, Any],
) -> None:
    """
    Assert the stable event-safe projection of a public dispatch result.

    Controller events identify the terminal public state without duplicating
    the complete public packet.
    """
    assert event_result["event_kind"] == public_result["event_kind"]
    assert event_result["ui_mode"] == public_result["ui_mode"]
    assert event_result["finished"] == public_result["finished"]


def test_step_routes_through_public_boundary_into_roleless_backend(
    controller_boundary,
):
    metadata = role_metadata("reviewer")

    backend = ScriptedSessionAPI(
        initial_ctx=ctx(
            "STEPFNSTEP",
            meta=metadata,
        ),
        step_script=[
            ctx(
                "MANUALFILLNEEDEDSTEP",
                meta=metadata,
            )
        ],
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        role="reviewer",
        render=False,
    )

    step = last_call(backend, "step_session")

    assert step[1] == ("S1",)
    assert step[2]["fill"] == {}
    assert step[2]["signal"] is None
    assert set(step[2]["threaded_callbacks"]) >= {
        "explosion_events_callback",
        "controller_events_callback",
    }

    assert_controller_event_pair(
        backend.session_event_queue,
        session_id="S1",
        action="STEP",
    )
    assert_roleless_backend(backend)
    assert_manual_fill_result(result)


def test_step_without_role_uses_same_roleless_backend_contract(
    controller_boundary,
):
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART"),
        step_script=[ctx("MANUALFILLNEEDEDSTEP")],
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        render=False,
    )

    assert len(calls_named(backend, "step_session")) == 1
    assert_controller_event_pair(
        backend.session_event_queue,
        session_id="S1",
        action="STEP",
    )
    assert_roleless_backend(backend)
    assert_manual_fill_result(result)


@pytest.mark.parametrize(
    ("submitted_fill", "expected_fill"),
    [
        (
            {"NAME.first": "Ada", "NAME.last": "Lovelace"},
            {"NAME": {"first": "Ada", "last": "Lovelace"}},
        ),
        (
            {"DOB": {"day": "01", "month": "12", "year": "1999"}},
            {"DOB": {"day": "01", "month": "12", "year": "1999"}},
        ),
        (
            {"DOB": "discarded scalar", "DOB.day": "01"},
            {"DOB": {"day": "01"}},
        ),
    ],
)
def test_step_normalizes_fill_before_backend_dispatch(
    controller_boundary,
    submitted_fill,
    expected_fill,
):
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("MANUALFILLNEEDEDSTEP"),
        step_script=[ctx("MANUALFILLNEEDEDSTEP")],
    )
    install_backend(controller_boundary, backend)

    controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        user_fill=submitted_fill,
        render=False,
    )

    step = last_call(backend, "step_session")
    assert step[2]["fill"] == expected_fill
    assert step[2]["signal"] is None


def test_keep_stepping_uses_none_fill_for_internal_continuation(
    controller_boundary,
):
    metadata = role_metadata("maker")

    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART", meta=metadata),
        step_script=[
            ctx("STEPFNSTEP", meta=metadata),
            ctx("MANUALFILLNEEDEDSTEP", meta=metadata),
        ],
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        role="maker",
        render=False,
    )

    step_calls = calls_named(backend, "step_session")
    assert len(step_calls) == 2
    assert [call[2]["fill"] for call in step_calls] == [{}, None]
    assert [call[2]["signal"] for call in step_calls] == [None, None]

    assert_controller_event_pair(
        backend.session_event_queue,
        session_id="S1",
        action="STEP",
    )
    assert_roleless_backend(backend)
    assert_manual_fill_result(result)


@pytest.mark.parametrize(
    ("action", "backend_method"),
    [
        (UserAction.UNDO, "undo_last_step"),
        (UserAction.REDO, "redo_last_step"),
    ],
)
def test_undo_and_redo_ignore_submitted_fill(
    controller_boundary,
    action,
    backend_method,
):
    metadata = role_metadata("reviewer")

    backend = ScriptedSessionAPI(
        initial_ctx=ctx("MANUALFILLNEEDEDSTEP", meta=metadata),
        undo_script=[ctx("MANUALFILLNEEDEDSTEP", meta=metadata)],
        redo_script=[ctx("MANUALFILLNEEDEDSTEP", meta=metadata)],
    )
    install_backend(controller_boundary, backend)

    with pytest.warns(UserWarning):
        result = controller_boundary["dispatch"](
            "S1",
            action=action,
            user_fill={"IGNORED.value": "x"},
            role="reviewer",
            render=False,
        )

    assert len(calls_named(backend, backend_method)) == 1
    assert last_call(backend, backend_method)[2] == {}
    assert calls_named(backend, "step_session") == []
    assert_controller_event_pair(
        backend.session_event_queue,
        session_id="S1",
        action=action.name,
    )
    assert_roleless_backend(backend)
    assert_manual_fill_result(result)


def test_program_end_recovery_returns_completion_packet(
    controller_boundary,
):
    metadata = role_metadata("reviewer")
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("STEPFNSTEP", meta=metadata),
        step_script=[ProgramEndReachedError("done")],
        context_after_end=ctx("ATCOMPLETION", meta=metadata),
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        role="reviewer",
        render=False,
    )

    assert len(calls_named(backend, "step_session")) == 1
    assert len(calls_named(backend, "get_session_context")) >= 1
    assert result["ui_mode"] == "RUN_COMPLETED_SUMMARY"
    assert result["event_kind"] == "ATCOMPLETION"
    assert result["finished"] is True
    assert_controller_event_pair(
        backend.session_event_queue,
        session_id="S1",
        action="STEP",
    )
    assert_roleless_backend(backend)


def test_program_start_recovery_auto_advances_with_none_fill(
    controller_boundary,
):
    metadata = role_metadata("reviewer")
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("STEPFNSTEP", meta=metadata),
        undo_script=[ProgramStartReachedError("at start")],
        context_after_start=ctx("ATSTART", meta=metadata),
        step_script=[ctx("MANUALFILLNEEDEDSTEP", meta=metadata)],
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.UNDO,
        role="reviewer",
        render=False,
    )

    assert len(calls_named(backend, "undo_last_step")) == 1
    continuation = last_call(backend, "step_session")
    assert continuation[2]["fill"] is None
    assert continuation[2]["signal"] is None
    assert_controller_event_pair(
        backend.session_event_queue,
        session_id="S1",
        action="UNDO",
    )
    assert_roleless_backend(backend)
    assert_manual_fill_result(result)



def test_fatal_engine_error_is_bounded_as_system_error(
    controller_boundary,
):
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("STEPFNSTEP"),
        step_script=[FatalEngineError("boom")],
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        render=False,
    )

    result_comparison = {
        "session_id": "S1",
        "ui_mode": None,
        "ui_config": {},
        "ctx": ctx("STEPFNSTEP"),
        "event_kind": (
            "SYSTEM_ERRORED_WHEN_PROCESSING_ACTION_DISPATCH"
        ),
        "finished": False,
        "last_error": None,
        "system_error": {
            "kind": "controller_dispatch_system_error_v1",
            "exception_type": "FatalEngineError",
            "message": "boom",
        },
    }

    for k in result: 
        if k in result_comparison:
            assert result[k] == result_comparison[k], (
                f"Mismatch on key {k!r}: "
                f"expected {result_comparison[k]!r}, "
                f"got {result[k]!r}"
            )

    assert len(calls_named(backend, "step_session")) == 1

    controller_events = controller_events_only(
        backend.session_event_queue
    )
    assert len(controller_events) == 2

    start_event, end_event = controller_events

    assert start_event["kind"] == CONTROLLER_EVENT_KIND
    assert start_event["name"] == CONTROLLER_START_EVENT
    assert start_event["phase"] == "start"
    assert start_event["session_id"] == "S1"
    assert start_event["action"] == "STEP"
    assert start_event["dispatch_id"]
    assert start_event["event_id"]
    assert start_event["emitted_at"]

    assert start_event["payload"]["U"] == ctx("STEPFNSTEP")
    assert start_event["payload"]["fill"] == {}
    assert start_event["payload"]["signal"] is None
    assert (
        start_event["payload"]["timestamp"]
        == start_event["emitted_at"]
    )
    assert "outcome" not in start_event["payload"]
    assert "result" not in start_event["payload"]
    assert "system_error" not in start_event["payload"]

    assert end_event["kind"] == CONTROLLER_EVENT_KIND
    assert end_event["name"] == CONTROLLER_END_EVENT
    assert end_event["phase"] == "end"
    assert end_event["session_id"] == "S1"
    assert end_event["action"] == "STEP"
    assert end_event["dispatch_id"] == start_event["dispatch_id"]
    assert end_event["event_id"]
    assert end_event["event_id"] != start_event["event_id"]
    assert end_event["emitted_at"]

    assert end_event["payload"]["U"] == ctx("STEPFNSTEP")
    assert end_event["payload"]["fill"] == {}
    assert end_event["payload"]["signal"] is None
    assert (
        end_event["payload"]["timestamp"]
        == end_event["emitted_at"]
    )
    assert end_event["payload"]["outcome"] == "system_error"
    assert end_event["payload"]["system_error"] == result["system_error"]
    assert "result" not in end_event["payload"]

    assert_roleless_backend(backend)



def test_step_forwards_valid_datum_signal(
    controller_boundary,
):
    signal = {
        "datum_id": "D",
        "kind": "refresh",
        "info": {"reason": "controller-test"},
    }
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("MANUALFILLNEEDEDSTEP"),
        step_script=[ctx("MANUALFILLNEEDEDSTEP")],
    )
    install_backend(controller_boundary, backend)

    controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        user_fill={"D.value": "Ada"},
        user_signal=signal,
        render=False,
    )

    step = last_call(backend, "step_session")
    assert step[2]["fill"] == {"D": {"value": "Ada"}}
    assert step[2]["signal"] == signal


def test_invalid_signal_is_rejected_before_step_or_event_emission(
    controller_boundary,
):
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("MANUALFILLNEEDEDSTEP"),
        step_script=[ctx("MANUALFILLNEEDEDSTEP")],
    )
    install_backend(controller_boundary, backend)

    with pytest.raises(Exception, match="datum_id|signal|Invalid fill"):
        controller_boundary["dispatch"](
            "S1",
            action=UserAction.STEP,
            user_signal={"kind": "refresh"},
            render=False,
        )

    assert calls_named(backend, "step_session") == []
    assert calls_named(backend, "record_session_event") == []
    assert backend.session_event_queue == []


def test_explosion_callback_is_threaded_to_roleless_step_and_shared_queue(
    controller_boundary,
):
    datum_event = {
        "kind": "datum_lifecycle_event_v1",
        "event_id": "datum-event-1",
        "emitted_at": "2026-01-01T00:00:00Z",
        "source": "datum_widget_result",
        "name": "datum.reexploded",
        "form_id": "FORM",
        "frame_id": "FRAME",
        "span_id": "SPAN",
        "datum_id": "D",
        "signal_kind": "fill",
        "payload": {"phase": "reexplode"},
    }
    emitted: List[Dict[str, Any]] = []
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("MANUALFILLNEEDEDSTEP"),
        step_script=[ctx("MANUALFILLNEEDEDSTEP")],
        explosion_events=[datum_event],
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        user_fill={"D.value": "Ada"},
        render=False,
        threaded_callbacks={"explosion_events_callback": emitted.append},
    )

    assert emitted == [datum_event]
    callback_bag = last_call(backend, "step_session")[2]["threaded_callbacks"]
    assert callable(callback_bag["explosion_events_callback"])

    queue_names = [
        event["name"]
        for event in backend.session_event_queue
    ]
    assert queue_names == [
        CONTROLLER_START_EVENT,
        "datum.reexploded",
        CONTROLLER_END_EVENT,
    ]
    assert datum_events_only(backend.session_event_queue) == [datum_event]

    assert_manual_fill_result(result)


def test_controller_callback_receives_start_and_end_events(
    controller_boundary,
):
    metadata = role_metadata("reviewer")

    entry_ctx = ctx("ATSTART", meta=metadata)
    final_ctx = ctx("MANUALFILLNEEDEDSTEP", meta=metadata)

    controller_events: List[Dict[str, Any]] = []

    backend = ScriptedSessionAPI(
        initial_ctx=entry_ctx,
        step_script=[final_ctx],
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        user_fill={"D.value": "Ada"},
        user_signal={"datum_id": "D", "kind": "refresh"},
        role="reviewer",
        render=False,
        threaded_callbacks={
            "controller_events_callback": controller_events.append,
        },
    )

    start_event, end_event = assert_controller_event_pair(
        controller_events,
        session_id="S1",
        action="STEP",
    )

    queue_start, queue_end = assert_controller_event_pair(
        backend.session_event_queue,
        session_id="S1",
        action="STEP",
    )
    assert [queue_start["event_id"], queue_end["event_id"]] == [
        start_event["event_id"],
        end_event["event_id"],
    ]

    expected_fill = {"D": {"value": "Ada"}}
    expected_signal = {
        "datum_id": "D",
        "kind": "refresh",
        "info": {},
    }

    start_payload = start_event["payload"]
    end_payload = end_event["payload"]

    assert_canonical_controller_context(start_payload["U"], entry_ctx)
    assert_canonical_controller_context(end_payload["U"], final_ctx)

    assert start_payload["fill"] == expected_fill
    assert start_payload["signal"] == expected_signal
    assert "result" not in start_payload
    assert "error" not in start_payload

    assert end_payload["fill"] == expected_fill
    assert end_payload["signal"] == expected_signal
    assert "error" not in end_payload

    assert_public_context_projects_canonical_context(result["ctx"], final_ctx)
    assert_controller_result_projection(end_payload["result"], result)

    assert end_payload["U"] != result["ctx"]
    assert "role_assignments" not in end_payload["U"]
    assert "role_mismatch_modulation_info" not in end_payload["U"]
    assert result["ctx"]["role_assignments"] == []
    assert (
        result["ctx"]["role_mismatch_modulation_info"]["role_viewing"]
        == "reviewer"
    )

    assert_roleless_backend(backend)


def test_controller_event_context_is_canonical_and_public_ctx_is_released(
    controller_boundary,
):
    metadata = role_metadata("reviewer")

    entry_ctx = ctx("ATSTART", meta=metadata)
    final_ctx = ctx("MANUALFILLNEEDEDSTEP", meta=metadata)

    controller_events: List[Dict[str, Any]] = []

    backend = ScriptedSessionAPI(
        initial_ctx=entry_ctx,
        step_script=[final_ctx],
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        role="reviewer",
        render=False,
        threaded_callbacks={
            "controller_events_callback": controller_events.append,
        },
    )

    start_event, end_event = assert_controller_event_pair(
        controller_events,
        session_id="S1",
        action="STEP",
    )

    assert_queue_and_callback_controller_events_match(
        queue_events=backend.session_event_queue,
        callback_events=controller_events,
    )

    canonical_entry_U = start_event["payload"]["U"]
    canonical_final_U = end_event["payload"]["U"]
    public_final_U = result["ctx"]

    assert canonical_entry_U == entry_ctx
    assert canonical_final_U == final_ctx

    assert_public_context_projects_canonical_context(
        public_final_U,
        canonical_final_U,
    )

    assert canonical_final_U != public_final_U

    assert "manual_io" not in canonical_final_U["session_metadata"]
    assert "session_storage" not in canonical_final_U["session_metadata"]
    assert "manual_io" in public_final_U["session_metadata"]
    assert "session_storage" in public_final_U["session_metadata"]

    assert "role_assignments" not in canonical_final_U
    assert "role_mismatch_modulation_info" not in canonical_final_U
    assert public_final_U["role_assignments"] == []
    assert (
        public_final_U["role_mismatch_modulation_info"]["role_viewing"]
        == "reviewer"
    )

    assert final_ctx == ctx("MANUALFILLNEEDEDSTEP", meta=metadata)
    assert_roleless_backend(backend)


def test_controller_events_are_queued_even_without_callback(
    controller_boundary,
):
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART"),
        step_script=[ctx("MANUALFILLNEEDEDSTEP")],
    )
    install_backend(controller_boundary, backend)

    controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        render=False,
    )

    assert_controller_event_pair(
        backend.session_event_queue,
        session_id="S1",
        action="STEP",
    )
    assert calls_named(backend, "record_session_event")
    assert_roleless_backend(backend)


@pytest.mark.parametrize(
    ("action", "action_name"),
    [
        (UserAction.STEP, "STEP"),
        (UserAction.UNDO, "UNDO"),
        (UserAction.REDO, "REDO"),
    ],
)
def test_every_public_action_emits_one_controller_event_pair(
    controller_boundary,
    action,
    action_name,
):
    events: List[Dict[str, Any]] = []
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("MANUALFILLNEEDEDSTEP"),
        step_script=[ctx("MANUALFILLNEEDEDSTEP")],
        undo_script=[ctx("MANUALFILLNEEDEDSTEP")],
        redo_script=[ctx("MANUALFILLNEEDEDSTEP")],
    )
    install_backend(controller_boundary, backend)

    controller_boundary["dispatch"](
        "S1",
        action=action,
        render=False,
        threaded_callbacks={"controller_events_callback": events.append},
    )

    assert_controller_event_pair(events, session_id="S1", action=action_name)
    assert_controller_event_pair(
        backend.session_event_queue,
        session_id="S1",
        action=action_name,
    )
    assert_queue_and_callback_controller_events_match(
        queue_events=backend.session_event_queue,
        callback_events=events,
    )


def test_threaded_controller_callback_is_used_when_explicit_callback_is_absent(
    controller_boundary,
):
    threaded_events: List[Dict[str, Any]] = []
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART"),
        step_script=[ctx("MANUALFILLNEEDEDSTEP")],
    )
    install_backend(controller_boundary, backend)

    controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        render=False,
        threaded_callbacks={
            "controller_events_callback": threaded_events.append,
        },
    )

    assert_controller_event_pair(
        threaded_events,
        session_id="S1",
        action="STEP",
    )
    assert_queue_and_callback_controller_events_match(
        queue_events=backend.session_event_queue,
        callback_events=threaded_events,
    )


def test_controller_callback_exception_is_isolated_after_queue_recording(
    controller_boundary,
):
    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART"),
        step_script=[ctx("MANUALFILLNEEDEDSTEP")],
    )
    install_backend(controller_boundary, backend)

    callback_calls: List[str] = []

    def rejecting_callback(event: Mapping[str, Any]) -> None:
        callback_calls.append(str(event["name"]))
        raise RuntimeError(f"rejected {event['name']}")

    with pytest.warns(
        RuntimeWarning,
        match="controller event callback raised and was isolated",
    ):
        result = controller_boundary["dispatch"](
            "S1",
            action=UserAction.STEP,
            render=False,
            threaded_callbacks={
                "controller_events_callback": rejecting_callback,
            },
        )

    assert_manual_fill_result(result)
    assert result["system_error"] is None

    assert len(calls_named(backend, "step_session")) == 1

    start_event, end_event = assert_controller_event_pair(
        backend.session_event_queue,
        session_id="S1",
        action="STEP",
    )
    assert start_event["payload"].get("outcome") is None
    assert end_event["payload"]["outcome"] == "success"

    assert callback_calls == [
        CONTROLLER_START_EVENT,
        CONTROLLER_END_EVENT,
    ]

def test_controller_events_can_fan_out_to_downstream_consumers(
    controller_boundary,
):
    database_sink: List[Dict[str, Any]] = []
    ui_sink: List[Dict[str, Any]] = []
    service_sink: List[Dict[str, Any]] = []

    def fanout(event: Dict[str, Any]) -> None:
        database_sink.append(deepcopy(event))
        ui_sink.append(deepcopy(event))
        service_sink.append(deepcopy(event))

    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART"),
        step_script=[ctx("MANUALFILLNEEDEDSTEP")],
    )
    install_backend(controller_boundary, backend)

    controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        render=False,
        threaded_callbacks={"controller_events_callback": fanout},
    )

    assert len(database_sink) == 2
    assert database_sink == ui_sink == service_sink
    assert [event["name"] for event in database_sink] == [
        CONTROLLER_START_EVENT,
        CONTROLLER_END_EVENT,
    ]
    assert_queue_and_callback_controller_events_match(
        queue_events=backend.session_event_queue,
        callback_events=database_sink,
    )


def test_controller_callback_remains_in_normalized_threaded_callback_bag(
    controller_boundary,
):
    """
    The normalized callback mapping is the common dispatch artery.

    The controller consumes ``controller_events_callback`` for start/end event
    delivery and passes the same normalized callback mapping through STEP. The
    roleless backend receives the mapping but need not interpret the callback.
    """
    controller_events: List[Dict[str, Any]] = []
    controller_callback = controller_events.append

    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART"),
        step_script=[ctx("MANUALFILLNEEDEDSTEP")],
    )
    install_backend(controller_boundary, backend)

    controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        render=False,
        threaded_callbacks={
            "controller_events_callback": controller_callback,
        },
    )

    callback_bag = last_call(backend, "step_session")[2]["threaded_callbacks"]

    assert_controller_event_pair(
        controller_events,
        session_id="S1",
        action="STEP",
    )

    assert callback_bag["controller_events_callback"] is controller_callback
    assert callback_bag["explosion_events_callback"] is None


def test_registered_metadata_pocket_is_published_in_surface(
    clean_session_metadata_pocket_registry,
):
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=grading_pocket_schema(),
    )

    sheet = session_args_metadata_surface_sheet_v1()

    assert sheet["kind"] == "session_args_metadata_surface_v1"
    assert set(sheet["core_keys"]) >= {
        "roles",
        "role_mismatch_policy",
        "manual_io",
        "session_storage",
    }
    assert sheet["app_pocket_keys"] == ["grading"]
    assert "grading" in sheet["keys"]

    grading_surface = sheet["subsurfaces"]["app_pockets"]["grading"]
    assert grading_surface["kind"] == "session_metadata_pocket_schema_v1"
    assert grading_surface["label"] == "Grading"
    assert grading_surface["required_fields"] == ["rubric_id", "grader_role"]
    assert grading_surface["fields"]["settings"]["required_fields"] == [
        "allow_revision",
        "visibility",
    ]


def test_controller_preserves_valid_registered_metadata_pocket(
    controller_boundary,
    clean_session_metadata_pocket_registry,
):
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=grading_pocket_schema(),
    )

    metadata = role_metadata_with_grading_pocket("maker", "reviewer")
    coerced = coerce_session_metadata(metadata)
    assert coerced["grading"] == metadata["grading"]

    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART", meta=metadata),
        step_script=[
            ctx("STEPFNSTEP", meta=metadata),
            ctx("MANUALFILLNEEDEDSTEP", meta=metadata),
        ],
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        role="reviewer",
        render=False,
    )

    assert_manual_fill_result(result)
    result_metadata = result["ctx"]["session_metadata"]
    assert result_metadata["grading"] == metadata["grading"]
    assert result_metadata["roles"] == metadata["roles"]
    assert (
        result_metadata["role_mismatch_policy"]
        == metadata["role_mismatch_policy"]
    )

    queue_end = controller_events_only(backend.session_event_queue)[-1]
    assert (
        queue_end["payload"]["U"]["session_metadata"]["grading"]
        == metadata["grading"]
    )
    assert "role_mismatch_modulation_info" not in queue_end["payload"]["U"]

    assert_roleless_backend(backend)
    assert_no_app_pocket_kwargs(backend, "grading")


def test_invalid_registered_metadata_pocket_is_rejected(
    controller_boundary,
    clean_session_metadata_pocket_registry,
):
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=grading_pocket_schema(),
    )

    invalid_metadata = role_metadata("maker", "reviewer")
    invalid_metadata["grading"] = {
        "grader_role": "reviewer",
        "max_score": 100,
        "settings": {
            "allow_revision": True,
            "visibility": "team",
        },
    }

    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART", meta=invalid_metadata),
        step_script=[ctx("MANUALFILLNEEDEDSTEP", meta=invalid_metadata)],
    )
    install_backend(controller_boundary, backend)

    with pytest.raises(KeyError, match="rubric_id"):
        controller_boundary["dispatch"](
            "S1",
            action=UserAction.STEP,
            role="reviewer",
            render=False,
        )

    assert calls_named(backend, "step_session") == []
    assert backend.session_event_queue == []
    assert_roleless_backend(backend)
    assert_no_app_pocket_kwargs(backend, "grading")


def test_nested_registered_metadata_violation_is_rejected(
    controller_boundary,
    clean_session_metadata_pocket_registry,
):
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=grading_pocket_schema(),
    )

    invalid_metadata = role_metadata("maker", "reviewer")
    invalid_metadata["grading"] = {
        "rubric_id": "rubric.controller.v1",
        "grader_role": "reviewer",
        "max_score": 100,
        "settings": {
            "allow_revision": True,
            "visibility": "secret",
        },
    }

    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART", meta=invalid_metadata),
        step_script=[ctx("MANUALFILLNEEDEDSTEP", meta=invalid_metadata)],
    )
    install_backend(controller_boundary, backend)

    with pytest.raises(ValueError, match="visibility"):
        controller_boundary["dispatch"](
            "S1",
            action=UserAction.STEP,
            role="reviewer",
            render=False,
        )

    assert calls_named(backend, "step_session") == []
    assert backend.session_event_queue == []
    assert_roleless_backend(backend)


def test_multiple_registered_pockets_share_one_controller_surface(
    controller_boundary,
    clean_session_metadata_pocket_registry,
):
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=grading_pocket_schema(),
    )
    SessionMetadataSurfaceRegistry.register_pocket(
        key="workflow",
        schema=workflow_pocket_schema(),
    )

    metadata = role_metadata_with_two_app_pockets("maker", "reviewer")
    sheet = session_args_metadata_surface_sheet_v1()
    coerced = coerce_session_metadata(metadata)

    assert sheet["app_pocket_keys"] == ["grading", "workflow"]
    assert set(sheet["subsurfaces"]["app_pockets"]) == {
        "grading",
        "workflow",
    }
    assert coerced["grading"] == metadata["grading"]
    assert coerced["workflow"] == metadata["workflow"]

    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART", meta=metadata),
        step_script=[
            ctx("STEPFNSTEP", meta=metadata),
            ctx("MANUALFILLNEEDEDSTEP", meta=metadata),
        ],
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        role="maker",
        render=False,
    )

    assert_manual_fill_result(result)
    result_metadata = result["ctx"]["session_metadata"]
    assert result_metadata["grading"] == metadata["grading"]
    assert result_metadata["workflow"] == metadata["workflow"]

    queue_end = controller_events_only(backend.session_event_queue)[-1]
    assert (
        queue_end["payload"]["U"]["session_metadata"]["grading"]
        == metadata["grading"]
    )
    assert (
        queue_end["payload"]["U"]["session_metadata"]["workflow"]
        == metadata["workflow"]
    )

    assert_roleless_backend(backend)
    assert_no_app_pocket_kwargs(backend, "grading", "workflow")


def test_registered_pocket_does_not_weaken_role_validation(
    controller_boundary,
    clean_session_metadata_pocket_registry,
):
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=grading_pocket_schema(),
    )

    invalid_metadata = {
        "roles": {
            "maker": {"read_roles": ["ghost"]},
            "reviewer": {},
        },
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                "maker": "redacted",
                "reviewer": "redacted",
            },
        },
        "grading": {
            "rubric_id": "rubric.controller.v1",
            "grader_role": "reviewer",
            "max_score": 100,
            "settings": {
                "allow_revision": True,
                "visibility": "team",
            },
        },
    }

    backend = ScriptedSessionAPI(
        initial_ctx=ctx("ATSTART", meta=invalid_metadata),
        step_script=[ctx("MANUALFILLNEEDEDSTEP", meta=invalid_metadata)],
    )
    install_backend(controller_boundary, backend)

    with pytest.raises(KeyError, match="ghost|unknown role"):
        controller_boundary["dispatch"](
            "S1",
            action=UserAction.STEP,
            role="maker",
            render=False,
        )

    assert calls_named(backend, "step_session") == []
    assert backend.session_event_queue == []
    assert_roleless_backend(backend)


def test_controller_integration_contract_summary(
    controller_boundary,
    clean_session_metadata_pocket_registry,
):
    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema=grading_pocket_schema(),
    )

    metadata = role_metadata_with_grading_pocket("maker", "reviewer")
    controller_events: List[Dict[str, Any]] = []

    entry_ctx = ctx("ATSTART", meta=metadata)
    final_ctx = ctx("MANUALFILLNEEDEDSTEP", meta=metadata)

    backend = ScriptedSessionAPI(
        initial_ctx=entry_ctx,
        step_script=[final_ctx],
    )
    install_backend(controller_boundary, backend)

    result = controller_boundary["dispatch"](
        "S1",
        action=UserAction.STEP,
        role="reviewer",
        render=False,
        threaded_callbacks={
            "controller_events_callback": controller_events.append,
        },
    )

    sheet = session_args_metadata_surface_sheet_v1()
    start_event, end_event = assert_controller_event_pair(
        controller_events,
        session_id="S1",
        action="STEP",
    )

    queue_start_event, queue_end_event = assert_controller_event_pair(
        backend.session_event_queue,
        session_id="S1",
        action="STEP",
    )

    start_event_U = start_event["payload"]["U"]
    end_event_U = end_event["payload"]["U"]
    queue_start_event_U = queue_start_event["payload"]["U"]
    queue_end_event_U = queue_end_event["payload"]["U"]
    event_result = end_event["payload"]["result"]
    public_ctx = result["ctx"]

    contract = {
        "core_metadata_surface_is_stable": (
            set(sheet["core_keys"])
            >= {
                "roles",
                "role_mismatch_policy",
                "manual_io",
                "session_storage",
            }
        ),
        "app_pocket_is_registered": sheet["app_pocket_keys"] == ["grading"],
        "app_pocket_schema_is_inert": (
            sheet["subsurfaces"]["app_pockets"]["grading"]["kind"]
            == "session_metadata_pocket_schema_v1"
        ),
        "canonical_start_event_context_is_entry_context": (
            start_event_U == entry_ctx
        ),
        "canonical_end_event_context_is_final_context": (
            end_event_U == final_ctx
        ),
        "queue_start_event_context_is_entry_context": (
            queue_start_event_U == entry_ctx
        ),
        "queue_end_event_context_is_final_context": (
            queue_end_event_U == final_ctx
        ),
        "queue_and_callback_event_ids_match": (
            event_ids(controller_events_only(backend.session_event_queue))
            == event_ids(controller_events_only(controller_events))
        ),
        "canonical_event_context_preserves_app_pocket": (
            end_event_U["session_metadata"]["grading"]["rubric_id"]
            == "rubric.controller.v1"
        ),
        "queue_event_context_preserves_app_pocket": (
            queue_end_event_U["session_metadata"]["grading"]["rubric_id"]
            == "rubric.controller.v1"
        ),
        "public_context_preserves_app_pocket": (
            public_ctx["session_metadata"]["grading"]["rubric_id"]
            == "rubric.controller.v1"
        ),
        "public_context_projects_canonical_identity": (
            public_ctx["kind"] == end_event_U["kind"]
            and public_ctx["cursor"] == end_event_U["cursor"]
        ),
        "public_context_contains_canonical_metadata": all(
            public_ctx["session_metadata"].get(key) == value
            for key, value in end_event_U["session_metadata"].items()
        ),
        "canonical_event_context_is_not_public_projection": (
            end_event_U != public_ctx
        ),
        "queue_event_context_is_not_public_projection": (
            queue_end_event_U != public_ctx
        ),
        "canonical_event_context_has_no_release_bookkeeping": (
            "role_assignments" not in end_event_U
            and "role_mismatch_modulation_info" not in end_event_U
        ),
        "queue_event_context_has_no_release_bookkeeping": (
            "role_assignments" not in queue_end_event_U
            and "role_mismatch_modulation_info" not in queue_end_event_U
        ),
        "public_context_has_release_bookkeeping": (
            public_ctx.get("role_assignments") == []
            and public_ctx.get(
                "role_mismatch_modulation_info",
                {},
            ).get("role_viewing")
            == "reviewer"
        ),
        "controller_emits_exact_event_pair": (
            start_event["name"] == CONTROLLER_START_EVENT
            and end_event["name"] == CONTROLLER_END_EVENT
        ),
        "event_pair_shares_dispatch_identity": (
            start_event["dispatch_id"] == end_event["dispatch_id"]
        ),
        "end_event_identifies_public_result": (
            event_result["event_kind"] == result["event_kind"]
            and event_result["ui_mode"] == result["ui_mode"]
            and event_result["finished"] == result["finished"]
        ),
        "controller_events_are_recorded_to_session_queue": (
            queue_start_event["name"] == CONTROLLER_START_EVENT
            and queue_end_event["name"] == CONTROLLER_END_EVENT
        ),
        "controller_is_not_app_schema_aware": all(
            "grading" not in kwargs
            for _, _, kwargs in backend.calls
        ),
        "base_api_is_roleless": all(
            "role" not in kwargs
            and "viewer_role" not in kwargs
            for _, _, kwargs in backend.calls
        ),
    }

    assert contract == {
        "core_metadata_surface_is_stable": True,
        "app_pocket_is_registered": True,
        "app_pocket_schema_is_inert": True,
        "canonical_start_event_context_is_entry_context": True,
        "canonical_end_event_context_is_final_context": True,
        "queue_start_event_context_is_entry_context": True,
        "queue_end_event_context_is_final_context": True,
        "queue_and_callback_event_ids_match": True,
        "canonical_event_context_preserves_app_pocket": True,
        "queue_event_context_preserves_app_pocket": True,
        "public_context_preserves_app_pocket": True,
        "public_context_projects_canonical_identity": True,
        "public_context_contains_canonical_metadata": True,
        "canonical_event_context_is_not_public_projection": True,
        "queue_event_context_is_not_public_projection": True,
        "canonical_event_context_has_no_release_bookkeeping": True,
        "queue_event_context_has_no_release_bookkeeping": True,
        "public_context_has_release_bookkeeping": True,
        "controller_emits_exact_event_pair": True,
        "event_pair_shares_dispatch_identity": True,
        "end_event_identifies_public_result": True,
        "controller_events_are_recorded_to_session_queue": True,
        "controller_is_not_app_schema_aware": True,
        "base_api_is_roleless": True,
    }