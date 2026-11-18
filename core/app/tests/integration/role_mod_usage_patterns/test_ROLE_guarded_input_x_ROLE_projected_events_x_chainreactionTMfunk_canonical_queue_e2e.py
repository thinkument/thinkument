from __future__ import annotations

"""
TASK D — ONE ROLELESS RUN, GUARDED WRITES, PROJECTED READS
=========================================================

This is the highest-façade E2E proof of Thinkument's role information layer.

The story
---------

Thinkument executes one canonical, roleless run.

Roles do not create separate sessions, state machines, or event histories.
They act only at the public boundary:

    write boundary
        A role may fill a guarded datum only when it owns that datum.

    read boundary
        A role may observe a guarded datum when it owns that datum or has been
        granted read access through ``read_roles``.

    storage boundary
        The engine retains one bounded canonical event queue. Role projection
        happens only when events or UI context are released to a caller.

For a datum ``d`` and viewer/dispatcher role ``r``:

    R(d)
        is the datum's explicit roles, falling back to its active span roles.

    Read(r)
        is ``{r} union roles[r].read_roles``.

    write_allowed(r, d)
        iff ``R(d)`` is empty or ``r`` is in ``R(d)``.

    read_allowed(r, d)
        iff ``R(d)`` is empty or ``R(d)`` intersects ``Read(r)``.

Therefore read authority never grants write authority.

The same release law governs both public contexts and event reads:

    controller_loop_event_v1
        remains visible, keeps canonical identity, and receives projected
        ``payload.U``.

    datum_lifecycle_event_v1
        remains in canonical storage but is omitted from a named viewer's read
        when that viewer cannot read the datum.

Projection never mutates canonical history.

Highest-façade dispatch boundary
--------------------------------

All live operations in this proof use only:

    _thinksessions.run.run_from_here

No test reads snapshots, engine state, controller internals, raw session APIs,
legacy polling receivers, or alternate dispatch systems.

The highest façade composes write authorization and event-cursor staleness as
adjacent but distinct checks inside the serialized per-session boundary:

    role authorization
        Unauthorized fill targets raise ``PermissionError`` before controller
        execution. The rejection is eventless: canonical state, context,
        queue contents, and event high-water remain unchanged.

    target resolution and staleness
        An authorized caller may optionally submit
        ``my_current_event_seq_number``. A future or conflicting stale cursor
        returns a structured staleness rejection packet without entering the
        controller and without moving canonical history.

    controller execution
        Only an authorized, staleness-allowed request reaches semantic and
        controller processing.

Authorization deliberately precedes staleness. A caller that lacks write
authority must not learn target conflict or cursor information for data it
cannot mutate.

The process-local highest-façade serialization proven here does not establish
cross-process mutual exclusion. A multi-process host must provide one durable,
atomic per-session transaction around authorization, cursor validation,
dispatch, event-sequence assignment, target-change indexing, and commit.

Proof sequence
--------------

    01   Metadata publishes the read/write separation law.
    03   Reviewer can read maker data but cannot write it.
    04   Role-rejected input is eventless and leaves state unchanged.
    05   Maker can fill its own datum.
    06b  U exposes one latest complete Di per span-owned datum.
    07   Controller event identity survives role projection.
    08   Readable roles receive identical ReactionTimeTM metadata.
    09   Guarded datum events are filtered; unguarded events remain public.
    10   Repeated projected reads never mutate canonical history.
    11   One run crosses maker, reviewer, and release ownership boundaries.
    12   Authorization precedes staleness while both remain distinct.
    13   Controller actions and actor envelopes follow datum read projection.
    14   Di collection is dead JSON and projection leaves canonical U intact.
"""

import json
from copy import deepcopy
from typing import Any, Dict, Mapping, Optional

import pytest

# Registration side effect for built-in micro types.
import _thinkprogram._iomicrosTM.table_micros  # noqa: F401

from _thinkprogram._thinkcontinuitykernelTM.api import (
    register_kernel_step_fn_v1,
    register_thinking_flow_explicit_language_v1,
)
from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
    pull_thinkwidget_class_into_kernel_v1,
)
from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
    register_think_program_language_v1,
)
from _thinksessions.run.run_from_here import (
    UserAction,
    create_live_session_from_program,
    dispatch_live_session_action,
    dispatch_live_session_action_with_chain_reaction,
    get_live_session_context,
    get_live_session_events,
    get_live_session_latest_event_seq,
)
from _thinksessions.sesh_metadata.__sesh_meta_future_surface_augments import (
    build_demo_program_sesh_metadata_v1,
    program_sesh_metadata_surface_v1,
    register_program_sesh_metadata_pockets_v1,
)


from _thinksessions.run.runme_surfaces_out.helpers_event_read import (
    CONTROLLER_LOOP_EVENT_KIND_V1,
    assert_controller_loop_event_v1,
    assert_datum_lifecycle_event_v1,
)

from _thinksessions.example_reused_test_flow_setups.funk.test import (
    FUNK_VERSION,
    register_demo_semantic_shell_funk_v1,
)
from _thinksessions.example_reused_test_flow_setups.programs.test import demo_think_program_v1
from _thinksessions.example_reused_test_flow_setups.widgets.test import DEMO_WIDGET_CLASSES



DATUM_EVENT_KIND = "datum_lifecycle_event_v1"

ROLE_MAKER = "maker"
ROLE_REVIEWER = "reviewer"
ROLE_RELEASE = "release_ai"
ROLE_AUDITOR = "auditor"

D_COMPLEX = "complex"
D_SUPPORT = "support"
D_REVIEW = "review"


# =============================================================================
# Application registration and launch
# =============================================================================

def register_demo_application_v1() -> None:
    register_program_sesh_metadata_pockets_v1(replace=True)
    register_demo_semantic_shell_funk_v1()

    for widget_cls in DEMO_WIDGET_CLASSES:
        receipt = pull_thinkwidget_class_into_kernel_v1(
            widget_cls,
            overwrite=True,
        )
        assert receipt["ok"] is True

    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()
    register_think_program_language_v1()


def launch_role_demo_v1(
    *,
    chainreaction_enabled: bool = False,
    maker_funk_version: Optional[str] = None,
    reviewer_funk_version: Optional[str] = None,
    release_funk_version: Optional[str] = None,
) -> str:
    register_demo_application_v1()

    created = create_live_session_from_program(
        program=demo_think_program_v1(),
        program_language=LANG_THINK_PROGRAM_V1,
        initial_parameter_overrides={},
        session_metadata=build_demo_program_sesh_metadata_v1(
            chainreaction_enabled=chainreaction_enabled,
            maker_funk_version=maker_funk_version,
            reviewer_funk_version=reviewer_funk_version,
            release_funk_version=release_funk_version,
        ),
    )

    assert created["ok"] is True
    return str(created["session_id"])


# =============================================================================
# Public-packet helpers
# =============================================================================

def dead_json(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def event_ids(events: list[Mapping[str, Any]]) -> list[str]:
    return [str(event["event_id"]) for event in events]


def controller_event_ids(
    events: list[Mapping[str, Any]],
) -> list[str]:
    return [
        str(event["event_id"])
        for event in events
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
    ]


def datum_event_ids(
    events: list[Mapping[str, Any]],
    *,
    datum_id: str,
) -> list[str]:
    return [
        str(event["event_id"])
        for event in events
        if event.get("kind") == DATUM_EVENT_KIND
        and event.get("datum_id") == datum_id
    ]


def latest_controller_end(
    events: list[Mapping[str, Any]],
) -> Dict[str, Any]:
    matches = [
        dict(event)
        for event in events
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
        and event.get("phase") == "end"
    ]
    assert matches
    return matches[-1]


def controller_events_for_dispatch(
    events: list[Mapping[str, Any]],
    *,
    dispatch_id: str,
) -> list[Dict[str, Any]]:
    return [
        dict(event)
        for event in events
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
        and event.get("dispatch_id") == dispatch_id
    ]


def latest_U(
    events: list[Mapping[str, Any]],
) -> Dict[str, Any]:
    U = latest_controller_end(events)["payload"]["U"]
    assert isinstance(U, Mapping)
    return deepcopy(dict(U))


def active_datum_ids(U: Mapping[str, Any]) -> list[str]:
    return [
        str(value)
        for value in list(U.get("datum_widgets_on_this_span") or [])
    ]


def role_info(U: Mapping[str, Any]) -> Dict[str, Any]:
    value = U.get("role_mismatch_modulation_info")
    assert isinstance(value, Mapping)
    return dict(value)


def role_receipt(U: Mapping[str, Any]) -> Any:
    return role_info(U).get("receipt")


def datums_by_id(
    U: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    spec = U.get("multiframespec")
    assert isinstance(spec, Mapping)

    datums = spec.get("datums")
    assert isinstance(datums, list)

    return {
        str(row["id"]): deepcopy(dict(row))
        for row in datums
        if isinstance(row, Mapping)
    }


def datum_states_by_id(
    U: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    rows = U.get("datum_states_on_this_span")
    assert isinstance(rows, list)

    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        assert isinstance(row, Mapping)
        datum_id = str(
            row.get("datum_id")
            or ""
        )
        assert datum_id
        out[datum_id] = deepcopy(dict(row))

    return out


def manual_complex_fill_v1() -> Dict[str, Any]:
    return {
        "description": "Complete deterministic role information layer proof",
        "long_description": (
            "Prove guarded writes projected reads and canonical queue storage"
        ),
        "slug": "role-information-layer-proof",
        "contact_email": "demo@example.com",
        "target_date": "2026-07-13",
        "snippet": "value = 1\nprint(value)",
        "formula": "x^2 + y^2",
        "hero_image_url": "https://example.com/image.png",
        "local_image_path": "./images/example.png",
        "count": "3",
        "confidence": "8",
        "metadata": {
            "task": "D",
            "proof": "role-layer",
        },
        "ready": True,
        "pause_ack": True,
    }


def assert_canonical_event_grammar(
    events: list[Mapping[str, Any]],
) -> None:
    assert events

    for event in events:
        kind = event.get("kind")

        if kind == CONTROLLER_LOOP_EVENT_KIND_V1:
            assert_controller_loop_event_v1(event)
        else:
            assert kind == DATUM_EVENT_KIND
            assert_datum_lifecycle_event_v1(event)


def assert_direct_dispatch_receipt(packet: Mapping[str, Any]) -> None:
    receipt = packet.get("dispatch_concurrency")
    assert isinstance(receipt, Mapping)

    assert receipt["applied"] is True
    assert receipt["rejected"] is False
    assert receipt["guarding"] == (
        "per_session_serialized_highest_facade"
    )
    assert receipt["idempotent_replay"] is False
    assert receipt["after_event_seq"] >= receipt["before_event_seq"]

    stale = packet.get("dispatch_staleness")
    assert isinstance(stale, Mapping)
    assert stale["kind"] == (
        "live_session_dispatch_staleness_receipt_v1"
    )
    assert stale["outcome"] == "allowed"


def assert_session_unchanged_v1(
    *,
    session_id: str,
    queue_before: Any,
    context_before: Any,
    latest_event_seq_before: int,
) -> None:
    queue_after = dead_json(
        get_live_session_events(
            session_id=session_id,
            role=None,
        )
    )
    context_after = dead_json(
        get_live_session_context(
            session_id=session_id,
            role=None,
        )
    )

    assert queue_after == queue_before
    assert context_after == context_before
    assert get_live_session_latest_event_seq(
        session_id=session_id
    ) == latest_event_seq_before


# =============================================================================
# 01–02. Published law
# =============================================================================

def test_01_metadata_surface_publishes_read_write_separation() -> None:
    metadata_surface = program_sesh_metadata_surface_v1()

    assert dead_json(metadata_surface) == metadata_surface

    role_surface = metadata_surface["base"]["subsurfaces"][
        "role_modulation"
    ]
    laws = " ".join(role_surface["laws"])

    assert "read_roles grants read visibility" in laws
    assert "never grants write permission" in laws
    assert "engine remains roleless" in laws


# =============================================================================
# 03–06. Guarded writes and preserved authored 
# =============================================================================

def test_03_read_authority_does_not_grant_write_authority() -> None:
    sid = launch_role_demo_v1()

    mounted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
    )
    assert_direct_dispatch_receipt(mounted)

    reviewer_U = get_live_session_context(
        session_id=sid,
        role=ROLE_REVIEWER,
    )
    reviewer_info = role_info(reviewer_U)

    assert D_COMPLEX in active_datum_ids(reviewer_U)
    assert reviewer_info["read_role_names"] == [
        ROLE_MAKER,
        ROLE_REVIEWER,
    ]

    assignments = {
        row["datum_id"]: dict(row)
        for row in reviewer_info["assignments"]
    }
    assert assignments[D_COMPLEX]["read_allowed"] is True
    assert assignments[D_COMPLEX]["write_allowed"] is False


    with pytest.raises(PermissionError, match=D_COMPLEX):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role=ROLE_REVIEWER,
            user_fill={
                D_COMPLEX: manual_complex_fill_v1(),
            },
        )


def test_04_role_rejected_write_is_eventless_and_leaves_state_unchanged() -> None:
    sid = launch_role_demo_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
    )

    queue_before = dead_json(
        get_live_session_events(
            session_id=sid,
            role=None,
        )
    )
    context_before = dead_json(
        get_live_session_context(
            session_id=sid,
            role=None,
        )
    )
    latest_event_seq_before = get_live_session_latest_event_seq(
        session_id=sid
    )

    with pytest.raises(PermissionError, match=D_COMPLEX):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role=ROLE_AUDITOR,
            user_fill={
                D_COMPLEX: manual_complex_fill_v1(),
            },
        )

    assert_session_unchanged_v1(
        session_id=sid,
        queue_before=queue_before,
        context_before=context_before,
        latest_event_seq_before=latest_event_seq_before,
    )


def test_05_owner_can_write_and_advance_its_datum() -> None:
    sid = launch_role_demo_v1()

    mounted = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
    )
    assert mounted["event_kind"] == "MANUALFILLNEEDEDSTEP"

    described = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
        user_fill={
            D_COMPLEX: manual_complex_fill_v1(),
        },
    )
    assert_direct_dispatch_receipt(described)

    maker_U = get_live_session_context(
        session_id=sid,
        role=ROLE_MAKER,
    )
    active_micros = {
        str(row["name"])
        for row in maker_U["datum_widget_decls"][D_COMPLEX][
            "datum_args"
        ]["micro_input_fields"]
    }

    assert active_micros == {"decision", "publish"}



def test_06b_U_exposes_one_latest_complete_Di_per_span_owned_datum() -> None:
    sid = launch_role_demo_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
    )

    before = get_live_session_context(
        session_id=sid,
        role=ROLE_MAKER,
    )

    before_rows = datum_states_by_id(before)
    assert list(before_rows) == [
        str(value)
        for value in before["step"]["span_owns"]
    ]

    before_Di = before_rows[D_COMPLEX]
    before_shell = datums_by_id(before)[D_COMPLEX]

    assert before_Di["kind"] == (
        "universal_ui_datum_state_v1"
    )
    assert before_Di["datum_id"] == D_COMPLEX
    assert before_Di["shell"] == before_shell
    assert before_Di["micros"] == list(
        before_shell.get("micros") or []
    )
    assert before_Di["args"] == dict(
        before_shell.get("args") or {}
    )

    assert before_Di["originating_step"] == {
        "public_step_name": str(
            before["step"].get("public_step_name")
            or ""
        ),
        "source_step_fn": str(
            before["step"].get("source_step_fn")
            or ""
        ),
        "source_fn_args": dict(
            before["step"].get("source_fn_args")
            or {}
        ),
    }
    assert before_Di["is_authoritative"] is True
    assert before_Di["is_pending"] is True

    semantic = before_Di["semantic_validation"]
    assert isinstance(semantic, Mapping)
    assert semantic["micros"]

    for micro_row, source_micro in zip(
        semantic["micros"],
        before_shell.get("micros") or [],
    ):
        assert micro_row["name"] == str(
            source_micro.get("name")
            or ""
        )
        assert micro_row["spec"] == source_micro
        assert micro_row["validator_fields"] == {
            str(key): value
            for key, value in source_micro.items()
            if (
                "validat" in str(key).lower()
                or "lambda" in str(key).lower()
            )
        }

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
        user_fill={
            D_COMPLEX: manual_complex_fill_v1(),
        },
    )

    after = get_live_session_context(
        session_id=sid,
        role=ROLE_MAKER,
    )
    after_Di = datum_states_by_id(after)[D_COMPLEX]
    after_shell = datums_by_id(after)[D_COMPLEX]

    assert after_Di["shell"] == after_shell
    assert after_Di["micro_names"] == ["decision", "publish"]
    assert after_Di["micro_names"] != before_Di["micro_names"]
    assert after_Di["lifecycle"]["runtime"] is not None
    assert after_Di["lifecycle"]["runtime"]["state"] is not None


# =============================================================================
# 07–10. Projected reads over one canonical queue
# =============================================================================

def test_07_controller_identity_is_stable_while_payload_U_is_projected() -> None:
    sid = launch_role_demo_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
    )

    canonical = get_live_session_events(
        session_id=sid,
        role=None,
    )
    maker = get_live_session_events(
        session_id=sid,
        role=ROLE_MAKER,
    )
    reviewer = get_live_session_events(
        session_id=sid,
        role=ROLE_REVIEWER,
    )
    auditor = get_live_session_events(
        session_id=sid,
        role=ROLE_AUDITOR,
    )

    assert_canonical_event_grammar(canonical)

    canonical_controller_ids = controller_event_ids(canonical)
    assert controller_event_ids(maker) == canonical_controller_ids
    assert controller_event_ids(reviewer) == canonical_controller_ids
    assert controller_event_ids(auditor) == canonical_controller_ids

    canonical_U = latest_U(canonical)
    maker_U = latest_U(maker)
    reviewer_U = latest_U(reviewer)
    auditor_U = latest_U(auditor)

    assert canonical_U.get("role_mismatch_modulation_info") is None
    assert role_info(maker_U)["role_viewing"] == ROLE_MAKER
    assert role_info(reviewer_U)["role_viewing"] == ROLE_REVIEWER
    assert role_info(auditor_U)["role_viewing"] == ROLE_AUDITOR
    assert role_receipt(maker_U) is None
    assert role_receipt(reviewer_U) is None
    assert role_receipt(auditor_U) is None

    assert D_COMPLEX in active_datum_ids(maker_U)
    assert D_COMPLEX in active_datum_ids(reviewer_U)
    assert D_COMPLEX not in active_datum_ids(auditor_U)
    assert D_SUPPORT in active_datum_ids(auditor_U)

    hidden = auditor_U["datum_widget_decls"][D_COMPLEX]
    assert hidden["kind"] == "role_mismatch_obfuscated_datum_v1"
    assert hidden["role_mismatch_obfuscated"] is True

    maker_Di = datum_states_by_id(maker_U)[D_COMPLEX]
    reviewer_Di = datum_states_by_id(reviewer_U)[D_COMPLEX]
    auditor_Di = datum_states_by_id(auditor_U)[D_COMPLEX]

    assert maker_Di["kind"] == "universal_ui_datum_state_v1"
    assert reviewer_Di == maker_Di

    assert auditor_Di == {
        "kind": "role_mismatch_obfuscated_datum_v1",
        "datum_id": D_COMPLEX,
        "role_mismatch_obfuscated": True,
        "obfuscated": True,
        "reason": "role_mismatch",
        "viewer_role": ROLE_AUDITOR,
        "required_roles": [ROLE_MAKER],
        "is_authoritative": None,
        "is_pending": False,
    }


def test_09_guarded_datum_events_are_filtered_and_unguarded_events_are_public() -> None:
    sid = launch_role_demo_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
    )

    canonical = get_live_session_events(
        session_id=sid,
        role=None,
    )
    maker = get_live_session_events(
        session_id=sid,
        role=ROLE_MAKER,
    )
    reviewer = get_live_session_events(
        session_id=sid,
        role=ROLE_REVIEWER,
    )
    auditor = get_live_session_events(
        session_id=sid,
        role=ROLE_AUDITOR,
    )

    canonical_complex = datum_event_ids(
        canonical,
        datum_id=D_COMPLEX,
    )
    canonical_support = datum_event_ids(
        canonical,
        datum_id=D_SUPPORT,
    )

    assert canonical_complex
    assert canonical_support

    assert datum_event_ids(
        maker,
        datum_id=D_COMPLEX,
    ) == canonical_complex
    assert datum_event_ids(
        reviewer,
        datum_id=D_COMPLEX,
    ) == canonical_complex
    assert datum_event_ids(
        auditor,
        datum_id=D_COMPLEX,
    ) == []

    for projected in (maker, reviewer, auditor):
        assert datum_event_ids(
            projected,
            datum_id=D_SUPPORT,
        ) == canonical_support


def test_10_projected_reads_never_mutate_canonical_history() -> None:
    sid = launch_role_demo_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
    )

    canonical_before = dead_json(
        get_live_session_events(
            session_id=sid,
            role=None,
        )
    )
    latest_event_seq_before = get_live_session_latest_event_seq(
        session_id=sid
    )

    for _ in range(3):
        for role in (
            ROLE_MAKER,
            ROLE_REVIEWER,
            ROLE_RELEASE,
            ROLE_AUDITOR,
        ):
            get_live_session_events(
                session_id=sid,
                role=role,
            )
            get_live_session_context(
                session_id=sid,
                role=role,
            )

    canonical_after = dead_json(
        get_live_session_events(
            session_id=sid,
            role=None,
        )
    )

    assert canonical_after == canonical_before
    assert get_live_session_latest_event_seq(
        session_id=sid
    ) == latest_event_seq_before

    for event in canonical_after:
        if event["kind"] == CONTROLLER_LOOP_EVENT_KIND_V1:
            assert (
                event["payload"]["U"].get(
                    "role_mismatch_modulation_info"
                )
                is None
            )


# =============================================================================
# 11. One run across maker, reviewer, and release ownership
# =============================================================================

def test_11_one_run_preserves_local_write_ownership_as_read_authority_grows() -> None:
    sid = launch_role_demo_v1(
        chainreaction_enabled=True,
        maker_funk_version=FUNK_VERSION,
        reviewer_funk_version=None,
        release_funk_version=FUNK_VERSION,
    )

    first = dispatch_live_session_action_with_chain_reaction(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
    )
    assert_direct_dispatch_receipt(first)

    assert first["event_kind"] == "MANUALFILLNEEDEDSTEP"
    assert first["chainreactionTM_receipt"]["roles_used"] == [
        ROLE_MAKER,
        ROLE_MAKER,
    ]

    reviewer_U = get_live_session_context(
        session_id=sid,
        role=ROLE_REVIEWER,
    )
    assert active_datum_ids(reviewer_U) == [D_REVIEW]


    reviewer_assignment = {
        row["datum_id"]: dict(row)
        for row in role_info(reviewer_U)["assignments"]
    }[D_REVIEW]
    assert reviewer_assignment["read_allowed"] is True
    assert reviewer_assignment["write_allowed"] is True

    release_U = get_live_session_context(
        session_id=sid,
        role=ROLE_RELEASE,
    )
    release_assignment = {
        row["datum_id"]: dict(row)
        for row in role_info(release_U)["assignments"]
    }[D_REVIEW]
    assert release_assignment["read_allowed"] is True
    assert release_assignment["write_allowed"] is False


    queue_before_rejected_write = dead_json(
        get_live_session_events(
            session_id=sid,
            role=None,
        )
    )
    context_before_rejected_write = dead_json(
        get_live_session_context(
            session_id=sid,
            role=None,
        )
    )
    latest_event_seq_before_rejected_write = (
        get_live_session_latest_event_seq(session_id=sid)
    )

    with pytest.raises(PermissionError, match=D_REVIEW):
        dispatch_live_session_action(
            session_id=sid,
            action=UserAction.STEP,
            role=ROLE_RELEASE,
            user_fill={
                D_REVIEW: {
                    "approval": "approve",
                    "comment": "Release may read but cannot review",
                }
            },
        )

    assert_session_unchanged_v1(
        session_id=sid,
        queue_before=queue_before_rejected_write,
        context_before=context_before_rejected_write,
        latest_event_seq_before=latest_event_seq_before_rejected_write,
    )

    completed = dispatch_live_session_action_with_chain_reaction(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_REVIEWER,
        user_fill={
            D_REVIEW: {
                "approval": "approve",
                "comment": "Reviewed and approved",
            }
        },
    )
    assert_direct_dispatch_receipt(completed)

    assert completed["event_kind"] == "ATCOMPLETION"
    assert completed["finished"] is True
    assert completed["chainreactionTM_receipt"]["roles_used"] == [
        ROLE_RELEASE,
    ]

    canonical = get_live_session_events(
        session_id=sid,
        role=None,
    )
    assert_canonical_event_grammar(canonical)

    for role in (
        ROLE_MAKER,
        ROLE_REVIEWER,
        ROLE_RELEASE,
        ROLE_AUDITOR,
    ):
        projected = get_live_session_events(
            session_id=sid,
            role=role,
        )
        assert set(event_ids(projected)).issubset(set(event_ids(canonical)))


# =============================================================================
# 12. Staleness and role-write guard composition
# =============================================================================

def test_12_authorization_precedes_staleness_without_conflating_them() -> None:
    sid = launch_role_demo_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
    )
    A = get_live_session_latest_event_seq(session_id=sid)
    queue_at_A = dead_json(
        get_live_session_events(
            session_id=sid,
            role=None,
        )
    )
    context_at_A = dead_json(
        get_live_session_context(
            session_id=sid,
            role=None,
        )
    )

    # An authorized writer reaches the staleness boundary. A future cursor is
    # rejected structurally and without canonical queue movement.
    future = dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
        user_fill={D_COMPLEX: manual_complex_fill_v1()},
        my_current_event_seq_number=A + 1,
    )

    assert future["rejection_kind"] == "future_event_cursor"
    assert future["dispatch_outcome"] == "stale_rejected"
    assert future["applied"] is False
    assert future["rejected"] is True

    stale_receipt = future.get("dispatch_staleness")
    assert isinstance(stale_receipt, Mapping)
    assert stale_receipt["kind"] == (
        "live_session_dispatch_staleness_receipt_v1"
    )
    assert stale_receipt["outcome"] == "rejected"

    assert_session_unchanged_v1(
        session_id=sid,
        queue_before=queue_at_A,
        context_before=context_at_A,
        latest_event_seq_before=A,
    )

    # An unauthorized writer is rejected before cursor validation. The same
    # PermissionError wins for both future and current cursors, preventing
    # unauthorized callers from probing cursor/conflict state.
    for cursor in (A + 1, A):
        with pytest.raises(PermissionError, match=D_COMPLEX):
            dispatch_live_session_action(
                session_id=sid,
                action=UserAction.STEP,
                role=ROLE_REVIEWER,
                user_fill={D_COMPLEX: manual_complex_fill_v1()},
                my_current_event_seq_number=cursor,
            )

        assert_session_unchanged_v1(
            session_id=sid,
            queue_before=queue_at_A,
            context_before=context_at_A,
            latest_event_seq_before=A,
        )


def test_13_controller_A_and_actor_envelope_follow_datum_read_projection() -> None:
    sid = launch_role_demo_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        identity_id="maker-user",
        role=ROLE_MAKER,
    )
    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        identity_id="maker-user",
        role=ROLE_MAKER,
        user_fill={D_COMPLEX: manual_complex_fill_v1()},
    )

    canonical = get_live_session_events(session_id=sid, role=None)
    target_start = [
        event
        for event in canonical
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
        and event.get("phase") == "start"
        and event.get("payload", {}).get("A", {}).get("fill")
    ][-1]
    dispatch_id = str(target_start["dispatch_id"])
    canonical_pair = controller_events_for_dispatch(
        canonical,
        dispatch_id=dispatch_id,
    )
    assert [event["phase"] for event in canonical_pair] == ["start", "end"]
    for event in canonical_pair:
        assert event["dispatcher_identity_id"] == "maker-user"
        assert event["dispatcher_role"] == ROLE_MAKER
        assert event["payload"]["A"]["fill"] == {
            D_COMPLEX: manual_complex_fill_v1(),
        }
        assert event["payload"]["fill"] == event["payload"]["A"]["fill"]
        assert event["payload"]["signal"] == event["payload"]["A"]["signal"]

    reviewer = get_live_session_events(session_id=sid, role=ROLE_REVIEWER)
    reviewer_pair = controller_events_for_dispatch(
        reviewer,
        dispatch_id=dispatch_id,
    )
    assert len(reviewer_pair) == 2
    for event in reviewer_pair:
        assert event["dispatcher_identity_id"] == "maker-user"
        assert event["dispatcher_role"] == ROLE_MAKER
        assert D_COMPLEX in event["payload"]["A"]["fill"]

    auditor = get_live_session_events(session_id=sid, role=ROLE_AUDITOR)
    hidden_pair = [
        event
        for event in auditor
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
        and event.get("phase") in {"start", "end"}
        and event.get("payload", {}).get("A") is None
    ][-2:]
    assert [event["phase"] for event in hidden_pair] == ["start", "end"]
    for event in hidden_pair:
        assert event["dispatch_id"] is None
        assert event["dispatcher_identity_id"] is None
        assert event["dispatcher_role"] is None
        assert event["payload"]["A"] is None
        assert event["payload"]["fill"] is None
        assert event["payload"]["signal"] is None


def test_14_Di_collector_is_dead_json_and_projection_never_mutates_canonical_U() -> None:
    sid = launch_role_demo_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
    )

    canonical_before = dead_json(
        get_live_session_context(
            session_id=sid,
            role=None,
        )
    )

    canonical_rows = datum_states_by_id(canonical_before)
    assert canonical_rows[D_COMPLEX]["shell"]
    assert canonical_rows[D_COMPLEX]["semantic_validation"]
    assert (
        canonical_before.get("role_mismatch_modulation_info")
        is None
    )
    assert canonical_rows[D_COMPLEX]["kind"] == (
        "universal_ui_datum_state_v1"
    )
    assert canonical_rows[D_COMPLEX]["shell"] == (
        datums_by_id(canonical_before)[D_COMPLEX]
    )

    json.dumps(
        canonical_before["datum_states_on_this_span"],
        sort_keys=True,
    )

    auditor = get_live_session_context(
        session_id=sid,
        role=ROLE_AUDITOR,
    )
    hidden = datum_states_by_id(auditor)[D_COMPLEX]

    for forbidden_key in (
        "shell",
        "micros",
        "args",
        "fill",
        "semantic_validation",
        "lifecycle",
        "originating_step",
    ):
        assert forbidden_key not in hidden

    canonical_after = dead_json(
        get_live_session_context(
            session_id=sid,
            role=None,
        )
    )
    assert canonical_after == canonical_before


def test_15_controller_start_and_end_U_carry_complete_Di_vectors() -> None:
    sid = launch_role_demo_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        identity_id="maker-user",
        role=ROLE_MAKER,
    )

    canonical = get_live_session_events(
        session_id=sid,
        role=None,
    )
    controller_events = [
        event
        for event in canonical
        if event.get("kind") == CONTROLLER_LOOP_EVENT_KIND_V1
    ]
    assert controller_events

    for event in controller_events:
        U = event["payload"]["U"]
        if U.get("kind") != "MANUALFILLNEEDEDSTEP":
            continue

        rows = U.get("datum_states_on_this_span")
        assert isinstance(rows, list)
        assert [
            str(row["datum_id"])
            for row in rows
        ] == [
            str(value)
            for value in U["step"]["span_owns"]
        ]

        for row in rows:
            assert row["kind"] == "universal_ui_datum_state_v1"
            assert row["shell"] == datums_by_id(U)[row["datum_id"]]
            assert isinstance(row["semantic_validation"], Mapping)


def test_16_named_role_projection_obfuscates_Di_without_shape_leaks() -> None:
    sid = launch_role_demo_v1()

    dispatch_live_session_action(
        session_id=sid,
        action=UserAction.STEP,
        role=ROLE_MAKER,
    )

    canonical = dead_json(
        get_live_session_context(
            session_id=sid,
            role=None,
        )
    )
    auditor = dead_json(
        get_live_session_context(
            session_id=sid,
            role=ROLE_AUDITOR,
        )
    )

    canonical_complex = datum_states_by_id(canonical)[D_COMPLEX]
    hidden_complex = datum_states_by_id(auditor)[D_COMPLEX]

    assert canonical_complex["shell"]

    assert hidden_complex == {
        "kind": "role_mismatch_obfuscated_datum_v1",
        "datum_id": D_COMPLEX,
        "role_mismatch_obfuscated": True,
        "obfuscated": True,
        "reason": "role_mismatch",
        "viewer_role": ROLE_AUDITOR,
        "required_roles": [ROLE_MAKER],
        "is_authoritative": None,
        "is_pending": False,
    }

    assert dead_json(
        get_live_session_context(
            session_id=sid,
            role=None,
        )
    ) == canonical