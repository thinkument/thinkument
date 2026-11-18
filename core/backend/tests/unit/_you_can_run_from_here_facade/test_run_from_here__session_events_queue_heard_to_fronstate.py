from __future__ import annotations

"""
Canonical session events -> frontend state E2E
==============================================

This sheet exercises the highest ``_thinksessions.run.run_from_here`` façade only for
normal app behavior. One lower concrete-session API handle is used solely to
inject explicit external informational events and synthetic internal failures.
That lower handle is test instrumentation, not part of the downstream
application pattern.

The proof is single-process and serverless. This is sufficient for canonical
event semantics and frontend replay because server locking does not alter packet
meaning. Multi-process write admission still requires a separate hosting-level
transaction, compare-and-swap operation, distributed lock, session actor, or
equivalent serialized per-session boundary.

The E2E does not claim hard-crash liveness, distributed ordering, durable
infinite history, exactly-once network delivery, canonical sink atomicity, or
multi-process exclusion.

The frontend model is incremental and Markovian:

    canonical events
        -> ordered controller action envelopes
        -> latest complete U + open envelope + completed action history

The frontend projection needs only:

    cursor
    latest_U
    open_action
    completed actions
    orphan informative events
    interruptions
    orphan ends

Applying one next canonical event updates this projection without rescanning
earlier events. ``latest_U`` is updated only by controller packets, while the
canonical cursor advances for every visible canonical packet.

For role-projected clients, cursor advancement must use
``page.next_after_event_seq`` rather than the sequence of the final visible
packet because hidden canonical positions may have been acknowledged by the
visibility receipt.

Important laws proved here:

* canonical event_seq values are strictly increasing and past packets do not
  change;
* controller start/end packets carry complete U, timestamp, action, shared
  dispatch_id, immutable dispatcher_identity_id, and dispatcher_role;
* datum/external informational packets need not carry U;
* callback failure remains isolated even when RuntimeWarning is configured as
  an exception;
* ordinary successful, semantic-rejected, undo, and systematic-error dispatches
  all append forward-only controller envelopes;
* every successfully recorded controller start is closed by one matching end
  for ordinary in-process Exception paths covered by the controller;
* an Exception with a broken ``__str__`` implementation still produces a
  bounded systematic-error packet and matching controller end;
* a new span/frame discovered by dispatch completion first appears on that
  dispatch's end U; the next start begins from that same U when no out-of-band
  mutation occurred;
* the latest complete state is U on the latest controller event, not
  necessarily the payload of the latest event of any kind;
* the latest canonical event is not required to be a state packet;
* a new start while another envelope is open marks the older dispatch as
  interrupted;
* external events may occur inside an open envelope or between envelopes;
* a poller can incrementally apply pages and reach the same projection as a
  one-shot replay;
* the live canonical queue is bounded and is not permanent audit history.

“Trident” means one controller start, zero or more informative events, and one
matching controller end. It does not mean exactly three packets. Informative
events may be absent, may be numerous, and may also occur between controller
envelopes.

The modulated action queue is a frontend projection, not a replacement
canonical record. Informative events do not currently carry ``dispatch_id`` or
dispatcher actor identity; attachment to an open envelope is therefore temporal
attribution rather than an independent causal-identity guarantee.

Envelope statuses used by this projection are:

    open
    success
    semantic_rejected
    system_error
    interrupted

Semantic rejection is represented by a successful controller end whose
``payload.result.last_error`` is populated. Systematic failure is represented
by an end whose ``payload.outcome`` is ``"system_error"``.

Preflight authorization, staleness, or request-normalization rejection occurs
before a controller start and therefore creates no controller envelope.

After a controller start has been successfully recorded, every ordinary
in-process Python ``Exception`` from routing, liaison execution, context
recovery, or result construction is converted into one matching end attempt.

Excluded from that safety statement are:

    SystemExit
    KeyboardInterrupt
    hard process death
    machine loss
    canonical sink failure

A sink can commit and then raise, so retrying an end could create a competing
duplicate packet. Merely being caught up while an envelope remains open does
not prove interruption; a later controller start provides the evidence used by
the frontend projection to classify the older envelope as interrupted.

Initial and terminal edges are ordinary controller envelopes:

    ATSTART -> first renderable/manual state
    last renderable/manual state -> ATCOMPLETION

Undo moves backward on the program tape while still appending later canonical
event sequence numbers.

No test claims hard-crash liveness or multi-process ordering.
"""

import warnings
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping
from unittest.mock import patch

import _thinkprogram._iomicrosTM.table_micros  # noqa: F401
import pytest

from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
)
from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
)
from _thinksessions.run.run_from_here import (
    UserAction,
    create_live_session_from_program,
    dispatch_live_session_action as _dispatch_live_session_action,
    get_live_session_context,
    get_live_session_events,
    get_live_session_events_since,
    get_live_session_latest_event_seq,
)

from ._fixtures_facade_run import (
    DEFAULT_DISPATCHER_IDENTITY_ID,
    assert_strict_canonical_event_order_v1,
    facade_note_program_v1,
    facade_session_metadata_v1,
    launch_facade_note_session_v1,
    two_note_program_v1,
)


CONTROLLER_KIND = "controller_loop_event_v1"
DATUM_KIND = "datum_lifecycle_event_v1"
DATUM_STATE_KIND = "universal_ui_datum_state_v1"
OBFUSCATED_DATUM_KIND = "role_mismatch_obfuscated_datum_v1"


def _validator_fields(value: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Test-side statement of the published validator-field projection law.

    The complete source shell/spec remains authoritative. This convenience
    projection retains authored fields whose key explicitly identifies
    validation or lambda semantics.
    """
    return {
        str(key): deepcopy(raw_value)
        for key, raw_value in value.items()
        if (
            "validat" in str(key).lower()
            or "lambda" in str(key).lower()
        )
    }


def _effective_datums_by_id(
    U: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    multiframespec = U.get("multiframespec")
    assert isinstance(multiframespec, Mapping)

    raw_datums = multiframespec.get("datums")
    assert isinstance(raw_datums, list)

    out: Dict[str, Dict[str, Any]] = {}
    for row in raw_datums:
        assert isinstance(row, Mapping)
        datum_id = str(row.get("id") or "").strip()
        assert datum_id
        assert datum_id not in out
        out[datum_id] = deepcopy(dict(row))

    return out


def _datum_states(U: Mapping[str, Any]) -> list[Dict[str, Any]]:
    rows = U.get("datum_states_on_this_span")
    assert isinstance(rows, list)
    return [
        deepcopy(dict(row))
        for row in rows
        if isinstance(row, Mapping)
    ]


def _assert_complete_readable_Di_v1(
    row: Mapping[str, Any],
    *,
    U: Mapping[str, Any],
    effective_shell: Mapping[str, Any],
) -> None:
    datum_id = str(row.get("datum_id") or "")

    assert row["kind"] == DATUM_STATE_KIND
    assert datum_id
    assert row["form_id"] == str(
        U.get("form_id") or U.get("app_form_id") or ""
    )
    assert row["frame_id"] == str(U.get("current_frame_id") or "")
    assert row["span_id"] == str(
        U.get("current_span")
        or U.get("current_span_id")
        or ""
    )

    # Shell authority is the current effective hydrated multiframespec.
    assert row["shell"] == effective_shell

    shell_micros = effective_shell.get("micros") or []
    assert isinstance(shell_micros, list)
    exact_micros = [
        dict(micro)
        for micro in shell_micros
        if isinstance(micro, Mapping)
    ]
    assert row["micros"] == exact_micros
    assert row["micro_names"] == [
        str(micro.get("name") or "")
        for micro in exact_micros
        if str(micro.get("name") or "").strip()
    ]

    shell_args = effective_shell.get("args")
    expected_args = (
        dict(shell_args)
        if isinstance(shell_args, Mapping)
        else {}
    )
    assert row["args"] == expected_args

    semantic = row["semantic_validation"]
    assert isinstance(semantic, Mapping)
    assert (
        semantic["datum_validator_fields"]
        == _validator_fields(effective_shell)
    )

    semantic_micros = semantic["micros"]
    assert isinstance(semantic_micros, list)
    assert len(semantic_micros) == len(exact_micros)
    for source_micro, semantic_micro in zip(
        exact_micros,
        semantic_micros,
        strict=True,
    ):
        assert semantic_micro == {
            "name": str(source_micro.get("name") or ""),
            "spec": source_micro,
            "validator_fields": _validator_fields(source_micro),
        }

    fills = U.get("datum_widget_fills")
    assert isinstance(fills, Mapping)
    assert row["has_fill"] is (datum_id in fills)
    assert row["fill"] == fills.get(datum_id)

    assert isinstance(row["is_authoritative"], bool)
    assert isinstance(row["is_pending"], bool)
    assert row["is_pending"] is (
        datum_id in list(U.get("datum_widgets_on_this_span") or [])
    )

    lifecycle = row["lifecycle"]
    assert isinstance(lifecycle, Mapping)
    assert isinstance(lifecycle["enabled"], bool)
    assert isinstance(lifecycle["policy"], Mapping)
    assert lifecycle["runtime"] is None or isinstance(
        lifecycle["runtime"],
        Mapping,
    )

    originating_step = row["originating_step"]
    assert isinstance(originating_step, Mapping)
    step = U.get("step")
    assert isinstance(step, Mapping)
    assert originating_step["public_step_name"] == str(
        step.get("public_step_name") or ""
    )
    assert originating_step["source_step_fn"] == str(
        step.get("source_step_fn") or ""
    )
    assert originating_step["source_fn_args"] == dict(
        step.get("source_fn_args") or {}
    )


def _assert_obfuscated_Di_has_no_private_pockets_v1(
    row: Mapping[str, Any],
) -> None:
    assert row["kind"] == OBFUSCATED_DATUM_KIND
    assert row["role_mismatch_obfuscated"] is True
    assert row["obfuscated"] is True
    assert row["is_authoritative"] is None
    assert row["is_pending"] is False

    for forbidden in (
        "shell",
        "micros",
        "micro_names",
        "args",
        "fill",
        "has_fill",
        "semantic_validation",
        "lifecycle",
        "originating_step",
    ):
        assert forbidden not in row


def dispatch_live_session_action(**kwargs: Any) -> Dict[str, Any]:
    kwargs.setdefault(
        "identity_id",
        DEFAULT_DISPATCHER_IDENTITY_ID,
    )
    return _dispatch_live_session_action(**kwargs)


def _launch(*, program: Mapping[str, Any] | None = None) -> str:
    return launch_facade_note_session_v1(program=program)


def _controller(events: list[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    return [
        dict(event)
        for event in events
        if event.get("kind") == CONTROLLER_KIND
    ]


def _scope(U: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    return (
        U.get("form_id") or U.get("app_form_id"),
        U.get("current_frame_id"),
        U.get("current_span") or U.get("current_span_id"),
    )


def _assert_monotonic_immutable_shape(
    events: list[Mapping[str, Any]],
) -> None:
    assert_strict_canonical_event_order_v1(events)


def _assert_closed_controller_stream(
    events: list[Mapping[str, Any]],
) -> None:
    open_dispatch_id: str | None = None

    for event in events:
        if event.get("kind") != CONTROLLER_KIND:
            continue

        assert isinstance(event["payload"]["U"], dict)
        assert event["payload"]["timestamp"] == event["emitted_at"]

        phase = event["phase"]
        dispatch_id = str(event["dispatch_id"])

        if phase == "start":
            assert open_dispatch_id is None
            open_dispatch_id = dispatch_id
            continue

        assert phase == "end"
        assert open_dispatch_id == dispatch_id
        open_dispatch_id = None

    assert open_dispatch_id is None


def _assert_fundamental_controller_packet_v1(
    event: Mapping[str, Any],
) -> None:
    assert event["kind"] == CONTROLLER_KIND
    assert event["phase"] in {"start", "end"}
    assert str(event["dispatch_id"])
    assert str(event["dispatcher_identity_id"])
    assert event["dispatcher_role"] is None or isinstance(
        event["dispatcher_role"],
        str,
    )
    assert str(event["event_id"])
    assert event["action"] in {"STEP", "UNDO", "REDO"}
    assert event["payload"]["timestamp"] == event["emitted_at"]
    assert isinstance(event["payload"]["U"], dict)

    # ISO-8601 parseability is the public timestamp law; exact timezone string
    # formatting remains owned by the shared timestamp helper.
    datetime.fromisoformat(
        str(event["emitted_at"]).replace("Z", "+00:00")
    )


@dataclass
class ActionEnvelope:
    dispatch_id: str
    start: Dict[str, Any]
    informative_events: list[Dict[str, Any]] = field(default_factory=list)
    end: Dict[str, Any] | None = None
    status: str = "open"

    @property
    def action(self) -> str:
        return str(self.start["action"])

    @property
    def dispatcher_identity_id(self) -> str:
        return str(self.start["dispatcher_identity_id"])

    @property
    def dispatcher_role(self) -> str | None:
        value = self.start.get("dispatcher_role")
        return None if value is None else str(value)

    @property
    def source_U(self) -> Dict[str, Any]:
        return dict(self.start["payload"]["U"])

    @property
    def destination_U(self) -> Dict[str, Any] | None:
        if self.end is None:
            return None
        return dict(self.end["payload"]["U"])


@dataclass
class FrontendProjection:
    cursor: int = 0
    latest_U: Dict[str, Any] | None = None
    open_action: ActionEnvelope | None = None
    actions: list[ActionEnvelope] = field(default_factory=list)
    orphan_informative_events: list[Dict[str, Any]] = field(
        default_factory=list
    )
    interruptions: list[str] = field(default_factory=list)
    orphan_ends: list[Dict[str, Any]] = field(default_factory=list)

    def apply(self, raw_event: Mapping[str, Any]) -> None:
        event = deepcopy(dict(raw_event))
        seq = int(event["event_seq"])

        if seq <= self.cursor:
            raise ValueError(
                "frontend projection requires strictly increasing event_seq; "
                f"cursor={self.cursor}, received={seq}"
            )

        self.cursor = seq

        if event.get("kind") != CONTROLLER_KIND:
            if self.open_action is None:
                self.orphan_informative_events.append(event)
            else:
                self.open_action.informative_events.append(event)
            return

        self.latest_U = deepcopy(dict(event["payload"]["U"]))
        dispatch_id = str(event["dispatch_id"])

        if event["phase"] == "start":
            if self.open_action is not None:
                self.open_action.status = "interrupted"
                self.actions.append(self.open_action)
                self.interruptions.append(self.open_action.dispatch_id)

            self.open_action = ActionEnvelope(
                dispatch_id=dispatch_id,
                start=event,
            )
            return

        assert event["phase"] == "end"

        if (
            self.open_action is None
            or self.open_action.dispatch_id != dispatch_id
            or (
                self.open_action.dispatcher_identity_id
                != str(event.get("dispatcher_identity_id") or "")
            )
            or (
                self.open_action.dispatcher_role
                != event.get("dispatcher_role")
            )
        ):
            self.orphan_ends.append(event)
            return

        self.open_action.end = event
        payload = event["payload"]

        if payload.get("outcome") == "system_error":
            self.open_action.status = "system_error"
        elif (payload.get("result") or {}).get("last_error"):
            self.open_action.status = "semantic_rejected"
        else:
            self.open_action.status = "success"

        self.actions.append(self.open_action)
        self.open_action = None


def _project(events: list[Mapping[str, Any]]) -> FrontendProjection:
    projection = FrontendProjection()
    for event in events:
        projection.apply(event)
    return projection


def _poll_all_incrementally(
    *,
    session_id: str,
    page_limit: int,
) -> FrontendProjection:
    projection = FrontendProjection()

    while projection.cursor < get_live_session_latest_event_seq(
        session_id=session_id
    ):
        page = get_live_session_events_since(
            session_id=session_id,
            role=None,
            identity_id="frontstate-test",
            after_event_seq=projection.cursor,
            limit=page_limit,
        )
        assert page["next_after_event_seq"] > projection.cursor
        for event in page["events"]:
            projection.apply(event)

        # role=None sees every retained canonical event, so its local event
        # cursor equals the canonical scanned-through cursor.
        assert projection.cursor == page["next_after_event_seq"]

    return projection


def test_initial_edge_is_ATSTART_to_first_manual_span() -> None:
    sid = _launch()

    packet = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    assert packet["dispatch_outcome"] == "applied"

    controller = _controller(
        get_live_session_events(session_id=sid, role=None)
    )
    assert [event["phase"] for event in controller] == ["start", "end"]

    start_U = controller[0]["payload"]["U"]
    end_U = controller[1]["payload"]["U"]

    assert start_U["kind"] == "ATSTART"
    assert end_U["kind"] == "MANUALFILLNEEDEDSTEP"
    assert end_U["current_span"] == "span"
    assert controller[0]["dispatch_id"] == controller[1]["dispatch_id"]


def test_every_controller_event_has_complete_envelope_identity() -> None:
    sid = _launch()
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="writer-controller-e2e",
    )

    controller = _controller(
        get_live_session_events(session_id=sid, role=None)
    )
    assert controller

    for event in controller:
        assert event["phase"] in {"start", "end"}
        assert str(event["dispatch_id"])
        assert event["dispatcher_identity_id"] == "writer-controller-e2e"
        assert event["dispatcher_role"] == "writer"
        assert str(event["event_id"])
        assert str(event["emitted_at"])
        assert event["payload"]["timestamp"] == event["emitted_at"]
        assert isinstance(event["payload"]["U"], dict)
        assert event["session_id"] == sid
        assert event["action"] == "STEP"

    assert controller[0]["dispatch_id"] == controller[1]["dispatch_id"]
    assert (
        controller[0]["dispatcher_identity_id"]
        == controller[1]["dispatcher_identity_id"]
    )
    assert (
        controller[0]["dispatcher_role"]
        == controller[1]["dispatcher_role"]
    )


def test_start_and_end_actor_identity_is_immutable_within_envelope() -> None:
    sid = _launch()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="writer-tab-primary",
    )

    start, end = _controller(
        get_live_session_events(session_id=sid, role=None)
    )

    assert start["dispatcher_identity_id"] == "writer-tab-primary"
    assert end["dispatcher_identity_id"] == "writer-tab-primary"
    assert start["dispatcher_role"] == "writer"
    assert end["dispatcher_role"] == "writer"


def test_roleless_controller_events_use_json_null_role() -> None:
    sid = _launch()

    # This fixture's writable datum requires writer, so use a targetless
    # controller action to prove roleless actor packet shape.
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=None,
        identity_id="system-roleless-dispatcher",
    )

    for event in _controller(
        get_live_session_events(session_id=sid, role=None)
    ):
        assert (
            event["dispatcher_identity_id"]
            == "system-roleless-dispatcher"
        )
        assert event["dispatcher_role"] is None


def test_one_by_one_fundamental_packet_box_holds_for_every_controller_event() -> None:
    sid = _launch()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": ""}},
    )
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "accepted"}},
    )
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.UNDO,
        role="writer",
    )

    events = get_live_session_events(session_id=sid, role=None)
    _assert_monotonic_immutable_shape(events)
    _assert_closed_controller_stream(events)
    for event in _controller(events):
        _assert_fundamental_controller_packet_v1(event)


def test_terminal_edge_is_last_manual_span_to_completion() -> None:
    sid = _launch()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    before = _controller(
        get_live_session_events(session_id=sid, role=None)
    )[-1]["payload"]["U"]
    assert before["kind"] == "MANUALFILLNEEDEDSTEP"

    packet = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "accepted"}},
    )
    assert packet["dispatch_outcome"] == "applied"

    start, end = _controller(
        get_live_session_events(session_id=sid, role=None)
    )[-2:]
    assert start["payload"]["U"] == before
    assert start["payload"]["U"]["kind"] == "MANUALFILLNEEDEDSTEP"
    assert end["payload"]["U"]["kind"] == "ATCOMPLETION"
    assert end["payload"]["result"]["finished"] is True


def test_role_denial_is_preflight_eventless_and_does_not_move_high_water() -> None:
    sid = _launch()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    before_seq = get_live_session_latest_event_seq(session_id=sid)
    before_events = deepcopy(
        get_live_session_events(session_id=sid, role=None)
    )

    with pytest.raises(PermissionError, match="note"):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="auditor",
            user_fill={"note": {"text": "Auditor Must Not Write"}},
        )

    assert get_live_session_latest_event_seq(session_id=sid) == before_seq
    assert (
        get_live_session_events(
            session_id=sid,
            role=None,
        )
        == before_events
    )


def test_success_semantic_rejection_and_undo_all_append_forward_envelopes() -> None:
    sid = _launch()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    C = get_live_session_latest_event_seq(session_id=sid)

    semantic = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": ""}},
        my_current_event_seq_number=C,
    )
    assert semantic["dispatch_outcome"] == "semantic_rejected"
    assert semantic["write_committed"] is False
    assert semantic["system_error"] is None

    success = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "accepted"}},
    )
    assert success["dispatch_outcome"] == "applied"

    before_undo = get_live_session_latest_event_seq(session_id=sid)
    with pytest.warns(UserWarning):
        undone = dispatch_live_session_action(
            session_id=sid,
            action=UserAction.UNDO,
            role="writer",
            user_fill={"note": {"text": "ignored"}},
            user_signal={
                "datum_id": "note",
                "kind": "ignored",
                "info": {},
            },
        )
    assert undone["dispatch_outcome"] == "applied"
    assert get_live_session_latest_event_seq(session_id=sid) > before_undo

    events = get_live_session_events(session_id=sid, role=None)
    _assert_monotonic_immutable_shape(events)
    _assert_closed_controller_stream(events)

    projection = _project(events)
    assert projection.open_action is None
    assert projection.orphan_ends == []
    assert [row.status for row in projection.actions] == [
        "success",
        "semantic_rejected",
        "success",
        "success",
    ]
    assert [row.action for row in projection.actions] == [
        "STEP",
        "STEP",
        "STEP",
        "UNDO",
    ]

    semantic_end = projection.actions[1].end
    assert semantic_end is not None
    assert semantic_end["payload"]["outcome"] == "success"
    assert semantic_end["payload"]["result"]["last_error"]["note"]

    undo = projection.actions[-1]
    assert undo.start["payload"]["fill"] == {}
    assert undo.start["payload"]["signal"] is None


def test_multiple_datum_semantic_errors_are_carried_on_end_U_and_result() -> None:
    sid = _launch(program=two_note_program_v1())

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )

    packet = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={
            "alpha": {"text": ""},
            "beta": {"text": ""},
        },
    )
    assert packet["dispatch_outcome"] == "semantic_rejected"

    end = _controller(
        get_live_session_events(session_id=sid, role=None)
    )[-1]
    errors_in_U = end["payload"]["U"]["last_error"]
    errors_in_result = end["payload"]["result"]["last_error"]

    assert set(errors_in_U) == {"alpha", "beta"}
    assert errors_in_result == errors_in_U
    assert end["payload"]["outcome"] == "success"
    assert "system_error" not in end["payload"]


def test_systematic_runtime_error_is_caught_and_closes_the_envelope() -> None:
    sid = _launch()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    before = get_live_session_latest_event_seq(session_id=sid)
    api = get_concrete_session_api()

    with patch.object(
        api,
        "step_session",
        side_effect=RuntimeError("synthetic controller-loop failure"),
    ):
        packet = dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
            user_fill={"note": {"text": "keep-open: never-committed"}},
        )

    assert packet["ok"] is False
    assert packet["applied"] is True
    assert packet["rejected"] is False
    assert packet["dispatch_outcome"] == "system_error"
    assert packet["write_committed"] is False
    assert packet["system_error"]["exception_type"] == "RuntimeError"

    events = get_live_session_events(session_id=sid, role=None)
    assert int(events[-1]["event_seq"]) > before
    _assert_closed_controller_stream(events)

    final_action = _project(events).actions[-1]
    assert final_action.status == "system_error"
    assert final_action.end is not None
    assert (
        final_action.end["payload"]["system_error"]
        == packet["system_error"]
    )


def test_post_step_controller_error_is_caught_and_closes_envelope() -> None:
    sid = _launch()

    with patch(
        "_thinkengine._engine_interactive_flow_controller."
        "dispatch_UFU_automaton.get_routing_map",
        side_effect=RuntimeError("synthetic routing failure"),
    ):
        packet = dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
        )

    assert packet["dispatch_outcome"] == "system_error"
    assert packet["system_error"]["exception_type"] == "RuntimeError"

    events = get_live_session_events(session_id=sid, role=None)
    _assert_closed_controller_stream(events)
    assert _project(events).actions[-1].status == "system_error"


def test_callback_exception_cannot_break_the_canonical_envelope() -> None:
    sid = _launch()

    def broken_callback(_event: Mapping[str, Any]) -> None:
        raise RuntimeError("frontend callback is broken")

    with pytest.warns(
        RuntimeWarning,
        match="controller event callback raised and was isolated",
    ):
        packet = dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
            threaded_callbacks={
                "controller_events_callback": broken_callback,
            },
        )

    assert packet["dispatch_outcome"] == "applied"
    _assert_closed_controller_stream(
        get_live_session_events(session_id=sid, role=None)
    )


def test_callback_exception_is_isolated_when_runtime_warning_is_an_error() -> None:
    sid = _launch()

    def broken_callback(_event: Mapping[str, Any]) -> None:
        raise RuntimeError("frontend callback is broken")

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        packet = dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
            threaded_callbacks={
                "controller_events_callback": broken_callback,
            },
        )

    assert packet["dispatch_outcome"] == "applied"
    events = get_live_session_events(session_id=sid, role=None)
    _assert_closed_controller_stream(events)
    assert _project(events).actions[-1].status == "success"


def test_exception_with_broken_stringification_still_closes_envelope() -> None:
    class BrokenStringError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("broken exception __str__")

    sid = _launch()
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    api = get_concrete_session_api()

    with patch.object(
        api,
        "step_session",
        side_effect=BrokenStringError(),
    ):
        packet = dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
            user_fill={"note": {"text": "never committed"}},
        )

    assert packet["dispatch_outcome"] == "system_error"
    assert packet["system_error"] == {
        "kind": "controller_dispatch_system_error_v1",
        "exception_type": "BrokenStringError",
        "message": "<exception message unavailable>",
    }

    events = get_live_session_events(session_id=sid, role=None)
    _assert_closed_controller_stream(events)
    action = _project(events).actions[-1]
    assert action.status == "system_error"
    assert action.end is not None
    assert (
        action.end["payload"]["system_error"]
        == packet["system_error"]
    )


def test_new_surface_is_first_seen_on_end_and_next_start_reuses_that_U() -> None:
    sid = _launch()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    first_end = _controller(
        get_live_session_events(session_id=sid, role=None)
    )[-1]
    first_manual_U = first_end["payload"]["U"]

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "accepted"}},
    )
    controller = _controller(
        get_live_session_events(session_id=sid, role=None)
    )
    second_start, second_end = controller[-2:]

    assert second_start["payload"]["U"] == first_manual_U
    assert _scope(second_start["payload"]["U"]) == _scope(first_manual_U)
    assert second_end["payload"]["U"]["kind"] == "ATCOMPLETION"

    # The completion surface did not exist on the second start.
    assert second_start["payload"]["U"]["kind"] == "MANUALFILLNEEDEDSTEP"


def test_end_U_contains_complete_static_D_vector_in_span_ownership_order() -> None:
    sid = _launch(program=two_note_program_v1())

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )

    U = _controller(
        get_live_session_events(session_id=sid, role=None)
    )[-1]["payload"]["U"]

    states = _datum_states(U)
    effective = _effective_datums_by_id(U)

    step = U.get("step")
    assert isinstance(step, Mapping)
    span_owns = [
        str(value)
        for value in list(step.get("span_owns") or [])
    ]

    assert [row["datum_id"] for row in states] == span_owns
    assert len(states) == len(span_owns)
    assert len({row["datum_id"] for row in states}) == len(states)

    authoritative = {
        str(value)
        for value in list(step.get("span_authoritative") or [])
    }

    for row in states:
        datum_id = str(row["datum_id"])
        _assert_complete_readable_Di_v1(
            row,
            U=U,
            effective_shell=effective[datum_id],
        )
        assert row["is_authoritative"] is (
            datum_id in authoritative
        )


def test_D_vector_exposes_authored_semantic_validator_fields_exactly() -> None:
    sid = _launch(program=two_note_program_v1())

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )

    U = _controller(
        get_live_session_events(session_id=sid, role=None)
    )[-1]["payload"]["U"]
    states = _datum_states(U)

    found_authored_validator = False
    for row in states:
        semantic = row["semantic_validation"]
        datum_fields = semantic["datum_validator_fields"]
        if datum_fields:
            found_authored_validator = True

        for micro in semantic["micros"]:
            if micro["validator_fields"]:
                found_authored_validator = True

    assert found_authored_validator, (
        "the semantic-validator E2E fixture must author at least one datum "
        "or micro validator field"
    )


def test_role_projection_obfuscates_the_complete_Di_row_without_leaks() -> None:
    sid = _launch()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )

    canonical_U = get_live_session_context(
        session_id=sid,
        role=None,
    )
    assert isinstance(canonical_U, Mapping)

    canonical_states = _datum_states(canonical_U)
    canonical_note = next(
        row
        for row in canonical_states
        if row.get("datum_id") == "note"
    )
    assert canonical_note["kind"] == DATUM_STATE_KIND
    assert "semantic_validation" in canonical_note

    auditor_U = get_live_session_context(
        session_id=sid,
        role="auditor",
    )
    assert isinstance(auditor_U, Mapping)

    auditor_states = _datum_states(auditor_U)
    auditor_note = next(
        row
        for row in auditor_states
        if row.get("datum_id") == "note"
    )
    _assert_obfuscated_Di_has_no_private_pockets_v1(auditor_note)

    assert "note" not in list(
        auditor_U.get("datum_widgets_on_this_span") or []
    )


def test_incremental_polling_preserves_complete_final_D_vector() -> None:
    sid = _launch(program=two_note_program_v1())

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={
            "alpha": {"text": ""},
            "beta": {"text": ""},
        },
    )

    events = get_live_session_events(session_id=sid, role=None)
    one_shot = _project(events)
    incremental = _poll_all_incrementally(
        session_id=sid,
        page_limit=1,
    )

    assert one_shot.latest_U is not None
    assert incremental.latest_U is not None
    assert (
        incremental.latest_U["datum_states_on_this_span"]
        == one_shot.latest_U["datum_states_on_this_span"]
    )

    for row in incremental.latest_U["datum_states_on_this_span"]:
        assert row["kind"] == DATUM_STATE_KIND
        assert isinstance(row["semantic_validation"], Mapping)


def test_undo_moves_backward_on_program_tape_but_forward_in_event_time() -> None:
    sid = _launch()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "accepted"}},
    )

    before = get_live_session_latest_event_seq(session_id=sid)
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.UNDO,
        role="writer",
    )
    after = get_live_session_latest_event_seq(session_id=sid)
    assert after > before

    undo = _project(
        get_live_session_events(session_id=sid, role=None)
    ).actions[-1]
    assert undo.action == "UNDO"
    assert undo.source_U["kind"] == "ATCOMPLETION"
    assert undo.destination_U is not None
    assert undo.destination_U["kind"] == "MANUALFILLNEEDEDSTEP"


def test_informative_events_may_be_inside_or_between_action_envelopes() -> None:
    sid = _launch()
    api = get_concrete_session_api()

    # Complete one controller envelope so the session has a real current
    # form/frame/span location. An external event emitted now is between
    # controller envelopes.
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )

    raw = api.get_session_context(sid)
    api.emit_session_event(
        sid,
        form_id=raw["form_id"],
        frame_id=raw["current_frame_id"],
        span_id=raw["current_span"],
        datum_id="note",
        payload={"where": "before-dispatch"},
        name="test.external.before_dispatch",
    )

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: second-envelope"}},
    )

    projection = _project(
        get_live_session_events(session_id=sid, role=None)
    )

    assert any(
        event["name"] == "test.external.before_dispatch"
        for event in projection.orphan_informative_events
    )

    # NoteWidget emits an immediate lifecycle message during mount. When the
    # lower lifecycle queue exposes it, it belongs to the open controller
    # envelope and is informational rather than a state snapshot.
    mounted = projection.actions[0]
    assert all(
        "U" not in event.get("payload", {})
        for event in mounted.informative_events
    )


def test_latest_complete_state_comes_from_latest_controller_event() -> None:
    sid = _launch()
    api = get_concrete_session_api()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    before_external = _project(
        get_live_session_events(session_id=sid, role=None)
    )
    latest_U = deepcopy(before_external.latest_U)

    raw = api.get_session_context(sid)
    api.emit_session_event(
        sid,
        form_id=raw["form_id"],
        frame_id=raw["current_frame_id"],
        span_id=raw["current_span"],
        datum_id="note",
        payload={"informative": True},
        name="test.external.non_mutating",
    )

    events = get_live_session_events(session_id=sid, role=None)
    assert events[-1]["kind"] == DATUM_KIND
    assert "U" not in events[-1]["payload"]

    projection = _project(events)
    assert projection.latest_U == latest_U
    assert projection.cursor == int(events[-1]["event_seq"])


def test_latest_event_is_not_required_to_be_a_state_packet() -> None:
    sid = _launch()
    api = get_concrete_session_api()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    controller_U = deepcopy(
        _controller(
            get_live_session_events(session_id=sid, role=None)
        )[-1]["payload"]["U"]
    )

    raw = api.get_session_context(sid)
    api.emit_session_event(
        sid,
        form_id=raw["form_id"],
        frame_id=raw["current_frame_id"],
        span_id=raw["current_span"],
        datum_id="note",
        payload={"informative_tail": True},
        name="test.external.informative_tail",
    )

    events = get_live_session_events(session_id=sid, role=None)
    assert events[-1]["kind"] == DATUM_KIND
    projection = _project(events)
    assert projection.latest_U == controller_U
    assert projection.cursor == int(events[-1]["event_seq"])


def test_frontend_projection_is_markovian_and_incremental_replay_equivalent() -> None:
    sid = _launch()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": ""}},
    )
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "accepted"}},
    )

    events = get_live_session_events(session_id=sid, role=None)
    one_shot = _project(events)
    incremental = _poll_all_incrementally(
        session_id=sid,
        page_limit=1,
    )

    assert incremental.cursor == one_shot.cursor
    assert incremental.latest_U == one_shot.latest_U
    assert [
        (row.dispatch_id, row.status) for row in incremental.actions
    ] == [
        (row.dispatch_id, row.status) for row in one_shot.actions
    ]

    assert one_shot.latest_U is not None
    assert one_shot.latest_U["kind"] == "ATCOMPLETION"
    assert one_shot.open_action is None
    assert one_shot.latest_U == one_shot.actions[-1].destination_U


def test_frontend_projection_rejects_duplicate_or_out_of_order_delivery() -> None:
    sid = _launch()
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    event = get_live_session_events(session_id=sid, role=None)[0]

    projection = FrontendProjection()
    projection.apply(event)

    with pytest.raises(
        ValueError,
        match="strictly increasing event_seq",
    ):
        projection.apply(event)


def test_frontend_projection_is_for_the_retained_window_not_infinite_history() -> None:
    sid = _launch()

    for index in range(40):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
            user_signal=(
                None
                if index == 0
                else {
                    "datum_id": "note",
                    "kind": "touch",
                    "info": {"index": index},
                }
            ),
        )

    events = get_live_session_events(session_id=sid, role=None)
    assert 0 < len(events) <= 32
    assert_strict_canonical_event_order_v1(events)


def test_SM_only_C_assignment_controls_the_live_canonical_retention_window() -> None:
    """
    This is the behavior-level proof for the SM half of joint puppeteering.

    ``session.queue_window`` does not exist in P. Default strict joint C must
    still accept it because SM exposes the name, and the resolved value must
    reach the existing queue implementation rather than merely appear in
    descriptive metadata.
    """
    program = facade_note_program_v1()
    metadata = facade_session_metadata_v1(chainreactioned=False)
    metadata["symbols"] = {
        "session.queue_window": {
            "value": 32,
            "parametrize": True,
        },
    }
    metadata["puppeteering"] = {
        "session.queue_window": 12,
    }
    metadata["session_storage"] = {
        "events_snapshot_window": "$session.queue_window",
    }

    created = create_live_session_from_program(
        program=program,
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={
            "session.queue_window": 6,
        },
        session_metadata=metadata,
    )
    assert created["ok"] is True
    sid = str(created["session_id"])

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )

    for index in range(10):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
            user_signal={
                "datum_id": "note",
                "kind": "touch",
                "info": {"index": index},
            },
        )

    events = get_live_session_events(
        session_id=sid,
        role=None,
    )
    assert len(events) == 6
    assert_strict_canonical_event_order_v1(events)

    latest = get_live_session_latest_event_seq(session_id=sid)
    assert [int(event["event_seq"]) for event in events] == list(
        range(latest - 5, latest + 1)
    )

    U = get_live_session_context(session_id=sid, role=None)
    assert U["session_metadata"]["session_storage"][
        "events_snapshot_window"
    ] == 6
    assert "symbols" not in U["session_metadata"]
    assert "puppeteering" not in U["session_metadata"]


def test_past_event_packets_do_not_change_after_later_dispatches() -> None:
    sid = _launch()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    first_snapshot = deepcopy(
        get_live_session_events(session_id=sid, role=None)
    )

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: later"}},
    )
    later = get_live_session_events(session_id=sid, role=None)

    assert later[: len(first_snapshot)] == first_snapshot
    assert int(later[-1]["event_seq"]) > int(first_snapshot[-1]["event_seq"])


def test_interrupted_open_action_is_detected_only_when_next_start_arrives() -> None:
    sid = _launch()
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    events = get_live_session_events(session_id=sid, role=None)

    first_start = next(
        event
        for event in events
        if event.get("kind") == CONTROLLER_KIND
        and event.get("phase") == "start"
    )
    final_U = _controller(events)[-1]["payload"]["U"]

    synthetic_next_start = deepcopy(first_start)
    synthetic_next_start.update(
        {
            "event_id": "synthetic-next-start",
            "event_seq": int(events[-1]["event_seq"]) + 1,
            "dispatch_id": "synthetic-next-dispatch",
        }
    )
    synthetic_next_start["payload"]["U"] = deepcopy(final_U)

    projection = FrontendProjection()
    projection.apply(first_start)

    # Merely being caught up with an open start does not prove when or whether
    # another event will arrive.
    assert projection.open_action is not None
    assert projection.interruptions == []

    projection.apply(synthetic_next_start)
    assert projection.interruptions == [str(first_start["dispatch_id"])]
    assert projection.actions[0].status == "interrupted"
    assert projection.latest_U == final_U
