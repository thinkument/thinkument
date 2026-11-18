from __future__ import annotations

"""
Flask dispatch-boundary E2E proof sheet.

This file is intentionally narrower than ``test_flask_e2e.py``. The broad
sheet proves the complete local web application. This sheet freezes the
server-boundary contract needed by dispatcher-pollers:

* the exact harmonized dispatch receipt projection;
* accepted, semantic-rejected, stale-rejected, and chain outcomes;
* eventless preflight rejection;
* receipt/high-water/event coherence for an admitted dispatch;
* same-session thread serialization;
* the single-owner-process runtime guard; and
* the launcher prohibition on reloaders and multiple worker processes.

The local Flask server is not a durable transaction manager. Its integrity
claim is deliberately limited to one OS process, concurrent request threads,
the core per-session serialized dispatch lane, and closed ordinary-Exception
controller envelopes. Crash/restart atomicity and durable request-id
idempotency belong to the Django service.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event
from typing import Any, Dict, Mapping
from unittest.mock import Mock, patch
from uuid import uuid4

import _thinkprogram._iomicrosTM.table_micros  # noqa: F401
import pytest

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
from _thinksessions.sesh_metadata.__sesh_meta_future_surface_augments import (
    build_demo_program_sesh_metadata_v1,
    register_program_sesh_metadata_pockets_v1,
)
from _thinksessions.example_reused_test_flow_setups.helpers import (
    valid_complex_describe_fill,
)
from _thinksessions.example_reused_test_flow_setups.programs.test import (
    demo_think_program_v1,
)
from _thinksessions.example_reused_test_flow_setups.widgets.test import (
    DEMO_WIDGET_CLASSES,
)
from live_vial._json_shell.eps_log import (
    InMemoryEpsLog,
)
from __staticfiles_mgmt.globals import (
    LOCAL_FLASK_OWNER_PID_EXTENSION_KEY,
    LOCAL_FLASK_RUNTIME_PROFILE,
)
from live_vial._flask.adapter import reset_access_handles
from live_vial._flask.launch_local_flask_server import (
    serve_program_wrapper_on_flask,
)
from live_vial._flask.server_wrapper import (
    close_app_sessions,
    create_app_for_program,
    get_app_launch_bundle,
)


DIRECT_KIND = "live_session_events_only_dispatch_receipt_v1"
CHAIN_KIND = "live_session_events_only_chain_dispatch_receipt_v1"

# This is the exact cross-server projection. A transport may add only the
# documented optional pockets checked by ``_assert_transport_extensions``.
HARMONIZED_DISPATCH_KEYS = (
    "kind",
    "session_id",
    "dispatcher_identity_id",
    "dispatcher_role",
    "events_only",
    "ok",
    "applied",
    "rejected",
    "rejection_kind",
    "dispatch_outcome",
    "write_committed",
    "event_kind",
    "finished",
    "last_error",
    "system_error",
    "request_id",
    "dispatch_concurrency",
    "dispatch_staleness",
)

DIRECT_OPTIONAL_KEYS = frozenset({"ctx_report"})
CHAIN_OPTIONAL_KEYS = frozenset(
    {"ctx_report", "chainreactionTM_receipt"}
)
CONCURRENCY_KEYS = {
    "kind",
    "applied",
    "rejected",
    "reason",
    "stale_policy",
    "before_event_seq",
    "after_event_seq",
    "request_id",
    "idempotent_replay",
    "coordination_layer",
    "guarding",
}


def _register_demo() -> None:
    register_program_sesh_metadata_pockets_v1(replace=True)

    for widget_cls in DEMO_WIDGET_CLASSES:
        receipt = pull_thinkwidget_class_into_kernel_v1(
            widget_cls,
            overwrite=True,
        )
        assert receipt["ok"] is True


    register_kernel_step_fn_v1()
    register_thinking_flow_explicit_language_v1()
    register_think_program_language_v1()


def _launch_spec(
    *,
    chainreaction_enabled: bool = False,
) -> Dict[str, Any]:
    _register_demo()
    metadata = build_demo_program_sesh_metadata_v1(
        chainreaction_enabled=chainreaction_enabled,
        maker_funk_version="",
        reviewer_funk_version=None,
        release_funk_version="",
    )
    roles = dict(metadata.pop("roles"))
    role_policy = dict(metadata.pop("role_mismatch_policy"))

    return {
        "kind": "thinkument_local_flask_launch_spec_v1",
        "runtime_profile": LOCAL_FLASK_RUNTIME_PROFILE,
        "program_language": LANG_THINK_PROGRAM_V1,
        "program": demo_think_program_v1(),
        "session_metadata": metadata,
        "roles": roles,
        "role_mismatch_policy": role_policy,
        "public_view_role": "maker",
        "start_on_create": True,
    }


@pytest.fixture
def app():
    reset_access_handles()
    value = create_app_for_program(
        launch_spec=_launch_spec(),
    )
    value.config.update(TESTING=True)

    try:
        yield value
    finally:
        close_app_sessions(value)
        reset_access_handles()


def _access_id(app, role: str = "maker") -> str:
    return str(
        get_app_launch_bundle(app)["access_ids"][role]
    )


def _path(access_id: str, suffix: str) -> str:
    return f"/think/run/{access_id}{suffix}"


def _latest(client, access_id: str) -> int:
    response = client.get(
        _path(access_id, "/latest-event-seq/")
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    packet = response.get_json()
    assert set(packet) == {"kind", "access_id", "event_seq"}
    return int(packet["event_seq"])


def _events(
    client,
    access_id: str,
    *,
    after: int = 0,
    identity_id: str = "boundary-poller",
) -> Dict[str, Any]:
    response = client.get(
        _path(access_id, "/events/"),
        query_string={
            "identity_id": identity_id,
            "after_event_seq": after,
            "limit": 500,
        },
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return dict(response.get_json())


def _dispatch(
    client,
    access_id: str,
    *,
    cursor: int,
    request_id: str,
    identity_id: str,
    user_fill: Mapping[str, Any] | None = None,
    user_signal: Mapping[str, Any] | None = None,
    funked: bool = False,
):
    suffix = (
        "/dispatch-funked/"
        if funked
        else "/dispatch/"
    )
    return client.post(
        _path(access_id, suffix),
        json={
            "action": "STEP",
            "identity_id": identity_id,
            "request_id": request_id,
            "my_current_event_seq_number": cursor,
            "user_fill": dict(user_fill or {}),
            "user_signal": (
                None
                if user_signal is None
                else dict(user_signal)
            ),
        },
    )


def _eps(
    client,
    access_id: str,
    *,
    after: int = 0,
    limit: int = 500,
    window: int | None = None,
) -> Dict[str, Any]:
    query: Dict[str, Any] = {
        "after_seq": after,
        "limit": limit,
    }
    if window is not None:
        query["window"] = window
    response = client.get(
        _path(access_id, "/eps/"),
        query_string=query,
    )
    assert response.status_code == 200
    return dict(response.get_json())


def _assert_transport_extensions(
    packet: Mapping[str, Any],
    *,
    chain: bool,
) -> None:
    optional = (
        CHAIN_OPTIONAL_KEYS
        if chain
        else DIRECT_OPTIONAL_KEYS
    )
    assert set(packet) - set(HARMONIZED_DISPATCH_KEYS) <= optional


def _assert_harmonized_receipt(
    packet: Mapping[str, Any],
    *,
    kind: str,
    request_id: str,
    outcome: str,
    applied: bool,
    rejected: bool,
    committed: bool,
) -> None:
    for key in HARMONIZED_DISPATCH_KEYS:
        assert key in packet, (
            f"missing harmonized key {key!r}: {packet!r}"
        )

    assert packet["kind"] == kind
    assert packet["request_id"] == request_id
    assert packet["events_only"] is True
    assert packet["applied"] is applied
    assert packet["rejected"] is rejected
    assert packet["dispatch_outcome"] == outcome
    assert packet["write_committed"] is committed

    concurrency = packet["dispatch_concurrency"]
    assert set(concurrency) == CONCURRENCY_KEYS
    assert concurrency["kind"] == (
        "live_session_dispatch_concurrency_receipt_v1"
    )
    assert concurrency["request_id"] == request_id
    assert concurrency["applied"] is applied
    assert concurrency["rejected"] is rejected
    assert concurrency["idempotent_replay"] is False
    assert concurrency["coordination_layer"] == (
        "flask_single_process"
    )
    assert type(concurrency["before_event_seq"]) is int
    assert type(concurrency["after_event_seq"]) is int

    staleness = packet["dispatch_staleness"]
    assert staleness["kind"] == (
        "live_session_dispatch_staleness_receipt_v1"
    )
    assert type(staleness["observed_event_seq"]) is int


def _assert_provisional_controller_envelopes_are_balanced(
    progress: Mapping[str, Any],
) -> None:
    controller = [
        row["event"]
        for row in list(progress.get("events") or [])
        if (
            isinstance(row, Mapping)
            and isinstance(row.get("event"), Mapping)
            and row["event"].get("kind")
            == "controller_loop_event_v1"
        )
    ]

    by_dispatch: Dict[str, list[Mapping[str, Any]]] = {}
    for event in controller:
        dispatch_id = str(event.get("dispatch_id") or "")
        assert dispatch_id
        assert "event_seq" not in event
        by_dispatch.setdefault(dispatch_id, []).append(event)

    assert by_dispatch
    for dispatch_id, events in by_dispatch.items():
        assert [event.get("phase") for event in events] == [
            "start",
            "end",
        ], (
            f"unbalanced provisional controller envelope "
            f"{dispatch_id!r}: {events!r}"
        )


def test_direct_accepted_receipt_matches_the_harmonized_server_contract(
    app,
) -> None:
    access_id = _access_id(app)
    client = app.test_client()
    C = _latest(client, access_id)
    request_id = f"flask-accepted-{uuid4().hex}"
    identity_id = "flask-accepted-client"

    response = _dispatch(
        client,
        access_id,
        cursor=C,
        request_id=request_id,
        identity_id=identity_id,
        user_fill={
            "complex": valid_complex_describe_fill()["complex"],
        },
    )

    assert response.status_code == 200
    packet = response.get_json()
    _assert_transport_extensions(packet, chain=False)
    _assert_harmonized_receipt(
        packet,
        kind=DIRECT_KIND,
        request_id=request_id,
        outcome="applied",
        applied=True,
        rejected=False,
        committed=True,
    )
    assert packet["ok"] is True
    assert packet["rejection_kind"] is None
    assert packet["dispatcher_identity_id"] == identity_id
    assert packet["dispatcher_role"] == "maker"
    assert packet["dispatch_staleness"]["reason"] == "at_high_water"
    assert packet["dispatch_concurrency"]["before_event_seq"] == C
    assert packet["dispatch_concurrency"]["after_event_seq"] > C


def test_semantic_rejection_is_an_admitted_http_200_receipt(app) -> None:
    access_id = _access_id(app)
    client = app.test_client()
    C = _latest(client, access_id)
    request_id = f"flask-semantic-{uuid4().hex}"

    response = _dispatch(
        client,
        access_id,
        cursor=C,
        request_id=request_id,
        identity_id="flask-semantic-client",
        user_fill={
            "complex": {
                "description": "too short",
            },
        },
    )

    assert response.status_code == 200
    packet = response.get_json()
    _assert_transport_extensions(packet, chain=False)
    _assert_harmonized_receipt(
        packet,
        kind=DIRECT_KIND,
        request_id=request_id,
        outcome="semantic_rejected",
        applied=True,
        rejected=False,
        committed=False,
    )
    assert packet["ok"] is True
    assert packet["last_error"]


def test_future_cursor_rejection_is_exact_and_eventless(app) -> None:
    access_id = _access_id(app)
    client = app.test_client()
    A = _latest(client, access_id)
    before = _events(
        client,
        access_id,
        identity_id="flask-future-before",
    )
    request_id = f"flask-future-{uuid4().hex}"

    response = _dispatch(
        client,
        access_id,
        cursor=A + 1,
        request_id=request_id,
        identity_id="flask-future-client",
    )

    assert response.status_code == 409
    packet = response.get_json()
    _assert_transport_extensions(packet, chain=False)
    _assert_harmonized_receipt(
        packet,
        kind=DIRECT_KIND,
        request_id=request_id,
        outcome="stale_rejected",
        applied=False,
        rejected=True,
        committed=False,
    )
    assert packet["ok"] is False
    assert packet["rejection_kind"] == "future_event_cursor"
    assert packet["dispatcher_identity_id"] is None
    assert packet["dispatcher_role"] is None
    assert packet["dispatch_staleness"]["reason"] == "future_event_cursor"
    assert packet["dispatch_concurrency"]["before_event_seq"] == A
    assert packet["dispatch_concurrency"]["after_event_seq"] == A
    assert _latest(client, access_id) == A
    assert _events(
        client,
        access_id,
        identity_id="flask-future-before",
    ) == before


def test_admitted_receipt_high_water_and_controller_envelope_commit_together(
    app,
) -> None:
    access_id = _access_id(app)
    client = app.test_client()
    C = _latest(client, access_id)
    identity_id = "flask-coherence-client"
    request_id = f"flask-coherence-{uuid4().hex}"

    response = _dispatch(
        client,
        access_id,
        cursor=C,
        request_id=request_id,
        identity_id=identity_id,
        user_fill={
            "complex": valid_complex_describe_fill()["complex"],
        },
        user_signal={
            "datum_id": "complex",
            "kind": "reseed",
            "info": {"proof": "receipt-event-coherence"},
        },
    )
    assert response.status_code == 200
    packet = response.get_json()
    after = int(
        packet["dispatch_concurrency"]["after_event_seq"]
    )

    assert after == _latest(client, access_id)
    page = _events(
        client,
        access_id,
        after=C,
        identity_id="flask-coherence-poller",
    )
    assert page["next_after_event_seq"] == after

    actor_controller_events = [
        event
        for event in page["events"]
        if event.get("kind") == "controller_loop_event_v1"
        and event.get("dispatcher_identity_id") == identity_id
    ]
    assert [event["phase"] for event in actor_controller_events] == [
        "start",
        "end",
    ]
    assert (
        actor_controller_events[0]["dispatch_id"]
        == actor_controller_events[1]["dispatch_id"]
    )

    eps_page = _eps(
        client,
        access_id,
        after=0,
    )
    assert eps_page["kind"] == "thinkument_eps_page_v1"
    request_rows = [
        row
        for row in eps_page["rows"]
        if row.get("request_id") == request_id
    ]
    assert request_rows
    assert all("event_seq" not in row for row in request_rows)
    assert all(
        row["trident_dispatch_id"] == actor_controller_events[0]["dispatch_id"]
        and row["theta_event_seq_at_emit"] == C
        for row in request_rows
    )


def test_eps_is_role_modulated_across_handles_on_same_run(app) -> None:
    maker_id = _access_id(app, "maker")
    auditor_id = _access_id(app, "auditor")
    client = app.test_client()
    before_eps = _eps(client, maker_id)["eps_head"]
    request_id = f"flask-eps-role-mod-{uuid4().hex}"
    identity_id = "flask-eps-owner"

    response = _dispatch(
        client,
        maker_id,
        cursor=_latest(client, maker_id),
        request_id=request_id,
        identity_id=identity_id,
        user_fill={
            "complex": valid_complex_describe_fill()["complex"],
        },
        user_signal={
            "datum_id": "complex",
            "kind": "reseed",
            "info": {"proof": "role-mod"},
        },
    )
    assert response.status_code == 200

    maker_eps = _eps(client, maker_id, after=before_eps)
    auditor_eps = _eps(client, auditor_id, after=before_eps)
    assert maker_eps["rows"]
    assert len(maker_eps["rows"]) == len(auditor_eps["rows"])
    assert any(
        row["datum_id"] == "complex" and row["obfuscated"] is False
        for row in maker_eps["rows"]
    )
    assert all(
        row["obfuscated"] is True
        and row["datum_id"] is None
        and row["payload"] is None
        for row in auditor_eps["rows"]
        if maker_eps["rows"][auditor_eps["rows"].index(row)]["datum_id"] == "complex"
    )


def test_datum_eps_is_visible_before_flask_dispatch_completion(
    app,
) -> None:
    access_id = _access_id(app)
    request_id = f"flask-inflight-datum-{uuid4().hex}"
    identity_id = "flask-inflight-datum-owner"
    datum_published = Event()
    release_dispatch = Event()
    original_append = InMemoryEpsLog.append

    with app.test_client() as client:
        cursor = _latest(client, access_id)
        before_eps_head = _eps(client, access_id)["eps_head"]

    def blocking_append(
        store: InMemoryEpsLog,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        row = original_append(store, **kwargs)

        if (
            kwargs.get("request_id") == expected_request_id
            and not datum_published.is_set()
        ):
            datum_published.set()
            if not release_dispatch.wait(timeout=10):
                raise AssertionError(
                    "test did not release the in-flight datum dispatch"
                )

        return row

    expected_request_id = request_id

    def submit():
        with app.test_client() as client:
            return _dispatch(
                client,
                access_id,
                cursor=cursor,
                request_id=request_id,
                identity_id=identity_id,
            )

    with patch.object(
        InMemoryEpsLog,
        "append",
        new=blocking_append,
    ):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(submit)

            try:
                assert datum_published.wait(timeout=10)

                with app.test_client() as client:
                    live_eps = _eps(
                        client,
                        access_id,
                        after=before_eps_head,
                    )

                assert live_eps["rows"]
                assert all(
                    row["request_id"] == request_id
                    and "event_seq" not in row
                    for row in live_eps["rows"]
                )
            finally:
                release_dispatch.set()

            response = future.result(timeout=20)

    assert response.status_code == 200


def test_chain_route_uses_the_same_projection_and_chain_kind(app) -> None:
    access_id = _access_id(app)
    client = app.test_client()
    C = _latest(client, access_id)
    request_id = f"flask-chain-{uuid4().hex}"

    response = _dispatch(
        client,
        access_id,
        cursor=C,
        request_id=request_id,
        identity_id="flask-chain-client",
        funked=True,
    )

    assert response.status_code == 200
    packet = response.get_json()
    _assert_transport_extensions(packet, chain=True)
    _assert_harmonized_receipt(
        packet,
        kind=CHAIN_KIND,
        request_id=request_id,
        outcome="applied",
        applied=True,
        rejected=False,
        committed=False,
    )
    assert packet["chainreactionTM_receipt"]["enabled"] is False



@pytest.mark.parametrize(
    "body",
    [
        {
            "action": "STEP",
            "identity_id": "missing-request-id",
            "my_current_event_seq_number": 0,
        },
        {
            "action": "STEP",
            "request_id": "missing-identity",
            "my_current_event_seq_number": 0,
        },
        {
            "action": "STEP",
            "identity_id": "missing-cursor",
            "request_id": "missing-cursor",
        },
        {
            "action": "STEP",
            "identity_id": "bool-cursor",
            "request_id": "bool-cursor",
            "my_current_event_seq_number": True,
        },
        {
            "action": "STEP",
            "identity_id": "string-cursor",
            "request_id": "string-cursor",
            "my_current_event_seq_number": "0",
        },
        {
            "action": "STEP",
            "identity_id": "non-string-request-id",
            "request_id": 123,
            "my_current_event_seq_number": 0,
        },
        {
            "action": "STEP",
            "identity_id": "unknown-key",
            "request_id": "unknown-key",
            "my_current_event_seq_number": 0,
            "unexpected": True,
        },
        {
            "action": "NOT_AN_ACTION",
            "identity_id": "bad-action",
            "request_id": "bad-action",
            "my_current_event_seq_number": 0,
        },
    ],
)
def test_malformed_dispatch_transport_is_http_400_and_eventless(
    app,
    body,
) -> None:
    access_id = _access_id(app)
    client = app.test_client()
    before_seq = _latest(client, access_id)
    before_events = _events(
        client,
        access_id,
        identity_id="flask-malformed-before",
    )

    response = client.post(
        _path(access_id, "/dispatch/"),
        json=body,
    )

    assert response.status_code == 400
    assert "error" in response.get_json()
    assert _latest(client, access_id) == before_seq
    assert _events(
        client,
        access_id,
        identity_id="flask-malformed-before",
    ) == before_events


def test_payload_role_cannot_spoof_the_sealed_flask_handle(app) -> None:
    access_id = _access_id(app)
    client = app.test_client()
    before_seq = _latest(client, access_id)

    response = client.post(
        _path(access_id, "/dispatch/"),
        json={
            "action": "STEP",
            "identity_id": "flask-role-spoof",
            "request_id": "flask-role-spoof",
            "my_current_event_seq_number": before_seq,
            "role": "reviewer",
        },
    )

    assert response.status_code == 400
    assert (
        "sealed access-handle role"
        in response.get_json()["error"]
    )
    assert _latest(client, access_id) == before_seq


def test_role_write_rejection_is_eventless_on_both_theta_and_eps(
    app,
) -> None:
    access_id = _access_id(app, "reviewer")
    client = app.test_client()
    before_seq = _latest(client, access_id)
    before_eps_head = _eps(client, access_id)["eps_head"]
    before_events = _events(
        client,
        access_id,
        identity_id="flask-permission-before",
    )
    request_id = f"flask-permission-{uuid4().hex}"
    identity_id = "flask-permission-reviewer"

    response = _dispatch(
        client,
        access_id,
        cursor=before_seq,
        request_id=request_id,
        identity_id=identity_id,
        user_fill={
            "complex": valid_complex_describe_fill()["complex"],
        },
    )

    assert response.status_code == 403
    packet = response.get_json()
    _assert_transport_extensions(packet, chain=False)
    _assert_harmonized_receipt(
        packet,
        kind="live_session_dispatch_rejected_v1",
        request_id=request_id,
        outcome="permission_rejected",
        applied=False,
        rejected=True,
        committed=False,
    )
    assert packet["rejection_kind"] == "permission_denied"
    assert _latest(client, access_id) == before_seq
    assert _events(
        client,
        access_id,
        identity_id="flask-permission-before",
    ) == before_events

    eps_page = _eps(
        client,
        access_id,
        after=before_eps_head,
    )
    assert eps_page["eps_head"] == before_eps_head
    assert eps_page["rows"] == []


def test_owner_pid_guard_rejects_a_secondary_process(app) -> None:
    access_id = _access_id(app)
    original = app.extensions[
        LOCAL_FLASK_OWNER_PID_EXTENSION_KEY
    ]
    app.extensions[
        LOCAL_FLASK_OWNER_PID_EXTENSION_KEY
    ] = int(original) + 1

    try:
        response = app.test_client().get(
            _path(access_id, "/latest-event-seq/")
        )
    finally:
        app.extensions[
            LOCAL_FLASK_OWNER_PID_EXTENSION_KEY
        ] = original

    assert response.status_code == 503
    packet = response.get_json()
    assert packet["runtime_profile"] == LOCAL_FLASK_RUNTIME_PROFILE
    assert "single-process" in packet["error"]


def test_launcher_forbids_reloader_and_multiple_processes() -> None:
    fake_app = Mock()

    with (
        patch(
            "live_vial._flask.launch_local_flask_server."
            "create_app_for_program",
            return_value=fake_app,
        ),
        patch(
            "live_vial._flask.launch_local_flask_server."
            "print_launcher_debug_surface",
        ),
        patch(
            "live_vial._flask.launch_local_flask_server."
            "print_access_handles_for_program",
        ),
        patch(
            "live_vial._flask.launch_local_flask_server."
            "close_app_sessions",
        ) as close_sessions,
    ):
        serve_program_wrapper_on_flask(
            {
                "program_language": LANG_THINK_PROGRAM_V1,
                "program": demo_think_program_v1(),
            },
            raw_target="test-wrapper",
            host="127.0.0.1",
            port=5055,
            debug=True,
        )

    fake_app.run.assert_called_once_with(
        host="127.0.0.1",
        port=5055,
        debug=True,
        use_reloader=False,
        threaded=True,
        processes=1,
    )
    close_sessions.assert_called_once_with(fake_app)