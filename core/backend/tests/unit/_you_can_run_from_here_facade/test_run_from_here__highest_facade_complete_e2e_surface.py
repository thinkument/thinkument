from __future__ import annotations

"""
run_from_here Highest-Facade E2E Sheet
======================================

This sheet proves that higher apps can use only:

    _thinksessions.run.run_from_here

for session creation, static ThinkProgramTM reading, direct live dispatch,
canonical queue inspection, stateless sequence-window reads, bounded reports,
and rendered state.

The point is not to retest every lower engine detail. The point is to prove the
Markov blanket:

    app code
      -> _thinksessions.run.run_from_here
      -> authored ThinkProgramTM session
      -> canonical events / reports / dispatch packets

without importing lower engine/controller/service seams.

The one lower session-API import is test instrumentation used only to append a
location-qualified informative event. All normal creation, dispatch, polling,
reporting, and rendering behavior is exercised through _thinksessions.run.run_from_here.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping
from unittest.mock import patch

import pytest

from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import (
    get_concrete_session_api,
)
from _thinkprogram.thinkprogramTM.api import LANG_THINK_PROGRAM_V1
from _thinksessions.run.run_from_here import (
    UserAction,
    create_live_session_from_program,
    describe_think_program,
    dispatch_live_session_action as _dispatch_live_session_action,
    dispatch_live_session_action_with_chain_reaction as _dispatch_live_session_action_with_chain_reaction,
    get_live_session_context,
    get_live_session_current_report,
    get_live_session_events,
    get_live_session_events_since,
    get_live_session_latest_event_seq,
    get_live_session_outputs_report,
    get_live_session_progress_report,
    query_live_session,
    render_live_session_state,
)
from _thinksessions.sesh_metadata.sesh_metadata_surface_puppeteering import (
    PUPPETEERING_OVERLAY_KEY_V1,
    PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
)

from ._fixtures_facade_run import (
    DEFAULT_DISPATCHER_IDENTITY_ID,
    PROGRAM_ID,
    facade_note_program_v1,
    facade_session_metadata_v1,
    launch_facade_note_session_v1,
    register_facade_run_fixture_v1,
)


def _joint_puppeteering_sources_v1(
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    One shared symbol plus one SM-only symbol.

    The authored puppet intentionally disagrees with each symbol default so
    merge_onto and take_over are behaviorally distinguishable.
    """
    shared_default = {
        "roles": ["writer"],
        "events_window": 12,
    }
    shared_authored = {
        "roles": ["auditor"],
        "events_window": 5,
    }

    program = facade_note_program_v1()
    program["symbols"]["joint.surface"] = {
        "value": shared_default,
        "parametrize": True,
    }
    program["puppeteering"]["joint.surface"] = deepcopy(
        shared_authored
    )
    program["run"]["program"]["widgets"]["note"]["roles"] = (
        "$joint.surface.roles"
    )

    metadata = facade_session_metadata_v1(chainreactioned=False)
    metadata["symbols"] = {
        "joint.surface": {
            "value": shared_default,
            "parametrize": True,
        },
        "session.max_fields": {
            "value": 1024,
            "parametrize": True,
        },
    }
    metadata["puppeteering"] = {
        "joint.surface": deepcopy(shared_authored),
        "session.max_fields": 64,
    }
    metadata["manual_io"] = {
        "persistence": "disabled",
        "include_forms_emitted_order_in_ctx": True,
        "max_fields_per_submit": "$session.max_fields",
    }
    metadata["session_storage"] = {
        "events_snapshot_window": "$joint.surface.events_window",
    }

    return program, metadata


def dispatch_live_session_action(**kwargs: Any) -> Dict[str, Any]:
    kwargs.setdefault(
        "identity_id",
        DEFAULT_DISPATCHER_IDENTITY_ID,
    )
    return _dispatch_live_session_action(**kwargs)


def dispatch_live_session_action_with_chain_reaction(
    **kwargs: Any,
) -> Dict[str, Any]:
    kwargs.setdefault(
        "identity_id",
        DEFAULT_DISPATCHER_IDENTITY_ID,
    )
    return _dispatch_live_session_action_with_chain_reaction(**kwargs)


def _event_ids(events: list[Mapping[str, Any]]) -> list[str]:
    return [str(event["event_id"]) for event in events]


def _assert_staleness_allowed(
    packet: Mapping[str, Any],
    *,
    reason: str,
) -> None:
    assert packet["kind"] == "live_session_dispatch_result_v1"
    assert packet["ok"] is True
    assert packet["applied"] is True
    assert packet["rejected"] is False
    assert packet["rejection_kind"] is None

    receipt = packet["dispatch_staleness"]
    assert receipt["kind"] == "live_session_dispatch_staleness_receipt_v1"
    assert receipt["outcome"] == "allowed"
    assert receipt["reason"] == reason


def _assert_staleness_rejected(
    packet: Mapping[str, Any],
    *,
    reason: str,
) -> None:
    assert packet["kind"] == "live_session_dispatch_rejected_v1"
    assert packet["ok"] is False
    assert packet["applied"] is False
    assert packet["rejected"] is True
    assert packet["rejection_kind"] == reason
    assert packet["event_kind"] is None
    assert packet["finished"] is False
    assert packet["last_error"] is None
    assert packet["dispatch_outcome"] == "stale_rejected"
    assert packet["write_committed"] is False

    receipt = packet["dispatch_staleness"]
    assert receipt["outcome"] == "rejected"
    assert receipt["reason"] == reason


def _poll_canonical_until_caught_up_v1(
    *,
    session_id: str,
    role: str | None,
    identity_id: str,
    cursor: int,
    page_limit: int = 2,
) -> tuple[int, list[Dict[str, Any]], int]:
    """
    Test-only realization of the two-level polling pattern.

    Outer poll:
        fetch only scalar A.

    Inner catch-up loop:
        fetch bounded event pages only while C < A.
    """
    C = int(cursor)
    scalar_polls = 1
    A = get_live_session_latest_event_seq(session_id=session_id)

    if A == C:
        return C, [], scalar_polls

    received: list[Dict[str, Any]] = []

    while C < A:
        page = get_live_session_events_since(
            session_id=session_id,
            role=role,
            identity_id=identity_id,
            after_event_seq=C,
            limit=page_limit,
        )

        assert page["after_event_seq"] == C
        assert page["session_latest_event_seq"] >= A
        assert page["next_after_event_seq"] >= C

        next_C = int(page["next_after_event_seq"])
        assert next_C > C, (
            "catch-up polling must advance through visible or acknowledged "
            "role-hidden canonical positions"
        )

        received.extend(page["events"])
        C = next_C
        A = int(page["session_latest_event_seq"])

    return C, received, scalar_polls


def test_dispatch_receipt_carries_normalized_dispatch_actor() -> None:
    sid = launch_facade_note_session_v1()

    packet = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="writer-device-7",
        events_only=True,
    )

    assert packet["dispatcher_identity_id"] == "writer-device-7"
    assert packet["dispatcher_role"] == "writer"


def test_chain_generated_dispatches_derive_actor_from_initial_identity() -> None:
    sid = launch_facade_note_session_v1(chainreactioned=True)

    dispatch_live_session_action_with_chain_reaction(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="manual-client-11",
        events_only=True,
    )

    controller = [
        event
        for event in get_live_session_events(
            session_id=sid,
            role=None,
        )
        if event["kind"] == "controller_loop_event_v1"
    ]
    assert controller

    by_dispatch: dict[str, list[Mapping[str, Any]]] = {}
    for event in controller:
        by_dispatch.setdefault(str(event["dispatch_id"]), []).append(event)

    actors = {
        (
            rows[0]["dispatcher_identity_id"],
            rows[0]["dispatcher_role"],
        )
        for rows in by_dispatch.values()
    }

    assert ("manual-client-11", "writer") in actors
    assert any(
        str(identity).startswith("funkedauto-")
        and str(identity).endswith("-manual-client-11")
        for identity, _role in actors
    )

    for rows in by_dispatch.values():
        assert len(rows) == 2
        assert [row["phase"] for row in rows] == ["start", "end"]
        assert (
            rows[0]["dispatcher_identity_id"]
            == rows[1]["dispatcher_identity_id"]
        )
        assert rows[0]["dispatcher_role"] == rows[1]["dispatcher_role"]


def test_funked_identity_is_not_recursively_prefixed() -> None:
    sid = launch_facade_note_session_v1(chainreactioned=True)

    dispatch_live_session_action_with_chain_reaction(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="root-actor",
    )

    generated = [
        str(event["dispatcher_identity_id"])
        for event in get_live_session_events(session_id=sid, role=None)
        if event["kind"] == "controller_loop_event_v1"
        and str(event["dispatcher_identity_id"]).startswith("funkedauto-")
    ]

    assert generated
    assert all(identity.count("funkedauto-") == 1 for identity in generated)
    assert all(identity.endswith("-root-actor") for identity in generated)


def test_static_program_description_is_available_before_session_creation() -> None:
    register_facade_run_fixture_v1()
    description = describe_think_program(program=facade_note_program_v1())

    assert description["kind"] == "think_program_static_description_v1"
    assert description["id"] == PROGRAM_ID
    assert description["counts"] == {
        "widgets": 1,
        "flow_steps": 1,
        "roles": 1,
    }
    assert description["roles"] == ["writer"]
    assert description["widgets"][0]["id"] == "note"
    assert description["flow"][0]["widgets"] == ["note"]


def test_one_C_routes_shared_and_SM_only_symbols_to_P_and_SM() -> None:
    register_facade_run_fixture_v1()
    program, metadata = _joint_puppeteering_sources_v1()
    program_before = deepcopy(program)
    metadata_before = deepcopy(metadata)

    created = create_live_session_from_program(
        program=program,
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={
            # Same assignment is consumed by P.roles and SM storage.
            "joint.surface": {
                "roles": ["writer"],
                "events_window": 7,
            },
            # Legal under strict=True because SM exposes it even though P does not.
            "session.max_fields": 17,
        },
        session_metadata=metadata,
    )
    assert created["ok"] is True
    sid = str(created["session_id"])

    mounted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    assert mounted["dispatch_outcome"] == "applied"

    U = get_live_session_context(
        session_id=sid,
        role=None,
    )
    resolved_metadata = U["session_metadata"]
    assert (
        resolved_metadata["session_storage"]["events_snapshot_window"]
        == 7
    )
    assert (
        resolved_metadata["manual_io"]["max_fields_per_submit"]
        == 17
    )
    assert "symbols" not in resolved_metadata
    assert "puppeteering" not in resolved_metadata

    # P received the exact same shared C assignment. The authored P puppet
    # would have made note auditor-owned; C changed it to writer-owned.
    with pytest.raises(PermissionError, match="note"):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="auditor",
            user_fill={"note": {"text": "blocked-auditor"}},
        )

    accepted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: joint-C-writer"}},
    )
    assert accepted["dispatch_outcome"] == "applied"
    assert accepted["write_committed"] is True

    # Joint routing is functional, never source mutation.
    assert program == program_before
    assert metadata == metadata_before


def test_joint_take_over_replaces_both_authored_puppeteering_pockets() -> None:
    register_facade_run_fixture_v1()
    program, metadata = _joint_puppeteering_sources_v1()

    created = create_live_session_from_program(
        program=program,
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={
            PUPPETEERING_OVERLAY_KEY_V1: {
                "mode": PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
                "strict": True,
            },
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

    U = get_live_session_context(
        session_id=sid,
        role=None,
    )
    resolved_metadata = U["session_metadata"]

    # SM authored puppets were 5 and 64; takeover removed them and restored
    # each declaration's own defaults.
    assert (
        resolved_metadata["session_storage"]["events_snapshot_window"]
        == 12
    )
    assert (
        resolved_metadata["manual_io"]["max_fields_per_submit"]
        == 1024
    )

    # P authored puppet made note auditor-owned; its default is writer-owned.
    with pytest.raises(PermissionError, match="note"):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="auditor",
            user_fill={"note": {"text": "blocked-after-takeover"}},
        )

    accepted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: default-writer"}},
    )
    assert accepted["write_committed"] is True


def test_joint_strict_C_rejects_name_exposed_by_neither_surface() -> None:
    register_facade_run_fixture_v1()
    program, metadata = _joint_puppeteering_sources_v1()

    with pytest.raises(
        ValueError,
        match="unknown symbol",
    ):
        create_live_session_from_program(
            program=program,
            program_language=LANG_THINK_PROGRAM_V1,
            initial_parameter_overrides={
                "not.exposed.anywhere": 1,
            },
            session_metadata=metadata,
        )


def test_joint_non_strict_C_drops_unknown_and_keeps_valid_SM_name() -> None:
    register_facade_run_fixture_v1()
    program, metadata = _joint_puppeteering_sources_v1()

    created = create_live_session_from_program(
        program=program,
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={
            PUPPETEERING_OVERLAY_KEY_V1: {
                "strict": False,
            },
            "not.exposed.anywhere": {
                "ignored": True,
            },
            "session.max_fields": 19,
        },
        session_metadata=metadata,
    )
    assert created["ok"] is True
    sid = str(created["session_id"])

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        # Authored P puppet remains active because this merge did not assign
        # joint.surface.
        role="auditor",
    )

    U = get_live_session_context(
        session_id=sid,
        role=None,
    )
    assert (
        U["session_metadata"]["manual_io"]["max_fields_per_submit"]
        == 19
    )


def test_plain_dispatch_does_not_perform_hosting_persistence_io() -> None:
    """
    The highest façade owns process-local dispatch semantics only.

    Hosting persistence restoration and saving must be performed by the
    server's coordinated transaction, never unconditionally by this call.
    """
    sid = launch_facade_note_session_v1()

    with patch(
        "_thinkengine.__persistence.repo.SessionRepo.get_aux_json",
        side_effect=AssertionError(
            "plain highest-façade dispatch must not load auxiliary JSON"
        ),
    ), patch(
        "_thinkengine.__persistence.repo.SessionRepo.save_aux_json",
        side_effect=AssertionError(
            "plain highest-façade dispatch must not save auxiliary JSON"
        ),
    ):
        packet = dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
            my_current_event_seq_number=0,
        )

    assert packet["ok"] is True
    assert packet["rejected"] is False


def test_event_queue_is_bounded_recent_window_not_permanent_storage() -> None:
    sid = launch_facade_note_session_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="writer-tab",
        events_only=True,
    )

    for i in range(40):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
            identity_id="writer-tab",
            user_signal={
                "datum_id": "note",
                "kind": "unknown_signal_falls_back_to_fill",
                "info": {"i": i},
            },
            events_only=True,
        )

    queue = get_live_session_events(session_id=sid, role=None)
    latest_five = get_live_session_events(
        session_id=sid,
        role=None,
        limit=5,
    )

    assert 0 < len(queue) <= 32
    assert _event_ids(latest_five) == _event_ids(queue[-5:])

    assert all(
        event["kind"]
        in {
            "controller_loop_event_v1",
            "datum_lifecycle_event_v1",
        }
        for event in queue
    )


def test_events_since_is_stateless_and_uses_canonical_event_seq() -> None:
    sid = launch_facade_note_session_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="writer-tab",
    )

    canonical = get_live_session_events(
        session_id=sid,
        role=None,
    )
    assert canonical

    split_seq = int(canonical[len(canonical) // 2]["event_seq"])
    page = get_live_session_events_since(
        session_id=sid,
        identity_id="writer-tab",
        role="writer",
        after_event_seq=split_seq,
        limit=3,
    )

    expected = [
        event
        for event in get_live_session_events(
            session_id=sid,
            role="writer",
        )
        if int(event["event_seq"]) > split_seq
    ][:3]

    assert page["kind"] == "live_session_events_since_v1"
    assert page["identity_id"] == "writer-tab"
    assert page["events"] == expected
    assert page["session_latest_event_seq"] == int(canonical[-1]["event_seq"])
    assert page["next_after_event_seq"] == (
        int(expected[-1]["event_seq"]) if expected else split_seq
    )

    assert (
        get_live_session_events_since(
            session_id=sid,
            identity_id="writer-tab",
            role="writer",
            after_event_seq=split_seq,
            limit=3,
        )
        == page
    )


def test_latest_event_seq_endpoint_is_tiny_monotonic_and_matches_canonical_tail() -> None:
    sid = launch_facade_note_session_v1()

    assert get_live_session_latest_event_seq(session_id=sid) == 0

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="writer-tab",
        events_only=True,
    )

    first = get_live_session_latest_event_seq(session_id=sid)
    canonical = get_live_session_events(session_id=sid, role=None)

    assert isinstance(first, int)
    assert first > 0
    assert first == int(canonical[-1]["event_seq"])

    for _ in range(10):
        assert get_live_session_latest_event_seq(session_id=sid) == first

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_signal={
            "datum_id": "note",
            "kind": "unknown_signal_falls_back_to_fill",
            "info": {"source": "poller-proof"},
        },
        events_only=True,
    )

    second = get_live_session_latest_event_seq(session_id=sid)
    assert second > first
    assert second == int(
        get_live_session_events(session_id=sid, role=None)[-1]["event_seq"]
    )


def test_events_since_acknowledges_role_hidden_sequence_gaps_without_content() -> None:
    sid = launch_facade_note_session_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="writer-tab",
    )

    canonical = get_live_session_events(session_id=sid, role=None)
    hidden_expected = [
        int(event["event_seq"])
        for event in canonical
        if event["kind"] == "datum_lifecycle_event_v1"
        and event["datum_id"] == "note"
    ]
    assert hidden_expected

    page = get_live_session_events_since(
        session_id=sid,
        identity_id="auditor-poller",
        role="auditor",
        after_event_seq=0,
        limit=None,
    )

    assert all(
        event["kind"] != "datum_lifecycle_event_v1"
        for event in page["events"]
    )
    assert page["session_latest_event_seq"] == get_live_session_latest_event_seq(
        session_id=sid
    )
    assert page["next_after_event_seq"] == page["session_latest_event_seq"]

    receipt = page["visibility_receipt"]
    assert receipt["kind"] == "live_session_event_visibility_receipt_v1"
    assert receipt["role"] == "auditor"
    assert receipt["reason"] == "role_projection"
    assert receipt["hidden_event_count"] == len(hidden_expected)

    expanded: list[int] = []
    for row in receipt["hidden_event_seq_ranges"]:
        expanded.extend(
            range(
                int(row["from_event_seq"]),
                int(row["to_event_seq"]) + 1,
            )
        )
    assert expanded == hidden_expected

    receipt_text = str(receipt)
    assert "note" not in receipt_text
    assert "payload" not in receipt_text


def test_cursor_zero_is_valid_for_a_fresh_session() -> None:
    sid = launch_facade_note_session_v1()
    packet = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=0,
    )
    _assert_staleness_allowed(packet, reason="at_high_water")


def test_dispatch_cursor_equal_to_high_water_is_allowed() -> None:
    sid = launch_facade_note_session_v1()
    C = get_live_session_latest_event_seq(session_id=sid)

    packet = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=C,
    )

    _assert_staleness_allowed(packet, reason="at_high_water")
    assert packet["dispatch_staleness"]["supplied_event_seq"] == C
    assert packet["dispatch_concurrency"]["before_event_seq"] == C
    assert get_live_session_latest_event_seq(session_id=sid) > C


def test_future_dispatch_cursor_is_rejected_without_emitting_events() -> None:
    sid = launch_facade_note_session_v1()
    A = get_live_session_latest_event_seq(session_id=sid)
    queue_before = get_live_session_events(session_id=sid, role=None)

    rejected = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=A + 1,
    )

    _assert_staleness_rejected(
        rejected,
        reason="future_event_cursor",
    )
    assert get_live_session_latest_event_seq(session_id=sid) == A
    assert get_live_session_events(session_id=sid, role=None) == queue_before


@pytest.mark.parametrize(
    "bad",
    [-1, True, "not-an-int", "1", 1.0],
)
def test_invalid_dispatch_cursor_is_rejected_without_dispatch(
    bad: Any,
) -> None:
    sid = launch_facade_note_session_v1()
    A = get_live_session_latest_event_seq(session_id=sid)

    rejected = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=bad,
    )

    _assert_staleness_rejected(
        rejected,
        reason="invalid_event_cursor",
    )
    assert get_live_session_latest_event_seq(session_id=sid) == A


def test_invalid_cursor_receipt_is_exact_and_eventless() -> None:
    sid = launch_facade_note_session_v1()
    A = get_live_session_latest_event_seq(session_id=sid)
    queue_before = get_live_session_events(session_id=sid, role=None)

    rejected = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=True,
    )

    _assert_staleness_rejected(rejected, reason="invalid_event_cursor")
    assert rejected["dispatch_staleness"]["supplied_event_seq"] is None
    assert rejected["dispatch_staleness"]["observed_event_seq"] == A
    assert get_live_session_latest_event_seq(session_id=sid) == A
    assert get_live_session_events(session_id=sid, role=None) == queue_before


def test_omitted_cursor_is_explicitly_unchecked() -> None:
    sid = launch_facade_note_session_v1()

    packet = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )

    receipt = packet["dispatch_staleness"]
    assert receipt["checked"] is False
    assert receipt["outcome"] == "allowed"
    assert receipt["reason"] == "cursor_not_supplied"
    assert receipt["supplied_event_seq"] is None


def test_stale_cursor_is_allowed_when_only_unrelated_events_advanced() -> None:
    sid = launch_facade_note_session_v1()

    mounted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    C = mounted["dispatch_concurrency"]["after_event_seq"]

    api = get_concrete_session_api()
    raw = api.get_session_context(sid)
    api.emit_session_event(
        sid,
        form_id=raw["form_id"],
        frame_id=raw["current_frame_id"],
        span_id=raw["current_span"],
        datum_id="note",
        payload={"audit": True},
        name="test.unrelated.external.activity",
    )
    assert get_live_session_latest_event_seq(session_id=sid) > C

    allowed = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_signal={
            "datum_id": "note",
            "kind": "unknown_signal_falls_back_to_fill",
            "info": {"source": "stale-but-disjoint"},
        },
        my_current_event_seq_number=C,
    )

    _assert_staleness_allowed(
        allowed,
        reason="stale_but_disjoint",
    )


def test_stale_cursor_conflicting_with_same_datum_is_rejected() -> None:
    sid = launch_facade_note_session_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    C = get_live_session_latest_event_seq(session_id=sid)

    first_writer = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={
            "note": {
                "text": "keep-open: writer-1",
            }
        },
        my_current_event_seq_number=C,
    )
    _assert_staleness_allowed(first_writer, reason="at_high_water")
    assert first_writer["write_committed"] is True
    assert first_writer["dispatch_outcome"] == "applied"
    A = get_live_session_latest_event_seq(session_id=sid)

    queue_before_rejection = get_live_session_events(
        session_id=sid,
        role=None,
    )
    second_writer = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={
            "note": {
                "text": "keep-open: writer-2",
            }
        },
        my_current_event_seq_number=C,
    )

    _assert_staleness_rejected(
        second_writer,
        reason="stale_conflict",
    )
    assert second_writer["dispatch_staleness"]["target_last_changed_seq"] == A
    assert get_live_session_latest_event_seq(session_id=sid) == A
    assert (
        get_live_session_events(
            session_id=sid,
            role=None,
        )
        == queue_before_rejection
    )


def test_dotted_and_macro_fill_keys_share_one_canonical_conflict_target() -> None:
    sid = launch_facade_note_session_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    C = get_live_session_latest_event_seq(session_id=sid)

    first = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: first"}},
        my_current_event_seq_number=C,
    )
    assert first["write_committed"] is True
    A = get_live_session_latest_event_seq(session_id=sid)
    queue_before = get_live_session_events(session_id=sid, role=None)

    stale = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={
            "note": {"text": "keep-open: stale"},
            "note.text": "also-stale",
        },
        my_current_event_seq_number=C,
    )
    _assert_staleness_rejected(stale, reason="stale_conflict")
    assert stale["dispatch_staleness"]["target_count"] == 1
    assert stale["dispatch_staleness"]["target_last_changed_seq"] == A
    assert get_live_session_latest_event_seq(session_id=sid) == A
    assert get_live_session_events(session_id=sid, role=None) == queue_before


def test_semantically_rejected_fill_does_not_mark_target_changed() -> None:
    sid = launch_facade_note_session_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    C = get_live_session_latest_event_seq(session_id=sid)

    rejected_semantically = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": ""}},
        my_current_event_seq_number=C,
    )
    assert rejected_semantically["last_error"]
    assert rejected_semantically["dispatch_outcome"] == "semantic_rejected"
    assert rejected_semantically["write_committed"] is False
    assert get_live_session_latest_event_seq(session_id=sid) > C

    accepted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "accepted"}},
        my_current_event_seq_number=C,
    )
    _assert_staleness_allowed(
        accepted,
        reason="stale_but_disjoint",
    )


def test_role_guard_precedes_staleness_and_engine_dispatch() -> None:
    sid = launch_facade_note_session_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    A = get_live_session_latest_event_seq(session_id=sid)
    queue_before = get_live_session_events(session_id=sid, role=None)

    with pytest.raises(PermissionError, match="note"):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="auditor",
            user_fill={"note": {"text": "blocked"}},
            my_current_event_seq_number=A + 1,
        )
    assert get_live_session_latest_event_seq(session_id=sid) == A
    assert get_live_session_events(session_id=sid, role=None) == queue_before

    with pytest.raises(PermissionError, match="note"):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="auditor",
            user_fill={"note": {"text": "blocked"}},
            my_current_event_seq_number=A,
        )

    assert get_live_session_latest_event_seq(session_id=sid) == A
    assert get_live_session_events(session_id=sid, role=None) == queue_before


def test_signal_target_uses_the_same_role_guard_as_fill_target() -> None:
    sid = launch_facade_note_session_v1()
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    A = get_live_session_latest_event_seq(session_id=sid)
    queue_before = get_live_session_events(session_id=sid, role=None)

    with pytest.raises(PermissionError, match="note"):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="auditor",
            user_signal={
                "datum_id": "note",
                "kind": "unknown_signal_falls_back_to_fill",
                "info": {},
            },
            my_current_event_seq_number=A,
        )

    assert get_live_session_latest_event_seq(session_id=sid) == A
    assert get_live_session_events(session_id=sid, role=None) == queue_before


def test_stale_rejection_does_not_invoke_threaded_callbacks() -> None:
    sid = launch_facade_note_session_v1()
    calls: list[Mapping[str, Any]] = []

    rejected = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=1,
        threaded_callbacks={
            "controller_events_callback": lambda event: calls.append(event),
            "explosion_events_callback": lambda event: calls.append(event),
        },
    )

    _assert_staleness_rejected(rejected, reason="future_event_cursor")
    assert calls == []


def test_events_only_success_and_stale_rejection_shapes_are_complete() -> None:
    sid = launch_facade_note_session_v1()
    C = get_live_session_latest_event_seq(session_id=sid)

    success = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        events_only=True,
        my_current_event_seq_number=C,
    )
    assert success["kind"] == "live_session_events_only_dispatch_receipt_v1"
    assert success["events_only"] is True
    assert success["ok"] is True
    assert success["applied"] is True
    assert success["rejected"] is False
    assert success["rejection_kind"] is None
    assert success["dispatch_staleness"]["outcome"] == "allowed"

    stale_scope = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_signal={
            "datum_id": "note",
            "kind": "unknown_signal_falls_back_to_fill",
            "info": {},
        },
        events_only=True,
        my_current_event_seq_number=C,
    )
    assert stale_scope["events_only"] is True
    assert stale_scope["ok"] is False
    assert stale_scope["applied"] is False
    assert stale_scope["rejected"] is True
    assert stale_scope["rejection_kind"] == "stale_scope_changed"
    assert stale_scope["dispatch_outcome"] == "stale_rejected"
    assert stale_scope["write_committed"] is False
    assert stale_scope["dispatch_staleness"]["outcome"] == "rejected"

    stable_C = get_live_session_latest_event_seq(session_id=sid)
    committed = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: events-only-writer-1"}},
        events_only=True,
        my_current_event_seq_number=stable_C,
    )
    assert committed["dispatch_outcome"] == "applied"
    assert committed["write_committed"] is True

    stale_target = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: events-only-writer-2"}},
        events_only=True,
        my_current_event_seq_number=stable_C,
    )
    assert stale_target["events_only"] is True
    assert stale_target["ok"] is False
    assert stale_target["applied"] is False
    assert stale_target["rejected"] is True
    assert stale_target["rejection_kind"] == "stale_conflict"
    assert stale_target["dispatch_outcome"] == "stale_rejected"
    assert stale_target["write_committed"] is False
    assert stale_target["dispatch_staleness"]["outcome"] == "rejected"


def test_stale_scope_change_precedes_target_conflict_classification() -> None:
    sid = launch_facade_note_session_v1()
    C = get_live_session_latest_event_seq(session_id=sid)

    mounted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=C,
    )
    assert mounted["dispatch_outcome"] == "applied"

    rejected = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: old-scope"}},
        my_current_event_seq_number=C,
    )

    _assert_staleness_rejected(
        rejected,
        reason="stale_scope_changed",
    )
    assert rejected["dispatch_staleness"]["scope_last_changed_seq"] > C


def test_signal_only_success_marks_the_signal_datum_changed() -> None:
    sid = launch_facade_note_session_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    C = get_live_session_latest_event_seq(session_id=sid)

    first = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_signal={
            "datum_id": "note",
            "kind": "touch",
            "info": {"writer": 1},
        },
        my_current_event_seq_number=C,
    )
    assert first["dispatch_outcome"] == "applied"
    assert first["write_committed"] is True

    A = get_live_session_latest_event_seq(session_id=sid)
    queue_before = get_live_session_events(session_id=sid, role=None)

    second = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_signal={
            "datum_id": "note",
            "kind": "touch",
            "info": {"writer": 2},
        },
        my_current_event_seq_number=C,
    )
    _assert_staleness_rejected(second, reason="stale_conflict")
    assert second["dispatch_staleness"]["target_last_changed_seq"] == A
    assert get_live_session_latest_event_seq(session_id=sid) == A
    assert get_live_session_events(session_id=sid, role=None) == queue_before


def test_fill_and_signal_share_one_canonical_conflict_target() -> None:
    sid = launch_facade_note_session_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    C = get_live_session_latest_event_seq(session_id=sid)

    signal_write = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_signal={
            "datum_id": "note",
            "kind": "touch",
            "info": {},
        },
        my_current_event_seq_number=C,
    )
    assert signal_write["write_committed"] is True

    stale_fill = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: stale-after-signal"}},
        my_current_event_seq_number=C,
    )
    _assert_staleness_rejected(stale_fill, reason="stale_conflict")


def test_success_status_header_is_stable_for_direct_and_events_only() -> None:
    sid = launch_facade_note_session_v1()
    C = get_live_session_latest_event_seq(session_id=sid)

    direct = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=C,
    )
    for key in (
        "kind",
        "ok",
        "applied",
        "rejected",
        "rejection_kind",
        "dispatch_outcome",
        "write_committed",
        "events_only",
        "session_id",
        "event_kind",
        "finished",
        "last_error",
        "dispatch_staleness",
        "dispatch_concurrency",
        "dispatcher_identity_id",
        "dispatcher_role",
    ):
        assert key in direct

    events_only = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        events_only=True,
    )
    assert set(events_only).issuperset(
        {
            "kind",
            "ok",
            "applied",
            "rejected",
            "rejection_kind",
            "dispatch_outcome",
            "write_committed",
            "events_only",
            "session_id",
            "event_kind",
            "finished",
            "last_error",
            "dispatch_staleness",
            "dispatch_concurrency",
            "dispatcher_identity_id",
            "dispatcher_role",
        }
    )


def test_staleness_rejection_return_shape_has_exact_status_contract() -> None:
    sid = launch_facade_note_session_v1()
    A = get_live_session_latest_event_seq(session_id=sid)

    rejected = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=A + 1,
    )

    required = {
        "kind",
        "ok",
        "applied",
        "rejected",
        "rejection_kind",
        "dispatch_outcome",
        "write_committed",
        "events_only",
        "session_id",
        "event_kind",
        "finished",
        "last_error",
        "dispatch_staleness",
    }
    assert set(rejected) == required
    assert rejected["kind"] == "live_session_dispatch_rejected_v1"
    assert rejected["dispatch_outcome"] == "stale_rejected"
    assert rejected["write_committed"] is False

    receipt_required = {
        "kind",
        "checked",
        "outcome",
        "reason",
        "supplied_event_seq",
        "observed_event_seq",
        "scope_last_changed_seq",
        "target_last_changed_seq",
        "target_count",
    }
    assert set(rejected["dispatch_staleness"]) == receipt_required


def test_dispatch_result_shape_distinguishes_commit_semantic_and_stale() -> None:
    sid = launch_facade_note_session_v1()

    mounted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    C = mounted["dispatch_concurrency"]["after_event_seq"]

    semantic = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": ""}},
        my_current_event_seq_number=C,
    )
    assert semantic["kind"] == "live_session_dispatch_result_v1"
    assert semantic["ok"] is True
    assert semantic["applied"] is True
    assert semantic["rejected"] is False
    assert semantic["rejection_kind"] is None
    assert semantic["dispatch_outcome"] == "semantic_rejected"
    assert semantic["write_committed"] is False
    assert semantic["last_error"]

    committed = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: committed"}},
        my_current_event_seq_number=C,
    )
    assert committed["kind"] == "live_session_dispatch_result_v1"
    assert committed["ok"] is True
    assert committed["applied"] is True
    assert committed["rejected"] is False
    assert committed["dispatch_outcome"] == "applied"
    assert committed["write_committed"] is True

    stale = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: stale"}},
        my_current_event_seq_number=C,
    )
    assert stale["kind"] == "live_session_dispatch_rejected_v1"
    assert stale["ok"] is False
    assert stale["applied"] is False
    assert stale["rejected"] is True
    assert stale["rejection_kind"] == "stale_conflict"
    assert stale["dispatch_outcome"] == "stale_rejected"
    assert stale["write_committed"] is False


def test_chain_dispatch_checks_caller_cursor_once_and_returns_receipt() -> None:
    sid = launch_facade_note_session_v1(chainreactioned=True)
    C = get_live_session_latest_event_seq(session_id=sid)

    packet = dispatch_live_session_action_with_chain_reaction(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=C,
    )

    assert packet["dispatch_staleness"]["outcome"] == "allowed"
    assert packet["dispatch_staleness"]["supplied_event_seq"] == C
    assert "chainreactionTM_receipt" in packet


def test_double_loop_polling_reads_scalar_when_idle_and_events_only_on_change() -> None:
    sid = launch_facade_note_session_v1()

    C = 0
    C, first_events, scalar_polls = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="writer-poller",
        cursor=C,
    )
    assert scalar_polls == 1
    assert C == 0
    assert first_events == []

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=C,
    )

    C, changed_events, scalar_polls = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="writer-poller",
        cursor=C,
        page_limit=1,
    )
    assert scalar_polls == 1
    assert changed_events
    assert C == get_live_session_latest_event_seq(session_id=sid)

    unchanged_C, no_events, scalar_polls = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="writer-poller",
        cursor=C,
    )
    assert scalar_polls == 1
    assert unchanged_C == C
    assert no_events == []


def test_dispatcher_can_enter_high_alert_polling_after_its_own_dispatch() -> None:
    sid = launch_facade_note_session_v1()
    C = 0

    C, _, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="writer-dispatcher-poller",
        cursor=C,
    )

    mounted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=C,
    )
    assert mounted["dispatch_staleness"]["outcome"] == "allowed"

    C, own_dispatch_events, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="writer-dispatcher-poller",
        cursor=C,
        page_limit=2,
    )
    assert own_dispatch_events
    assert C == mounted["dispatch_concurrency"]["after_event_seq"]

    committed = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: insider-dispatch"}},
        my_current_event_seq_number=C,
    )
    assert committed["write_committed"] is True

    C, mutation_events, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="writer-dispatcher-poller",
        cursor=C,
        page_limit=1,
    )
    assert mutation_events
    assert C == committed["dispatch_concurrency"]["after_event_seq"]


def test_two_decentralized_pollers_share_canonical_order_but_keep_own_cursors() -> None:
    sid = launch_facade_note_session_v1()

    writer_C = 0
    auditor_C = 0

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=writer_C,
    )

    writer_C, writer_events, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="writer-poller",
        cursor=writer_C,
        page_limit=2,
    )
    auditor_C, auditor_events, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="auditor",
        identity_id="auditor-poller",
        cursor=auditor_C,
        page_limit=2,
    )

    A = get_live_session_latest_event_seq(session_id=sid)
    assert writer_C == A
    assert auditor_C == A

    writer_seqs = [int(event["event_seq"]) for event in writer_events]
    auditor_seqs = [int(event["event_seq"]) for event in auditor_events]
    assert writer_seqs == sorted(writer_seqs)
    assert auditor_seqs == sorted(auditor_seqs)
    assert len(auditor_events) <= len(writer_events)


def test_disjoint_stale_dispatch_commits_and_conflicting_stale_dispatch_does_not() -> None:
    sid = launch_facade_note_session_v1()

    mounted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    C = int(mounted["dispatch_concurrency"]["after_event_seq"])

    api = get_concrete_session_api()
    raw = api.get_session_context(sid)
    api.emit_session_event(
        sid,
        form_id=raw["form_id"],
        frame_id=raw["current_frame_id"],
        span_id=raw["current_span"],
        datum_id="note",
        payload={"unrelated": True},
        name="test.poller.unrelated.queue.activity",
    )

    disjoint = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: accepted-from-old-C"}},
        my_current_event_seq_number=C,
    )
    assert disjoint["dispatch_staleness"]["reason"] == "stale_but_disjoint"
    assert disjoint["write_committed"] is True

    A = get_live_session_latest_event_seq(session_id=sid)
    queue_before = get_live_session_events(session_id=sid, role=None)

    conflict = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: rejected-from-old-C"}},
        my_current_event_seq_number=C,
    )
    assert conflict["kind"] == "live_session_dispatch_rejected_v1"
    assert conflict["rejection_kind"] == "stale_conflict"
    assert conflict["write_committed"] is False

    assert get_live_session_latest_event_seq(session_id=sid) == A
    assert get_live_session_events(session_id=sid, role=None) == queue_before


def test_many_sessions_have_isolated_high_water_cursors_and_target_indexes() -> None:
    session_ids = [launch_facade_note_session_v1() for _ in range(4)]

    cursors = {
        sid: get_live_session_latest_event_seq(session_id=sid)
        for sid in session_ids
    }
    assert set(cursors.values()) == {0}

    for index, sid in enumerate(session_ids):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
            my_current_event_seq_number=cursors[sid],
        )
        cursors[sid] = get_live_session_latest_event_seq(session_id=sid)

        for other_sid in session_ids:
            if other_sid == sid:
                continue
            if session_ids.index(other_sid) > index:
                assert (
                    get_live_session_latest_event_seq(session_id=other_sid) == 0
                )

    for sid in session_ids:
        assert cursors[sid] > 0
        canonical = get_live_session_events(session_id=sid, role=None)
        assert canonical
        assert int(canonical[-1]["event_seq"]) == cursors[sid]


def test_scope_rejection_is_eventless_and_queue_stable() -> None:
    sid = launch_facade_note_session_v1()
    C = get_live_session_latest_event_seq(session_id=sid)

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=C,
    )

    A = get_live_session_latest_event_seq(session_id=sid)
    queue_before = get_live_session_events(session_id=sid, role=None)

    rejected = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: old-scope"}},
        my_current_event_seq_number=C,
    )

    _assert_staleness_rejected(rejected, reason="stale_scope_changed")
    assert get_live_session_latest_event_seq(session_id=sid) == A
    assert get_live_session_events(session_id=sid, role=None) == queue_before


def test_semantic_rejection_advances_events_but_not_target_change_index() -> None:
    sid = launch_facade_note_session_v1()

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
    assert get_live_session_latest_event_seq(session_id=sid) > C

    accepted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: valid-after-semantic-error"}},
        my_current_event_seq_number=C,
    )
    _assert_staleness_allowed(accepted, reason="stale_but_disjoint")
    assert accepted["write_committed"] is True


def test_dispatcher_poller_round_trip_uses_returned_after_seq_as_alert_target() -> None:
    sid = launch_facade_note_session_v1()
    C = 0

    mounted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        my_current_event_seq_number=C,
        events_only=True,
    )
    dispatch_A = int(mounted["dispatch_concurrency"]["after_event_seq"])
    assert dispatch_A > C

    C, received, scalar_polls = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="writer-round-trip",
        cursor=C,
        page_limit=1,
    )
    assert scalar_polls == 1
    assert received
    assert C == dispatch_A

    committed = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: round-trip"}},
        my_current_event_seq_number=C,
        events_only=True,
    )
    assert committed["dispatch_outcome"] == "applied"
    assert committed["write_committed"] is True

    C, received, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="writer-round-trip",
        cursor=C,
        page_limit=2,
    )
    assert received
    assert C == int(committed["dispatch_concurrency"]["after_event_seq"])


def test_many_dispatcher_pollers_on_many_sessions_remain_isolated() -> None:
    session_ids = [launch_facade_note_session_v1() for _ in range(3)]
    cursors = {
        (sid, client): 0
        for sid in session_ids
        for client in ("writer-a", "writer-b", "auditor")
    }

    for sid in session_ids:
        packet = dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
            my_current_event_seq_number=0,
            events_only=True,
        )
        assert packet["ok"] is True

    for sid in session_ids:
        for client, role in (
            ("writer-a", "writer"),
            ("writer-b", "writer"),
            ("auditor", "auditor"),
        ):
            key = (sid, client)
            cursors[key], events, _ = _poll_canonical_until_caught_up_v1(
                session_id=sid,
                role=role,
                identity_id=f"{sid}:{client}",
                cursor=cursors[key],
                page_limit=1,
            )
            assert cursors[key] == get_live_session_latest_event_seq(
                session_id=sid
            )
            assert [int(e["event_seq"]) for e in events] == sorted(
                int(e["event_seq"]) for e in events
            )

    chosen = session_ids[0]
    others_before = {
        sid: get_live_session_latest_event_seq(session_id=sid)
        for sid in session_ids[1:]
    }
    C = cursors[(chosen, "writer-a")]
    dispatch_live_session_action(
        session_id=chosen,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: isolated"}},
        my_current_event_seq_number=C,
    )
    for sid, before in others_before.items():
        assert get_live_session_latest_event_seq(session_id=sid) == before


def test_decentralized_clients_poll_reject_refresh_and_retry_in_one_flow() -> None:
    sid = launch_facade_note_session_v1()

    client_a_C = 0
    client_b_C = 0

    mounted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="client-a",
        events_only=True,
        my_current_event_seq_number=client_a_C,
    )
    assert mounted["dispatch_outcome"] == "applied"

    client_a_C, a_mount_events, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="client-a",
        cursor=client_a_C,
        page_limit=1,
    )
    client_b_C, b_mount_events, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="client-b",
        cursor=client_b_C,
        page_limit=2,
    )
    assert a_mount_events
    assert b_mount_events
    assert client_a_C == client_b_C

    shared_C = client_a_C
    first_write = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="client-a",
        user_fill={"note": {"text": "keep-open: client-a"}},
        events_only=True,
        my_current_event_seq_number=shared_C,
    )
    assert first_write["dispatch_outcome"] == "applied"
    assert first_write["write_committed"] is True

    queue_before_stale = get_live_session_events(
        session_id=sid,
        role=None,
    )
    high_water_before_stale = get_live_session_latest_event_seq(
        session_id=sid
    )

    stale = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="client-b",
        user_fill={"note": {"text": "keep-open: client-b-stale"}},
        events_only=True,
        my_current_event_seq_number=shared_C,
    )
    assert stale["kind"] == "live_session_events_only_dispatch_receipt_v1"
    assert stale["rejection_kind"] == "stale_conflict"
    assert stale["dispatch_outcome"] == "stale_rejected"
    assert stale["write_committed"] is False
    assert (
        get_live_session_latest_event_seq(session_id=sid)
        == high_water_before_stale
    )
    assert (
        get_live_session_events(
            session_id=sid,
            role=None,
        )
        == queue_before_stale
    )

    client_b_C, b_refresh_events, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="client-b",
        cursor=client_b_C,
        page_limit=1,
    )
    assert b_refresh_events
    assert client_b_C == high_water_before_stale

    retry = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        identity_id="client-b",
        user_fill={"note": {"text": "keep-open: client-b-refreshed"}},
        events_only=True,
        my_current_event_seq_number=client_b_C,
    )
    assert retry["dispatch_outcome"] == "applied"
    assert retry["write_committed"] is True

    client_a_C, a_final_events, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="client-a",
        cursor=client_a_C,
        page_limit=2,
    )
    client_b_C, b_final_events, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="client-b",
        cursor=client_b_C,
        page_limit=1,
    )
    final_A = get_live_session_latest_event_seq(session_id=sid)

    assert a_final_events
    assert b_final_events
    assert client_a_C == client_b_C == final_A


def test_fill_and_signal_share_one_staleness_frontier_with_poller_recovery() -> None:
    sid = launch_facade_note_session_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
    )
    stale_client_C = get_live_session_latest_event_seq(session_id=sid)

    fill_write = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: fill-frontier"}},
        my_current_event_seq_number=stale_client_C,
    )
    assert fill_write["write_committed"] is True

    stale_signal = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_signal={
            "datum_id": "note",
            "kind": "touch",
            "info": {"attempt": "before-refresh"},
        },
        my_current_event_seq_number=stale_client_C,
    )
    _assert_staleness_rejected(stale_signal, reason="stale_conflict")

    refreshed_C, fill_events, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="fill-signal-client",
        cursor=stale_client_C,
        page_limit=1,
    )
    assert fill_events

    signal_write = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_signal={
            "datum_id": "note",
            "kind": "touch",
            "info": {"attempt": "after-refresh"},
        },
        my_current_event_seq_number=refreshed_C,
    )
    assert signal_write["dispatch_outcome"] == "applied"
    assert signal_write["write_committed"] is True

    stale_fill = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: stale-after-signal"}},
        my_current_event_seq_number=refreshed_C,
    )
    _assert_staleness_rejected(stale_fill, reason="stale_conflict")

    final_C, signal_events, _ = _poll_canonical_until_caught_up_v1(
        session_id=sid,
        role="writer",
        identity_id="fill-signal-client",
        cursor=refreshed_C,
        page_limit=2,
    )
    assert signal_events
    assert final_C == get_live_session_latest_event_seq(session_id=sid)


def test_session_scale_model_is_many_independent_serialized_write_domains() -> None:
    left = launch_facade_note_session_v1()
    right = launch_facade_note_session_v1()

    for sid in (left, right):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role="writer",
            my_current_event_seq_number=0,
        )

    left_C = get_live_session_latest_event_seq(session_id=left)
    right_C = get_live_session_latest_event_seq(session_id=right)

    left_write = dispatch_live_session_action(
        session_id=left,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: left"}},
        my_current_event_seq_number=left_C,
    )
    assert left_write["write_committed"] is True

    right_A_before = get_live_session_latest_event_seq(session_id=right)
    right_queue_before = get_live_session_events(
        session_id=right,
        role=None,
    )

    left_stale = dispatch_live_session_action(
        session_id=left,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: stale-left"}},
        my_current_event_seq_number=left_C,
    )
    _assert_staleness_rejected(left_stale, reason="stale_conflict")

    assert (
        get_live_session_latest_event_seq(session_id=right) == right_A_before
    )
    assert (
        get_live_session_events(
            session_id=right,
            role=None,
        )
        == right_queue_before
    )

    right_write = dispatch_live_session_action(
        session_id=right,
        action=UserAction.STEP,
        role="writer",
        user_fill={"note": {"text": "keep-open: right"}},
        my_current_event_seq_number=right_C,
    )
    assert right_write["write_committed"] is True
