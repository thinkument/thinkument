from __future__ import annotations

"""E2E proof sheet for dispatch admission, trident taxonomy and aggregation.

Downstream interpretation lives in ``_event_trident_downstream_readers.py`` so
this suite, the adjacent UI suite, and true downstream applications consume one
exact basis.  This file deliberately proves transport/runtime behavior rather
than duplicating reader implementation.
"""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping, Optional
from unittest.mock import patch

import pytest

from _thinkprogram._iomicrosTM.tiny_helpers import assert_dead_json
from __exceptions.engine import InvalidExternalFillError
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
)
from _thinksessions.run.run_from_here import (
    UserAction,
    dispatch_live_session_action,
    dispatch_live_session_action_with_chain_reaction,
    get_live_session_events,
    get_live_session_events_since,
    get_live_session_latest_event_seq,
)
from _thinksessions.run.runme_surfaces_out.helpers_event_read import (
    CONTROLLER_LOOP_EVENT_KIND_V1,
    SESSION_EVENT_KIND_V1,
)

from ._event_trident_downstream_readers import (
    TridentStreamBuilderV1,
    TridentV1,
    build_trident_log_v1,
    controller_A_v1,
    controller_U_v1,
    datum_states_by_id_v1,
    dispatch_context_v1,
    semantic_errors_v1,
    thaw_json_v1,
)
from ._fixtures_facade_run import (
    facade_note_program_v1,
    launch_facade_note_session_v1,
    two_note_program_v1,
)


EVENTS_ONLY_REJECTION_KEYS = {
    "kind", "session_id", "dispatcher_identity_id", "dispatcher_role",
    "events_only", "ok", "applied", "rejected", "rejection_kind",
    "dispatch_outcome", "write_committed", "event_kind", "finished",
    "last_error", "system_error", "dispatch_staleness",
}
STALENESS_RECEIPT_KEYS = {
    "kind", "checked", "outcome", "reason", "supplied_event_seq",
    "observed_event_seq", "scope_last_changed_seq", "target_last_changed_seq",
    "target_count",
}


def _dispatch(
    *,
    session_id: str,
    action: UserAction = UserAction.STEP,
    identity_id: Optional[str] = "dispatch-trident-e2e",
    role: Optional[str] = "writer",
    **kwargs: Any,
) -> dict[str, Any]:
    return dispatch_live_session_action(
        session_id=session_id,
        action=action,
        identity_id=identity_id,
        role=role,
        **kwargs,
    )


def _queue_snapshot(session_id: str) -> tuple[int, list[dict[str, Any]]]:
    return (
        get_live_session_latest_event_seq(session_id=session_id),
        deepcopy(get_live_session_events(session_id=session_id, role=None)),
    )


def _assert_queue_unchanged(
    session_id: str,
    *,
    before_seq: int,
    before_events: list[dict[str, Any]],
) -> None:
    assert get_live_session_latest_event_seq(session_id=session_id) == before_seq
    assert get_live_session_events(session_id=session_id, role=None) == before_events


def _assert_exact_events_only_rejection(
    packet: Mapping[str, Any], *, kind: str, rejection_kind: str
) -> None:
    assert set(packet) == EVENTS_ONLY_REJECTION_KEYS
    assert packet["kind"] == kind
    assert packet["events_only"] is True
    assert packet["ok"] is False
    assert packet["applied"] is False
    assert packet["rejected"] is True
    assert packet["rejection_kind"] == rejection_kind
    assert packet["dispatch_outcome"] == "stale_rejected"
    assert packet["write_committed"] is False
    assert packet["event_kind"] is None
    assert packet["finished"] is False
    assert packet["last_error"] is None
    assert packet["system_error"] is None
    assert packet["dispatcher_identity_id"] is None
    assert packet["dispatcher_role"] is None
    assert set(packet["dispatch_staleness"]) == STALENESS_RECEIPT_KEYS
    assert packet["dispatch_staleness"]["outcome"] == "rejected"
    assert packet["dispatch_staleness"]["reason"] == rejection_kind


def _two_step_note_program_v1() -> dict[str, Any]:
    program = deepcopy(facade_note_program_v1())
    first = deepcopy(program["run"]["program"]["flow"][0])
    second = deepcopy(first)
    first.update(id="note_step_one", title="Note step one")
    second.update(id="note_step_two", title="Note step two")
    program["run"]["program"]["flow"] = [first, second]
    return program


def _last_trident(session_id: str) -> TridentV1:
    log = build_trident_log_v1(
        get_live_session_events(session_id=session_id, role=None)
    )
    assert log.ordered
    return log.ordered[-1]


# 01-04. Eventless preflight partition -------------------------------------


@pytest.mark.parametrize(
    ("cursor", "expected"),
    [(True, "invalid_event_cursor"), (1, "future_event_cursor")],
)
def test_01_events_only_cursor_rejections_are_exact_and_eventless(
    cursor: Any, expected: str
) -> None:
    sid = launch_facade_note_session_v1()
    before_seq, before_events = _queue_snapshot(sid)
    packet = _dispatch(
        session_id=sid,
        events_only=True,
        my_current_event_seq_number=cursor,
    )
    _assert_exact_events_only_rejection(
        packet,
        kind="live_session_events_only_dispatch_receipt_v1",
        rejection_kind=expected,
    )
    _assert_queue_unchanged(sid, before_seq=before_seq, before_events=before_events)


def test_02_events_only_stale_scope_and_target_rejections_are_exact() -> None:
    sid_scope = launch_facade_note_session_v1()
    _dispatch(session_id=sid_scope, my_current_event_seq_number=0)
    before_seq, before_events = _queue_snapshot(sid_scope)
    stale_scope = _dispatch(
        session_id=sid_scope,
        user_fill={"note": {"text": "keep-open: old-scope"}},
        events_only=True,
        my_current_event_seq_number=0,
    )
    _assert_exact_events_only_rejection(
        stale_scope,
        kind="live_session_events_only_dispatch_receipt_v1",
        rejection_kind="stale_scope_changed",
    )
    _assert_queue_unchanged(
        sid_scope, before_seq=before_seq, before_events=before_events
    )

    sid_target = launch_facade_note_session_v1()
    _dispatch(session_id=sid_target)
    cursor = get_live_session_latest_event_seq(session_id=sid_target)
    committed = _dispatch(
        session_id=sid_target,
        user_fill={"note": {"text": "keep-open: first-writer"}},
        my_current_event_seq_number=cursor,
    )
    assert committed["write_committed"] is True
    before_seq, before_events = _queue_snapshot(sid_target)
    stale_target = _dispatch(
        session_id=sid_target,
        user_fill={"note": {"text": "keep-open: stale-writer"}},
        events_only=True,
        my_current_event_seq_number=cursor,
    )
    _assert_exact_events_only_rejection(
        stale_target,
        kind="live_session_events_only_dispatch_receipt_v1",
        rejection_kind="stale_conflict",
    )
    _assert_queue_unchanged(
        sid_target, before_seq=before_seq, before_events=before_events
    )


def test_03_chain_events_only_preflight_rejection_changes_only_receipt_kind() -> None:
    sid = launch_facade_note_session_v1(chainreactioned=True)
    before_seq, before_events = _queue_snapshot(sid)
    packet = dispatch_live_session_action_with_chain_reaction(
        session_id=sid,
        action=UserAction.STEP,
        identity_id="chain-preflight-e2e",
        role="writer",
        events_only=True,
        my_current_event_seq_number=1,
    )
    _assert_exact_events_only_rejection(
        packet,
        kind="live_session_events_only_chain_dispatch_receipt_v1",
        rejection_kind="future_event_cursor",
    )
    _assert_queue_unchanged(sid, before_seq=before_seq, before_events=before_events)


def test_04_role_and_request_shape_preflight_exceptions_are_eventless() -> None:
    sid = launch_facade_note_session_v1()
    _dispatch(session_id=sid)
    before_seq, before_events = _queue_snapshot(sid)
    with pytest.raises(PermissionError, match="note"):
        _dispatch(
            session_id=sid,
            role="auditor",
            user_fill={"note": {"text": "blocked"}},
            events_only=True,
        )
    _assert_queue_unchanged(sid, before_seq=before_seq, before_events=before_events)

    with pytest.raises(InvalidExternalFillError, match="Invalid fill"):
        _dispatch(
            session_id=sid,
            user_signal={
                "datum_id": "note",
                "kind": "touch",
                "info": ["not", "a", "mapping"],
            },
            events_only=True,
        )
    _assert_queue_unchanged(sid, before_seq=before_seq, before_events=before_events)


# 05-16. Canonical structure, taxonomy, identity, and projection -----------


def test_05_first_step_is_exact_ATSTART_to_first_span_trident() -> None:
    sid = launch_facade_note_session_v1()
    packet = _dispatch(session_id=sid, events_only=True)
    assert packet["dispatch_outcome"] == "applied"
    assert packet["write_committed"] is False
    trident = _last_trident(sid)
    start_U = controller_U_v1(trident.start)
    end_U = controller_U_v1(trident.end)
    assert trident.transition == "N->S"
    assert trident.outcome == "success"
    assert start_U["kind"] == "ATSTART"
    assert "datum_widgets_on_this_span" not in start_U
    assert end_U["kind"] == "MANUALFILLNEEDEDSTEP"
    assert end_U["datum_widgets_on_this_span"] == ("note",)
    assert controller_A_v1(trident.start) == {"fill": {}, "signal": None}
    assert controller_A_v1(trident.end) == controller_A_v1(trident.start)
    assert trident.start["payload"]["fill"] == trident.start["payload"]["A"]["fill"]
    assert trident.start["payload"]["signal"] == trident.start["payload"]["A"]["signal"]
    assert trident.end["payload"]["fill"] == trident.end["payload"]["A"]["fill"]
    assert trident.end["payload"]["signal"] == trident.end["payload"]["A"]["signal"]


def test_06_semantic_rejection_is_successful_same_scope_trident() -> None:
    sid = launch_facade_note_session_v1(program=two_note_program_v1())
    _dispatch(session_id=sid)
    packet = _dispatch(
        session_id=sid,
        user_fill={"alpha": {"text": ""}, "beta": {"text": ""}},
    )
    assert packet["dispatch_outcome"] == "semantic_rejected"
    assert packet["write_committed"] is False
    trident = _last_trident(sid)
    assert trident.transition == "S->S"
    assert trident.outcome == "semantic_rejected"
    assert len(trident.informative) == 2
    assert all(
        event["kind"] == "datum_lifecycle_event_v1"
        for event in trident.informative
    )
    assert [event["event_seq"] for event in trident.informative] == list(
        range(trident.start_seq + 1, trident.end_seq)
    )
    assert set(semantic_errors_v1(trident)) == {"alpha", "beta"}
    assert trident.end["payload"]["outcome"] == "success"
    assert trident.end["payload"]["result"]["last_error"] == (
        trident.end["payload"]["U"]["last_error"]
    )


def test_07_semantic_good_reexplosion_is_success_same_scope_with_messages() -> None:
    sid = launch_facade_note_session_v1()
    _dispatch(session_id=sid)
    packet = _dispatch(
        session_id=sid,
        user_fill={"note": {"text": "keep-open: exact-same-span"}},
    )
    assert packet["dispatch_outcome"] == "applied"
    assert packet["write_committed"] is True
    trident = _last_trident(sid)
    assert trident.transition == "S->S"
    assert trident.outcome == "success"
    messages = [
        event
        for event in trident.informative
        if event.get("kind") == SESSION_EVENT_KIND_V1
        and event.get("name") == "datum.message"
    ]
    assert messages
    assert any(
        "accepted and kept open" in str(event["payload"]["message"]["text"])
        for event in messages
    )


def test_08_forward_lifecycle_covers_N_to_S_S1_to_S2_and_S_to_N() -> None:
    sid = launch_facade_note_session_v1(program=_two_step_note_program_v1())
    _dispatch(session_id=sid)
    _dispatch(session_id=sid, user_fill={"note": {"text": "accepted step one"}})
    _dispatch(session_id=sid, user_fill={"note": {"text": "accepted step two"}})
    log = build_trident_log_v1(
        get_live_session_events(session_id=sid, role=None)
    )
    assert [trident.transition for trident in log.ordered] == [
        "N->S", "S1->S2", "S->N",
    ]
    assert [trident.outcome for trident in log.ordered] == [
        "success", "success", "success",
    ]
    assert controller_U_v1(log.ordered[1].end) == controller_U_v1(
        log.ordered[2].start
    )
    completed = controller_U_v1(log.ordered[-1].end)
    assert completed["kind"] == "ATCOMPLETION"
    assert "datum_widgets_on_this_span" not in completed


def test_09_initial_system_error_can_form_total_N_to_N_relation() -> None:
    sid = launch_facade_note_session_v1()
    api = get_concrete_session_api()
    with patch.object(
        api,
        "step_session",
        side_effect=RuntimeError("synthetic initial failure before scope entry"),
    ):
        packet = _dispatch(session_id=sid)
    assert packet["dispatch_outcome"] == "system_error"
    trident = _last_trident(sid)
    assert trident.outcome == "system_error"
    assert trident.transition == "N->N"
    assert controller_U_v1(trident.start)["kind"] == "ATSTART"
    assert controller_U_v1(trident.end)["kind"] == "ATSTART"


def test_10_system_error_closes_envelope_and_overlays_scope_relation() -> None:
    sid = launch_facade_note_session_v1()
    _dispatch(session_id=sid)
    api = get_concrete_session_api()
    with patch.object(
        api,
        "step_session",
        side_effect=RuntimeError("synthetic trident system failure"),
    ):
        packet = _dispatch(
            session_id=sid,
            user_fill={"note": {"text": "never committed"}},
        )
    assert packet["ok"] is False
    assert packet["applied"] is True
    assert packet["rejected"] is False
    assert packet["dispatch_outcome"] == "system_error"
    assert packet["write_committed"] is False
    trident = _last_trident(sid)
    assert trident.outcome == "system_error"
    assert trident.transition == "S->S"
    assert trident.end["payload"]["system_error"]["exception_type"] == "RuntimeError"
    assert trident.start["dispatch_id"] == trident.end["dispatch_id"]


def test_11_consecutive_tridents_reuse_previous_end_U() -> None:
    sid = launch_facade_note_session_v1()
    _dispatch(session_id=sid)
    _dispatch(session_id=sid, user_fill={"note": {"text": "keep-open: continuity"}})
    log = build_trident_log_v1(
        get_live_session_events(session_id=sid, role=None)
    )
    assert len(log.ordered) == 2
    assert controller_U_v1(log.ordered[0].end) == controller_U_v1(
        log.ordered[1].start
    )


def test_12_Di_reader_exposes_ownership_vector_and_latest_shell() -> None:
    sid = launch_facade_note_session_v1(program=two_note_program_v1())
    _dispatch(session_id=sid)
    U = controller_U_v1(_last_trident(sid).end)
    by_id = datum_states_by_id_v1(U)
    assert list(by_id) == list(U["step"]["span_owns"])
    assert set(by_id) == {"alpha", "beta"}
    for datum_id, row in by_id.items():
        assert row["kind"] == "universal_ui_datum_state_v1"
        assert row["datum_id"] == datum_id
        assert isinstance(row["shell"], Mapping)
        assert isinstance(row["semantic_validation"], Mapping)
        assert isinstance(row["lifecycle"], Mapping)
        assert isinstance(row["originating_step"], Mapping)
        assert row["is_authoritative"] is True
        assert row["is_pending"] is True


def test_13_generated_chain_dispatch_context_is_end_only_and_lossless() -> None:
    sid = launch_facade_note_session_v1(chainreactioned=True)
    dispatch_live_session_action_with_chain_reaction(
        session_id=sid,
        action=UserAction.STEP,
        identity_id="manual-chain-root",
        role="writer",
    )
    log = build_trident_log_v1(
        get_live_session_events(session_id=sid, role=None)
    )
    generated_by_actor = [
        trident
        for trident in log.ordered
        if str(trident.start["dispatcher_identity_id"]).startswith("funkedauto-")
    ]
    assert generated_by_actor
    assert all(dispatch_context_v1(t) is not None for t in generated_by_actor)
    generated_by_context = [t for t in log.ordered if dispatch_context_v1(t)]
    assert generated_by_context == generated_by_actor
    for trident in generated_by_actor:
        assert "dispatch_context" not in trident.start["payload"]
        context = dispatch_context_v1(trident)
        assert isinstance(context, Mapping)
        assert_dead_json(thaw_json_v1(context), path="e2e.generated_dispatch_context")
        lowered_keys = [str(key).lower() for key in context]
        assert any("version" in key for key in lowered_keys)
        assert any("role" in key for key in lowered_keys)
        assert any("receipt" in key for key in lowered_keys)
        assert controller_A_v1(trident.end) == controller_A_v1(trident.start)
    direct = [
        t for t in log.ordered
        if not str(t.start["dispatcher_identity_id"]).startswith("funkedauto-")
    ]
    assert direct
    assert all(dispatch_context_v1(t) is None for t in direct)


def test_14_fully_hidden_projected_A_forms_valid_local_trident() -> None:
    sid = launch_facade_note_session_v1()
    _dispatch(session_id=sid, identity_id="writer-visible")
    _dispatch(
        session_id=sid,
        identity_id="writer-visible",
        user_fill={"note": {"text": "keep-open: hidden from auditor"}},
    )
    canonical = build_trident_log_v1(
        get_live_session_events(session_id=sid, role=None)
    )
    projected = build_trident_log_v1(
        get_live_session_events(session_id=sid, role="auditor"),
        projected=True,
    )
    assert len(projected.ordered) == len(canonical.ordered)
    hidden = projected.ordered[-1]
    assert hidden.dispatch_id is None
    assert hidden.local_id.startswith("projected:")
    assert controller_A_v1(hidden.start) is None
    assert controller_A_v1(hidden.end) is None
    assert hidden.start["dispatcher_identity_id"] is None
    assert hidden.end["dispatcher_identity_id"] is None
    assert hidden.start["dispatcher_role"] is None
    assert hidden.end["dispatcher_role"] is None
    assert hidden.informative == ()
    page = get_live_session_events_since(
        session_id=sid,
        role="auditor",
        identity_id="auditor-reader",
        after_event_seq=0,
        limit=None,
    )
    assert page["next_after_event_seq"] == get_live_session_latest_event_seq(
        session_id=sid
    )
    assert page["visibility_receipt"]["hidden_event_count"] > 0


def test_16_STEP_UNDO_REDO_each_form_complete_canonical_trident() -> None:
    sid = launch_facade_note_session_v1()
    _dispatch(session_id=sid)
    _dispatch(session_id=sid, user_fill={"note": {"text": "accepted before undo-redo"}})
    _dispatch(session_id=sid, action=UserAction.UNDO)
    _dispatch(session_id=sid, action=UserAction.REDO)
    log = build_trident_log_v1(
        get_live_session_events(session_id=sid, role=None)
    )
    assert [trident.action_name for trident in log.ordered] == [
        "STEP", "STEP", "UNDO", "REDO",
    ]
    assert all(
        trident.start["dispatch_id"] == trident.end["dispatch_id"]
        for trident in log.ordered
    )
    assert all(
        trident.start["dispatcher_identity_id"]
        == trident.end["dispatcher_identity_id"]
        for trident in log.ordered
    )
    assert controller_U_v1(log.ordered[-1].end)["kind"] == "ATCOMPLETION"


# 17-21. One-pass indexes, immutability, bounded residuals, docs ------------


def test_17_one_pass_and_incremental_builds_have_same_complete_indexes() -> None:
    sid = launch_facade_note_session_v1()
    _dispatch(session_id=sid)
    _dispatch(session_id=sid, user_fill={"note": {"text": ""}})
    _dispatch(session_id=sid, user_fill={"note": {"text": "keep-open: indexed"}})
    _dispatch(session_id=sid, action=UserAction.UNDO)
    events = get_live_session_events(session_id=sid, role=None)
    one_pass = build_trident_log_v1(events)
    builder = TridentStreamBuilderV1()
    for event in events:
        builder.feed(event)
    incremental = builder.snapshot()

    assert incremental.events_seen == len(events)
    assert [t.local_id for t in incremental.ordered] == [
        t.local_id for t in one_pass.ordered
    ]
    assert set(incremental.by_dispatch_id) == set(one_pass.by_dispatch_id)
    assert {
        key: [t.local_id for t in value]
        for key, value in incremental.by_action_name.items()
    } == {
        key: [t.local_id for t in value]
        for key, value in one_pass.by_action_name.items()
    }
    assert len(incremental.by_action_name["STEP"]) == 3
    assert len(incremental.by_action_name["UNDO"]) == 1
    for trident in incremental.ordered:
        assert incremental.by_local_id[trident.local_id] is trident
        assert incremental.by_dispatch_id[trident.dispatch_id] is trident
        assert controller_A_v1(trident.start) == controller_A_v1(trident.end)
        assert trident.start["payload"]["fill"] == trident.start["payload"]["A"]["fill"]
        assert trident.end["payload"]["signal"] == trident.end["payload"]["A"]["signal"]
    active = [t for t in incremental.ordered if t.source_scope.active]
    assert active
    for trident in active:
        assert trident in incremental.by_source_span_id[trident.source_scope.span_id]


def test_18_immutable_snapshot_rejects_index_event_and_sequence_mutation() -> None:
    sid = launch_facade_note_session_v1()
    _dispatch(session_id=sid)
    log = build_trident_log_v1(
        get_live_session_events(session_id=sid, role=None)
    )
    trident = log.ordered[0]
    with pytest.raises(TypeError):
        log.by_local_id["new"] = trident  # type: ignore[index]
    with pytest.raises(TypeError):
        trident.start["phase"] = "changed"  # type: ignore[index]
    with pytest.raises(AttributeError):
        trident.informative.append({})  # type: ignore[attr-defined]


def test_19_bounded_window_may_begin_mid_envelope_without_fabrication() -> None:
    sid = launch_facade_note_session_v1()
    _dispatch(session_id=sid)
    for index in range(20):
        _dispatch(
            session_id=sid,
            user_signal={
                "datum_id": "note",
                "kind": "touch",
                "info": {"index": index},
            },
            events_only=True,
        )
    events = get_live_session_events(session_id=sid, role=None)
    assert 0 < len(events) <= 32
    assert int(events[0]["event_seq"]) > 1
    window = list(events)
    if (
        window[0].get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
        and window[0].get("phase") == "start"
    ):
        window = window[1:]
    log = build_trident_log_v1(window)
    assert log.events_seen == len(window)
    assert log.ordered
    assert log.orphan_events or log.orphan_ends or log.open_suffix is not None


def test_20_reader_output_thaws_to_dead_json_and_indexes_authored_rank() -> None:
    sid = launch_facade_note_session_v1()
    _dispatch(session_id=sid)
    log = build_trident_log_v1(
        get_live_session_events(session_id=sid, role=None)
    )
    trident = log.ordered[0]
    assert trident.destination_span_rank == 0
    rank_key = (trident.destination_scope.form_id, 0)
    assert trident in log.by_destination_span_rank[rank_key]
    thawed = thaw_json_v1(trident.end)
    assert_dead_json(thawed, path="e2e.trident.end")
    json.dumps(thawed, sort_keys=True)

