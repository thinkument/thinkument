from __future__ import annotations

"""
E2E proof for role-mismatch mode switching and scalable receipt registration.

The test stays on the highest authored-session facade for session creation,
dispatch, context reads, and event reads. The only additional public surface is
``role_modulation.register_mode``/``mode_sheet`` because mode registration is
process-startup configuration, not a live-session operation.
"""

import json
from copy import deepcopy
from typing import Any, Dict, Mapping

import pytest

from _thinkprogram.thinkprogramTM.api import LANG_THINK_PROGRAM_V1
from _thinksessions.libs_read_write_augmented.rolebasedRWmodulatorTM.obfuscation_api import (
    role_modulation,
)
from _thinksessions.run.run_from_here import (
    UserAction,
    create_live_session_from_program,
    dispatch_live_session_action,
    get_live_session_context,
    get_live_session_events,
    get_live_session_latest_event_seq,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.flows.program9__events_heard_and_events_caused_by_dispatch_under_role_modulated_reads_writes import (
    PROGRAM,
    ROLE_AUDITOR,
    ROLE_MAKER,
    ROLE_REVIEWER,
    SESSION_METADATA,
)
from ways_to_run.dry_run_examples.dry_run_lib_widgets_flows.registration import (
    register_dry_run_lib_widgets_flows_v1,
)


D_DAILY = "daily"
D_BOARD = "board"

BUILTIN_CASES = (
    ("redacted", frozenset()),
    ("redacted-w-activity-receipt", frozenset({"activity"})),
    ("redacted-w-identity-receipt", frozenset({"identity"})),
    (
        "redacted-w-identity-ownership-receipt",
        frozenset({"identity", "ownership"}),
    ),
    (
        "redacted-w-identity-ownership-activity-receipt",
        frozenset({"identity", "ownership", "activity"}),
    ),
)


def dead_json(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def launch_v1(*, auditor_mode: str) -> str:
    register_dry_run_lib_widgets_flows_v1()
    metadata = deepcopy(SESSION_METADATA)
    metadata["role_mismatch_policy"]["role_modes"][ROLE_AUDITOR] = (
        auditor_mode
    )

    created = create_live_session_from_program(
        program=deepcopy(PROGRAM),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata=metadata,
    )
    assert created["ok"] is True
    return str(created["session_id"])


def mount_v1(session_id: str) -> None:
    packet = dispatch_live_session_action(
        session_id=session_id,
        action=UserAction.STEP,
        identity_id="receipt-mode-maker",
        role=ROLE_MAKER,
    )
    assert packet["applied"] is True
    assert packet["rejected"] is False
    assert packet["event_kind"] == "MANUALFILLNEEDEDSTEP"


def modulation_info(U: Mapping[str, Any]) -> Dict[str, Any]:
    value = U.get("role_mismatch_modulation_info")
    assert isinstance(value, Mapping)
    return dict(value)


def hidden_daily(U: Mapping[str, Any]) -> Dict[str, Any]:
    decls = U.get("datum_widget_decls")
    assert isinstance(decls, Mapping)
    value = decls.get(D_DAILY)
    assert isinstance(value, Mapping)
    return dict(value)


def receipt(U: Mapping[str, Any]) -> Any:
    return modulation_info(U).get("receipt")


def assert_common_access_law_v1(session_id: str) -> None:
    reviewer_U = get_live_session_context(
        session_id=session_id,
        role=ROLE_REVIEWER,
    )
    assert D_DAILY in reviewer_U["datum_widgets_on_this_span"]

    assignments = {
        str(row["datum_id"]): dict(row)
        for row in modulation_info(reviewer_U)["assignments"]
    }
    assert assignments[D_DAILY]["read_allowed"] is True
    assert assignments[D_DAILY]["write_allowed"] is False

    with pytest.raises(PermissionError, match=D_DAILY):
        dispatch_live_session_action(
            session_id=session_id,
            action=UserAction.STEP,
            identity_id="receipt-mode-reviewer",
            role=ROLE_REVIEWER,
            user_fill={
                D_DAILY: {
                    "representative_number": 9,
                    "good_day": True,
                }
            },
        )

    maker_packet = dispatch_live_session_action(
        session_id=session_id,
        action=UserAction.STEP,
        identity_id="receipt-mode-maker",
        role=ROLE_MAKER,
        user_fill={
            D_BOARD: {
                "new_1": 1,
                "new_2": 3,
                "new_3": 5,
            }
        },
    )
    assert maker_packet["applied"] is True
    assert maker_packet["write_committed"] is True


def assert_receipt_has_no_content_leaks_v1(value: Mapping[str, Any]) -> None:
    forbidden = {
        "fill",
        "shell",
        "micros",
        "args",
        "semantic_validation",
        "messages",
        "proc_notes",
        "originating_step",
        "actor",
        "identity_id",
        "dispatcher_identity_id",
    }

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            assert forbidden.isdisjoint({str(key) for key in node})
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)


@pytest.mark.parametrize(("mode", "fields"), BUILTIN_CASES)
def test_builtin_mode_switching_preserves_access_and_emits_exact_receipt_shape(
    mode: str,
    fields: frozenset[str],
) -> None:
    sid = launch_v1(auditor_mode=mode)
    mount_v1(sid)

    canonical_before = dead_json(
        get_live_session_context(session_id=sid, role=None)
    )
    queue_before = dead_json(
        get_live_session_events(session_id=sid, role=None)
    )
    high_water_before = get_live_session_latest_event_seq(session_id=sid)

    auditor_U = get_live_session_context(
        session_id=sid,
        role=ROLE_AUDITOR,
    )

    hidden = hidden_daily(auditor_U)
    assert hidden["kind"] == "role_mismatch_obfuscated_datum_v1"
    assert hidden["role_mismatch_obfuscated"] is True
    assert D_DAILY not in auditor_U["datum_widgets_on_this_span"]
    assert D_BOARD in auditor_U["datum_widgets_on_this_span"]

    value = receipt(auditor_U)
    if not fields:
        assert value is None
    else:
        assert isinstance(value, Mapping)
        value = dict(value)
        assert value["kind"] == "role_mismatch_activity_receipt_v1"
        assert value["mode"] == mode
        assert value["viewer_role"] == ROLE_AUDITOR
        assert value["obfuscated_count"] == 1
        assert_receipt_has_no_content_leaks_v1(value)

        assert ("identity" in value) is ("identity" in fields)
        assert ("ownership" in value) is ("ownership" in fields)
        assert ("activity" in value) is ("activity" in fields)

        if "identity" in fields:
            assert value["identity"] == [{"datum_id": D_DAILY}]

        if "ownership" in fields:
            assert value["ownership"] == [
                {
                    "datum_id": D_DAILY,
                    "write_roles": [ROLE_MAKER],
                }
            ]

        if "activity" in fields and "identity" in fields:
            rows = value["activity"]
            assert isinstance(rows, list)
            assert len(rows) == 1
            row = rows[0]
            assert row["datum_id"] == D_DAILY
            assert isinstance(row["has_fill"], bool)
            assert isinstance(row["is_pending"], bool)
            assert isinstance(row["reexplode_count"], int)
            assert isinstance(row["message_count"], int)
            assert isinstance(row["proc_note_count"], int)

        if fields == frozenset({"activity"}):
            aggregate = value["activity"]
            assert isinstance(aggregate, Mapping)
            assert "datum_id" not in aggregate
            assert "write_roles" not in aggregate

    # Repeated projected reads are pure and deterministic.
    assert dead_json(
        get_live_session_context(session_id=sid, role=ROLE_AUDITOR)
    ) == dead_json(
        get_live_session_context(session_id=sid, role=ROLE_AUDITOR)
    )

    # Projection, including receipt production, never changes canonical state.
    assert dead_json(
        get_live_session_context(session_id=sid, role=None)
    ) == canonical_before
    assert dead_json(
        get_live_session_events(session_id=sid, role=None)
    ) == queue_before
    assert get_live_session_latest_event_seq(session_id=sid) == high_water_before

    assert_common_access_law_v1(sid)


def test_registered_mode_reuses_redacted_transform_without_runtime_branch() -> None:
    custom_mode = "redacted-w-test-identity-activity-receipt"
    role_modulation.register_mode(
        custom_mode,
        base_mode="redacted",
        receipt_fields=("identity", "activity"),
        overwrite=True,
    )

    assert custom_mode in role_modulation.mode_names()
    sheet = role_modulation.mode_sheet()
    assert dead_json(sheet) == sheet

    rows = {
        str(row["name"]): dict(row)
        for row in sheet["modes"]
    }
    assert rows[custom_mode]["receipt_fields"] == [
        "activity",
        "identity",
    ]

    sid = launch_v1(auditor_mode=custom_mode)
    mount_v1(sid)
    auditor_U = get_live_session_context(
        session_id=sid,
        role=ROLE_AUDITOR,
    )

    hidden = hidden_daily(auditor_U)
    assert hidden["kind"] == "role_mismatch_obfuscated_datum_v1"

    value = receipt(auditor_U)
    assert isinstance(value, Mapping)
    assert value["mode"] == custom_mode
    assert value["identity"] == [{"datum_id": D_DAILY}]
    assert "ownership" not in value
    assert isinstance(value["activity"], list)


def test_registration_rejects_invalid_receipt_capability_combinations() -> None:
    with pytest.raises(ValueError, match="unknown role mismatch receipt"):
        role_modulation.register_mode(
            "bad-unknown-receipt-field",
            base_mode="redacted",
            receipt_fields=("secret-content",),
            overwrite=True,
        )

    with pytest.raises(ValueError, match="ownership receipt requires identity"):
        role_modulation.register_mode(
            "bad-ownership-without-identity",
            base_mode="redacted",
            receipt_fields=("ownership",),
            overwrite=True,
        )