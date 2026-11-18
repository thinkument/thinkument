from __future__ import annotations

"""
Local Flask highest-façade E2E
==============================

This is the executable outside-user story for the local Flask server.

Architectural level
-------------------

The core highest façade already proves:

* canonical event sequencing;
* role-aware reads and writes;
* optimistic target-aware staleness;
* process-local per-session dispatch serialization;
* semantic versus stale rejection;
* chain-reaction serialization;
* bounded stateless event polling.

This sheet does not recreate those lower proofs.

It proves the additional contract introduced by the Flask transport:

* one exact single-process threaded runtime profile;
* role-sealed capability handles;
* HTTP launch and session lifecycle;
* exact JSON dispatch payloads;
* mandatory request correlation;
* exact query-string polling payloads;
* HTTP status translation;
* scalar latest-sequence polling;
* canonical event-page transport;
* direct and chain dispatch routes;
* whole-page shell delivery;
* framework-agnostic aggregated static delivery;
* theta canonical-event and epsilon provisional-progress normalization;
* one downstream information-drinker socket;
* the exact Q/X/writeX/dispatch loopback capability seam;
* concurrent HTTP callers sharing one serialized session write lane;
* independent write lanes for different sessions;
* stale refresh, intent rebuild, and retry through HTTP;
* cleanup of every session created through the Flask app.

Static ownership law
--------------------

Physical static ownership is package-local:

    live_vial/_js/thinkumentJS/
        wrapper_shim.js
        platform/

    _vial_js_interactive/formreactJS/
        core/
        renderportfolioTM__dom_asset_examples/

The browser-facing namespace remains one stable namespace:

    /think/static/wrapper_shim.js
    /think/static/platform/...
    /think/static/core/...
    /think/static/renderportfolioTM__dom_asset_examples/...

Therefore this sheet deliberately tests logical static names, not physical
package directories. The separate static-aggregation equivalence proof owns
physical-root membership and Flask/Django resolver equivalence.

Public HTTP usage
-----------------

A client receives a role-sealed ``access_id``. It does not receive or select the
underlying engine session id.

Cheap outer poll:

    GET /think/run/<access_id>/latest-event-seq/

Bounded inner catch-up:

    GET /think/run/<access_id>/events/
        ?identity_id=<client>
        &after_event_seq=<C>
        &limit=<page-size>

Checked dispatch:

    POST /think/run/<access_id>/dispatch/

    {
        "request_id": "dispatch-browser-tab-1-000001",
        "action": "STEP",
        "identity_id": "browser-tab-1",
        "my_current_event_seq_number": C,
        "user_fill": {...},
        "user_signal": null
    }

``request_id`` is transport correlation metadata. It is required on every
dispatch and does not replace the canonical event cursor or highest-façade
staleness checks.

The client advances C using ``next_after_event_seq``, not the final visible
event sequence. Role projection may intentionally hide canonical event bodies.

HTTP outcome law
----------------

    200
        Admitted dispatch, including semantic rejection.

    400
        Malformed transport payload, request id, action, cursor, query,
        or role spoof.

    403
        Role authorization failure.

    404
        Unknown role-sealed access handle.

    409
        Highest-façade stale/future-cursor rejection.

    503
        Request reached a process other than the app-owning process.

Concurrency law
---------------

The local Flask runtime is exactly one OS process with concurrent request
threads. Every write still enters ``_thinksessions.run.run_from_here``.

Therefore:

    same session
        -> one highest-façade process-local serialized write lane

    different sessions
        -> independent serialized write lanes that may run concurrently

The browser has one serialized state-commit lane shared by canonical theta,
provisional epsilon, and explicit higher-JS writeX transitions. DOM behavior
itself is ordinary higher JavaScript and reaches ThinkumentJS only through the
loopback capability.

This sheet deliberately does not claim cross-process or restart-safe
serialization. That belongs to the production Django persistence boundary.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from typing import Any, Dict, Mapping
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
from __staticfiles_mgmt.globals import (
    LOCAL_FLASK_OWNER_PID_EXTENSION_KEY,
    LOCAL_FLASK_RUNTIME_PROFILE,
    LOCAL_FLASK_RUNTIME_PROFILE_EXTENSION_KEY,
    LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY,
    WEB_SHIM_FILENAME,
)
from live_vial._flask.adapter import (
    reset_access_handles,
)
from live_vial._flask.server_wrapper import (
    close_app_sessions,
    create_app_for_program,
    get_app_launch_bundle,
)


# =============================================================================
# Registration and app construction
# =============================================================================

def _register_demo() -> None:
    """Register the authored demo components consumed by the Flask server."""
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
    start_on_create: bool = True,
    public_view_role: str = "maker",
    chainreaction_enabled: bool = False,
) -> Dict[str, Any]:
    """Build one exact launcher-owned local Flask program specification."""
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
        "public_view_role": public_view_role,
        "start_on_create": start_on_create,
    }


@pytest.fixture
def app():
    """Yield one started local Flask app and release every created session."""
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


# =============================================================================
# HTTP client helpers
# =============================================================================

def _handles(app) -> Dict[str, str]:
    return dict(get_app_launch_bundle(app)["access_ids"])


def _path(access_id: str, suffix: str = "") -> str:
    return f"/think/run/{access_id}{suffix}"


def _request_id(label: str = "test-dispatch") -> str:
    return f"{label}-{uuid4().hex}"


def _latest_packet(client, access_id: str) -> Dict[str, Any]:
    response = client.get(
        _path(access_id, "/latest-event-seq/")
    )
    assert response.status_code == 200

    packet = response.get_json()
    assert packet["kind"] == "thinkument_latest_event_seq_v1"
    assert packet["access_id"] == access_id
    assert type(packet["event_seq"]) is int
    assert packet["event_seq"] >= 0
    return dict(packet)


def _latest(client, access_id: str) -> int:
    return int(_latest_packet(client, access_id)["event_seq"])


def _dispatch(
    client,
    access_id: str,
    *,
    cursor: Any,
    request_id: Any | None = None,
    user_fill: Mapping[str, Any] | None = None,
    user_signal: Mapping[str, Any] | None = None,
    funked: bool = False,
    identity_id: str = "test-client",
    action: str = "STEP",
):
    endpoint = (
        "/dispatch-funked/"
        if funked
        else "/dispatch/"
    )
    return client.post(
        _path(access_id, endpoint),
        json={
            "request_id": (
                _request_id(identity_id)
                if request_id is None
                else request_id
            ),
            "action": action,
            "identity_id": identity_id,
            "my_current_event_seq_number": cursor,
            "user_fill": dict(user_fill or {}),
            "user_signal": (
                None
                if user_signal is None
                else dict(user_signal)
            ),
        },
    )


def _event_page(
    client,
    access_id: str,
    *,
    identity_id: str,
    cursor: Any,
    limit: Any = 100,
):
    return client.get(
        _path(access_id, "/events/"),
        query_string={
            "identity_id": identity_id,
            "after_event_seq": cursor,
            "limit": limit,
        },
    )


def _catch_up(
    client,
    access_id: str,
    *,
    identity_id: str,
    cursor: int,
    limit: int = 2,
) -> tuple[int, list[Dict[str, Any]], int, int]:
    """
    Real HTTP realization of the two-loop polling pattern.

    Exactly one scalar outer poll is made. Event pages are requested only when
    the canonical scalar differs from the local cursor.
    """
    C = int(cursor)
    scalar_polls = 1
    event_page_polls = 0
    A = _latest(client, access_id)
    events: list[Dict[str, Any]] = []

    while C < A:
        response = _event_page(
            client,
            access_id,
            identity_id=identity_id,
            cursor=C,
            limit=limit,
        )
        event_page_polls += 1

        assert response.status_code == 200
        page = response.get_json()

        assert page["kind"] == "live_session_events_since_v1"
        assert page["identity_id"] == identity_id
        assert page["after_event_seq"] == C
        assert page["session_latest_event_seq"] >= A
        assert page["scanned_through_event_seq"] == (
            page["next_after_event_seq"]
        )

        next_C = int(page["next_after_event_seq"])
        assert next_C > C

        events.extend(page["events"])
        C = next_C
        A = int(page["session_latest_event_seq"])

    return C, events, scalar_polls, event_page_polls


def _assert_no_store_headers(response) -> None:
    assert response.headers["Cache-Control"] == (
        "no-store, private, max-age=0"
    )
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Robots-Tag"] == (
        "noindex, nofollow, noarchive"
    )
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Thinkument-Runtime-Profile"] == (
        LOCAL_FLASK_RUNTIME_PROFILE
    )


# =============================================================================
# A. Runtime profile and launch lifecycle
# =============================================================================

def test_app_declares_the_exact_single_process_runtime_profile(app) -> None:
    assert app.extensions[
        LOCAL_FLASK_RUNTIME_PROFILE_EXTENSION_KEY
    ] == LOCAL_FLASK_RUNTIME_PROFILE

    owner_pid = app.extensions[
        LOCAL_FLASK_OWNER_PID_EXTENSION_KEY
    ]
    assert type(owner_pid) is int
    assert owner_pid > 0

    session_ids = app.extensions[
        LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY
    ]
    assert isinstance(session_ids, set)
    assert session_ids == {
        str(get_app_launch_bundle(app)["session_id"])
    }


def test_initial_launch_bundle_has_one_handle_per_role(app) -> None:
    bundle = get_app_launch_bundle(app)
    handles = _handles(app)

    assert bundle["public_view_role"] == "maker"
    assert bundle["selected_access_id"] == handles["maker"]
    assert handles["default"] == handles["maker"]

    assert {
        "default",
        "maker",
        "reviewer",
        "release_ai",
        "auditor",
    } == set(handles)

    assert all(
        isinstance(access_id, str) and access_id.startswith("run-")
        for access_id in handles.values()
    )


def test_create_route_can_create_an_unstarted_session(app) -> None:
    client = app.test_client()
    initial_session_ids = set(
        app.extensions[
            LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY
        ]
    )

    response = client.post(
        "/think/create",
        json={
            "start_on_create": False,
        },
    )
    assert response.status_code == 200

    packet = response.get_json()
    assert packet["kind"] == "thinkument_local_flask_launch_result_v1"
    assert packet["public_view_role"] == "maker"
    assert packet["state"]["event_kind"] == "ATSTART"
    assert packet["state"]["finished"] is False

    created_access_id = packet["selected_access_id"]
    assert packet["state"]["access_id"] == created_access_id
    assert packet["handles"]["default"]["role"] == "maker"

    created_session_ids = set(
        app.extensions[
            LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY
        ]
    )
    assert len(created_session_ids) == len(initial_session_ids) + 1
    assert packet["session_id"] in created_session_ids

    assert _latest(client, created_access_id) == 0


def test_create_route_rejects_launcher_owned_fields(app) -> None:
    response = app.test_client().post(
        "/think/create",
        json={
            "start_on_create": True,
            "program": {},
        },
    )

    assert response.status_code == 400
    error = response.get_json()["error"]
    assert "accepts only start_on_create" in error
    assert "program" in error


def test_close_app_sessions_is_idempotent() -> None:
    reset_access_handles()
    value = create_app_for_program(
        launch_spec=_launch_spec(),
    )
    value.config.update(TESTING=True)

    try:
        first = close_app_sessions(value)
        second = close_app_sessions(value)

        assert len(first) == 1
        assert second == []
        assert value.extensions[
            LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY
        ] == set()
    finally:
        close_app_sessions(value)
        reset_access_handles()


# =============================================================================
# B. Route bundle, shell, headers, and capability handles
# =============================================================================

def test_page_and_route_bundle_are_complete(app) -> None:
    bundle = get_app_launch_bundle(app)
    selected = str(bundle["selected_access_id"])

    client = app.test_client()
    page = client.get(_path(selected, "/page/"))

    assert page.status_code == 200
    assert page.mimetype == "text/html"

    text = page.get_data(as_text=True)
    assert "<!doctype html>" in text
    assert "thinkument_web_client_config_v1" in text
    assert "latestEventSeq" in text
    assert "dispatchFunked" in text
    assert "initialEventSeq" in text

    assert "basePeriodMs" in text
    assert "dispatchPeriodMs" in text
    assert "dispatchWindowMs" in text
    assert "remoteActivityPeriodMs" in text
    assert "remoteActivityWindowMs" in text
    assert "epsPollPeriodMs" in text
    assert "maxEpsRows" in text

    assert "basePollIntervalMs" not in text
    assert "alertPollIntervalMs" not in text
    assert "alertDecayMultiplier" not in text
    assert "idleBackoffMultiplier" not in text
    assert "maxIdlePollIntervalMs" not in text

    assert "thinkument_dispatch_contract_v1" in text
    assert "request_id" in text
    assert '"opinionation"' in text
    assert '"theta":' not in text
    assert '"gamma":' not in text
    assert '"epsilon":' not in text

    root = client.get("/")
    assert root.status_code == 302
    assert root.headers["Location"].endswith(
        f"/think/run/{selected}/page/"
    )


def test_json_and_html_routes_apply_local_capability_headers(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    public = client.get(_path(access_id))
    page = client.get(_path(access_id, "/page/"))
    latest = client.get(
        _path(access_id, "/latest-event-seq/")
    )

    for response in (public, page, latest):
        assert response.status_code == 200
        _assert_no_store_headers(response)


def test_public_state_uses_access_id_not_engine_session_id(app) -> None:
    access_id = _handles(app)["maker"]
    response = app.test_client().get(_path(access_id))

    assert response.status_code == 200
    packet = response.get_json()

    assert packet["kind"] == "thinkument_live_session_public_state_v1"
    assert packet["access_id"] == access_id
    assert "session_id" not in packet
    assert packet["role"] == "maker"
    assert isinstance(packet["ctx"], dict)
    assert packet["event_kind"] == packet["ctx"]["kind"]
    assert packet["finished"] is False


@pytest.mark.parametrize(
    "suffix,method",
    [
        ("", "get"),
        ("/latest-event-seq/", "get"),
        ("/events/?identity_id=x", "get"),
        ("/page/", "get"),
        ("/dispatch/", "post"),
        ("/dispatch-funked/", "post"),
    ],
)
def test_unknown_access_handle_is_404(
    app,
    suffix: str,
    method: str,
) -> None:
    client = app.test_client()
    path = _path("run-does-not-exist", suffix)

    if method == "post":
        response = client.post(
            path,
            json={
                "request_id": _request_id("unknown"),
                "action": "STEP",
                "identity_id": "unknown",
                "my_current_event_seq_number": 0,
                "user_fill": {},
                "user_signal": None,
            },
        )
    else:
        response = client.get(path)

    assert response.status_code == 404
    assert "unknown access handle" in response.get_json()["error"]


def test_role_is_sealed_by_access_handle(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    response = client.post(
        _path(access_id, "/dispatch/"),
        json={
            "request_id": _request_id("role-spoof"),
            "action": "STEP",
            "identity_id": "role-spoof",
            "role": "reviewer",
            "my_current_event_seq_number": _latest(
                client,
                access_id,
            ),
            "user_fill": {},
            "user_signal": None,
        },
    )

    assert response.status_code == 400
    assert "sealed" in response.get_json()["error"]


def test_role_authorization_failure_maps_to_http_403(app) -> None:
    reviewer_access_id = _handles(app)["reviewer"]
    client = app.test_client()
    C = _latest(client, reviewer_access_id)
    request_id = _request_id("reviewer-spoof-write")

    response = _dispatch(
        client,
        reviewer_access_id,
        cursor=C,
        request_id=request_id,
        identity_id="reviewer-spoof-write",
        user_fill={
            "complex": valid_complex_describe_fill()["complex"],
        },
    )

    assert response.status_code == 403

    packet = response.get_json()

    assert packet["request_id"] == request_id
    assert packet["kind"] == "live_session_dispatch_rejected_v1"
    assert packet["ok"] is False
    assert packet["applied"] is False
    assert packet["rejected"] is True
    assert packet["rejection_kind"] == "permission_denied"
    assert packet["dispatch_outcome"] == "permission_rejected"
    assert packet["write_committed"] is False
    assert packet["events_only"] is True

    concurrency = packet["dispatch_concurrency"]
    assert concurrency["before_event_seq"] == C
    assert concurrency["after_event_seq"] == C

    staleness = packet["dispatch_staleness"]
    assert staleness["checked"] is False
    assert staleness["outcome"] == "not_checked"
    assert staleness["reason"] == "permission_denied"

    assert _latest(client, reviewer_access_id) == C


# =============================================================================
# C. Exact dispatch HTTP grammar
# =============================================================================

def test_dispatch_accepts_the_exact_final_payload_shape(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()
    request_id = _request_id("exact-payload")

    response = client.post(
        _path(access_id, "/dispatch/"),
        json={
            "request_id": request_id,
            "action": "STEP",
            "identity_id": "exact-payload-client",
            "my_current_event_seq_number": _latest(
                client,
                access_id,
            ),
            "user_fill": {},
            "user_signal": None,
        },
    )

    assert response.status_code == 200
    packet = response.get_json()

    assert packet["request_id"] == request_id
    assert packet["kind"] == (
        "live_session_events_only_dispatch_receipt_v1"
    )


@pytest.mark.parametrize(
    "bad_request_id",
    [None, "", "   ", True, 1, 1.0, [], {}],
)
def test_dispatch_requires_a_nonempty_string_request_id(
    app,
    bad_request_id: Any,
) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    payload = {
        "request_id": bad_request_id,
        "action": "STEP",
        "identity_id": "bad-request-id",
        "my_current_event_seq_number": _latest(
            client,
            access_id,
        ),
        "user_fill": {},
        "user_signal": None,
    }

    response = client.post(
        _path(access_id, "/dispatch/"),
        json=payload,
    )

    assert response.status_code == 400
    assert "request_id" in response.get_json()["error"]


def test_dispatch_requires_request_id_key(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    response = client.post(
        _path(access_id, "/dispatch/"),
        json={
            "action": "STEP",
            "identity_id": "missing-request-id",
            "my_current_event_seq_number": _latest(
                client,
                access_id,
            ),
            "user_fill": {},
            "user_signal": None,
        },
    )

    assert response.status_code == 400
    assert "request_id" in response.get_json()["error"]


@pytest.mark.parametrize(
    "bad_cursor",
    [None, True, "1", 1.0, -1],
)
def test_dispatch_requires_exact_non_negative_json_integer(
    app,
    bad_cursor: Any,
) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    payload = {
        "request_id": _request_id("bad-cursor"),
        "action": "STEP",
        "identity_id": "bad-cursor",
        "user_fill": {},
        "user_signal": None,
    }
    if bad_cursor is not None:
        payload["my_current_event_seq_number"] = bad_cursor

    response = client.post(
        _path(access_id, "/dispatch/"),
        json=payload,
    )
    assert response.status_code == 400


def test_dispatch_rejects_non_object_json(app) -> None:
    access_id = _handles(app)["maker"]
    response = app.test_client().post(
        _path(access_id, "/dispatch/"),
        data="[]",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "request body must be an object" in (
        response.get_json()["error"]
    )


def test_dispatch_rejects_invalid_json(app) -> None:
    access_id = _handles(app)["maker"]
    response = app.test_client().post(
        _path(access_id, "/dispatch/"),
        data="{",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "invalid JSON" in response.get_json()["error"]


def test_dispatch_requires_identity_id(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    response = client.post(
        _path(access_id, "/dispatch/"),
        json={
            "request_id": _request_id("missing-identity"),
            "action": "STEP",
            "identity_id": "",
            "my_current_event_seq_number": _latest(
                client,
                access_id,
            ),
            "user_fill": {},
            "user_signal": None,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "identity_id is required"


def test_dispatch_rejects_unknown_action(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    response = _dispatch(
        client,
        access_id,
        cursor=_latest(client, access_id),
        action="NOT_AN_ACTION",
    )

    assert response.status_code == 400
    assert "unknown action" in response.get_json()["error"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_fill", []),
        ("user_fill", "not-an-object"),
        ("user_signal", []),
        ("user_signal", 1),
    ],
)
def test_dispatch_fill_and_signal_must_be_objects(
    app,
    field: str,
    value: Any,
) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    payload = {
        "request_id": _request_id("shape-client"),
        "action": "STEP",
        "identity_id": "shape-client",
        "my_current_event_seq_number": _latest(
            client,
            access_id,
        ),
        "user_fill": {},
        "user_signal": None,
    }
    payload[field] = value

    response = client.post(
        _path(access_id, "/dispatch/"),
        json=payload,
    )
    assert response.status_code == 400
    assert f"{field} must be an object" in (
        response.get_json()["error"]
    )


def test_dispatch_rejects_unknown_payload_keys(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    response = client.post(
        _path(access_id, "/dispatch/"),
        json={
            "request_id": _request_id("unknown-key"),
            "action": "STEP",
            "identity_id": "unknown-key-client",
            "my_current_event_seq_number": _latest(
                client,
                access_id,
            ),
            "user_fill": {},
            "user_signal": None,
            "unexpected_field": {
                "value": "not-part-of-the-contract",
            },
        },
    )

    assert response.status_code == 400
    error = response.get_json()["error"]
    assert "unknown dispatch payload keys" in error
    assert "unexpected_field" in error


def test_dispatch_receipt_echoes_request_id(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()
    request_id = _request_id("receipt-correlation")

    response = _dispatch(
        client,
        access_id,
        cursor=_latest(client, access_id),
        request_id=request_id,
        identity_id="receipt-correlation-client",
    )

    assert response.status_code == 200
    assert response.get_json()["request_id"] == request_id


# =============================================================================
# D. Exact event-polling HTTP grammar
# =============================================================================

def test_events_route_requires_identity_id(app) -> None:
    access_id = _handles(app)["maker"]
    response = app.test_client().get(
        _path(access_id, "/events/"),
        query_string={
            "after_event_seq": 0,
            "limit": 100,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "identity_id is required"


@pytest.mark.parametrize(
    "field,value",
    [
        ("after_event_seq", "-1"),
        ("after_event_seq", "1.0"),
        ("after_event_seq", "abc"),
        ("after_event_seq", "+1"),
        ("limit", "0"),
        ("limit", "-1"),
        ("limit", "1.0"),
        ("limit", "abc"),
        ("limit", "501"),
    ],
)
def test_events_route_rejects_noncanonical_query_integers(
    app,
    field: str,
    value: str,
) -> None:
    access_id = _handles(app)["maker"]

    query = {
        "identity_id": "bad-query-poller",
        "after_event_seq": "0",
        "limit": "100",
    }
    query[field] = value

    response = app.test_client().get(
        _path(access_id, "/events/"),
        query_string=query,
    )
    assert response.status_code == 400


def test_event_page_preserves_the_highest_facade_packet(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    response = _event_page(
        client,
        access_id,
        identity_id="packet-reader",
        cursor=0,
        limit=1,
    )

    assert response.status_code == 200
    packet = response.get_json()

    assert set(packet) == {
        "kind",
        "session_id",
        "identity_id",
        "role",
        "after_event_seq",
        "session_earliest_event_seq",
        "session_latest_event_seq",
        "scanned_through_event_seq",
        "next_after_event_seq",
        "canonical_gap_detected",
        "visibility_receipt",
        "events",
    }
    assert packet["kind"] == "live_session_events_since_v1"
    assert packet["identity_id"] == "packet-reader"
    assert packet["role"] == "maker"
    assert packet["after_event_seq"] == 0
    assert packet["next_after_event_seq"] >= 1
    assert isinstance(packet["events"], list)

    visibility = packet["visibility_receipt"]
    assert visibility["kind"] == (
        "live_session_event_visibility_receipt_v1"
    )
    assert visibility["scanned_through_event_seq"] == (
        packet["next_after_event_seq"]
    )


def test_repeating_one_event_read_is_stateless(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    first = _event_page(
        client,
        access_id,
        identity_id="stateless-reader",
        cursor=0,
        limit=2,
    )
    second = _event_page(
        client,
        access_id,
        identity_id="stateless-reader",
        cursor=0,
        limit=2,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json() == second.get_json()


# =============================================================================
# E. HTTP outcome translation
# =============================================================================

def test_semantic_rejection_is_http_200_not_stale_409(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()
    C = _latest(client, access_id)
    request_id = _request_id("semantic-rejection")

    response = _dispatch(
        client,
        access_id,
        cursor=C,
        request_id=request_id,
        user_fill={
            "complex": {
                "description": "too short",
            }
        },
    )

    assert response.status_code == 200
    packet = response.get_json()

    assert packet["request_id"] == request_id
    assert packet["ok"] is True
    assert packet["applied"] is True
    assert packet["rejected"] is False
    assert packet["rejection_kind"] is None
    assert packet["dispatch_outcome"] == "semantic_rejected"
    assert packet["write_committed"] is False
    assert packet["last_error"]


def test_future_cursor_maps_to_http_409_without_event_movement(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()
    A = _latest(client, access_id)
    request_id = _request_id("future-cursor")

    response = _dispatch(
        client,
        access_id,
        cursor=A + 1,
        request_id=request_id,
        identity_id="future-cursor-client",
    )

    assert response.status_code == 409
    packet = response.get_json()

    assert packet["request_id"] == request_id
    assert packet["ok"] is False
    assert packet["applied"] is False
    assert packet["rejected"] is True
    assert packet["rejection_kind"] == "future_event_cursor"
    assert packet["dispatch_outcome"] == "stale_rejected"
    assert packet["write_committed"] is False
    assert _latest(client, access_id) == A


def test_direct_dispatch_route_returns_small_events_only_receipt(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()
    C = _latest(client, access_id)
    request_id = _request_id("direct-route")

    response = _dispatch(
        client,
        access_id,
        cursor=C,
        request_id=request_id,
        identity_id="direct-route-client",
    )

    assert response.status_code == 200
    packet = response.get_json()

    assert packet["kind"] == (
        "live_session_events_only_dispatch_receipt_v1"
    )
    assert packet["request_id"] == request_id
    assert packet["events_only"] is True
    assert packet["ok"] is True
    assert packet["applied"] is True
    assert packet["rejected"] is False
    assert packet["dispatch_outcome"] == "applied"
    assert "dispatch_concurrency" in packet
    assert "dispatch_staleness" in packet

    assert "datum_widget_decls" not in packet
    assert "state" not in packet
    assert "raw_ctx" not in packet


def test_chain_dispatch_route_returns_chain_receipt(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()
    C = _latest(client, access_id)
    request_id = _request_id("chain-route")

    response = _dispatch(
        client,
        access_id,
        cursor=C,
        request_id=request_id,
        identity_id="chain-route-client",
        funked=True,
    )

    assert response.status_code == 200
    packet = response.get_json()

    assert packet["kind"] == (
        "live_session_events_only_chain_dispatch_receipt_v1"
    )
    assert packet["request_id"] == request_id
    assert packet["events_only"] is True
    assert packet["ok"] is True
    assert packet["applied"] is True
    assert packet["rejected"] is False
    assert "chainreactionTM_receipt" in packet
    assert packet["chainreactionTM_receipt"]["enabled"] is False
    assert "dispatch_concurrency" in packet
    assert "dispatch_staleness" in packet


# =============================================================================
# F. Latest-sequence scalar and two-loop polling
# =============================================================================

def test_latest_event_seq_read_is_tiny_pure_and_role_independent(app) -> None:
    handles = _handles(app)
    client = app.test_client()

    maker_packet = _latest_packet(client, handles["maker"])
    auditor_packet = _latest_packet(client, handles["auditor"])

    assert set(maker_packet) == {
        "kind",
        "access_id",
        "event_seq",
    }
    assert maker_packet["event_seq"] == auditor_packet["event_seq"]

    before = maker_packet["event_seq"]
    for _ in range(10):
        assert _latest(client, handles["maker"]) == before
        assert _latest(client, handles["auditor"]) == before


def test_latest_event_seq_increases_after_an_admitted_dispatch(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()
    before = _latest(client, access_id)

    response = _dispatch(
        client,
        access_id,
        cursor=before,
        identity_id="latest-monotonic-client",
        user_signal={
            "datum_id": "complex",
            "kind": "reseed",
            "info": {
                "reason": "latest-sequence-proof",
            },
        },
    )
    assert response.status_code == 200

    after = _latest(client, access_id)
    assert after > before


def test_outer_scalar_poll_is_idle_without_event_fetch(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()
    C = _latest(client, access_id)

    new_C, events, scalar_polls, event_page_polls = _catch_up(
        client,
        access_id,
        identity_id="idle-poller",
        cursor=C,
    )

    assert scalar_polls == 1
    assert event_page_polls == 0
    assert new_C == C
    assert events == []


def test_double_loop_catches_up_in_bounded_pages(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()

    new_C, events, scalar_polls, event_page_polls = _catch_up(
        client,
        access_id,
        identity_id="bounded-poller",
        cursor=0,
        limit=1,
    )

    assert scalar_polls == 1
    assert event_page_polls >= 1
    assert events
    assert new_C == _latest(client, access_id)

    event_seqs = [
        int(event["event_seq"])
        for event in events
    ]
    assert event_seqs == sorted(event_seqs)
    assert len(event_seqs) == len(set(event_seqs))


def test_role_projected_poller_advances_hidden_positions(app) -> None:
    handles = _handles(app)
    maker = handles["maker"]
    auditor = handles["auditor"]
    client = app.test_client()

    A = _latest(client, maker)
    assert A > 0

    page_response = _event_page(
        client,
        auditor,
        identity_id="auditor-poller",
        cursor=0,
        limit=500,
    )
    assert page_response.status_code == 200

    page = page_response.get_json()
    receipt = page["visibility_receipt"]

    assert page["session_latest_event_seq"] == A
    assert page["next_after_event_seq"] == A
    assert receipt["reason"] == "role_projection"
    assert receipt["hidden_event_count"] > 0
    assert receipt["hidden_event_seq_ranges"]

    visible_datum_events = [
        event
        for event in page["events"]
        if event["kind"] == "datum_lifecycle_event_v1"
    ]

    assert visible_datum_events
    assert all(
        event["datum_id"] == "support"
        for event in visible_datum_events
    )

    visible_seqs = {
        int(event["event_seq"])
        for event in page["events"]
    }
    hidden_seqs = {
        seq
        for row in receipt["hidden_event_seq_ranges"]
        for seq in range(
            int(row["from_event_seq"]),
            int(row["to_event_seq"]) + 1,
        )
    }

    assert visible_seqs.isdisjoint(hidden_seqs)
    assert max(visible_seqs | hidden_seqs) == A


def test_two_role_pollers_keep_independent_cursors(app) -> None:
    handles = _handles(app)
    client = app.test_client()

    maker_C, maker_events, _, _ = _catch_up(
        client,
        handles["maker"],
        identity_id="maker-independent-poller",
        cursor=0,
        limit=2,
    )
    auditor_C, auditor_events, _, _ = _catch_up(
        client,
        handles["auditor"],
        identity_id="auditor-independent-poller",
        cursor=0,
        limit=1,
    )

    A = _latest(client, handles["maker"])
    assert maker_C == auditor_C == A
    assert len(auditor_events) <= len(maker_events)

    assert [
        int(event["event_seq"])
        for event in maker_events
    ] == sorted(
        int(event["event_seq"])
        for event in maker_events
    )
    assert [
        int(event["event_seq"])
        for event in auditor_events
    ] == sorted(
        int(event["event_seq"])
        for event in auditor_events
    )


# =============================================================================
# G. Same-session HTTP concurrency
# =============================================================================

def test_same_session_concurrent_conflicting_writes_serialize(app) -> None:
    access_id = _handles(app)["maker"]

    with app.test_client() as client:
        C = _latest(client, access_id)

    barrier = Barrier(2)

    def submit(label: str):
        with app.test_client() as client:
            barrier.wait()
            return _dispatch(
                client,
                access_id,
                cursor=C,
                request_id=_request_id(label),
                identity_id=label,
                user_fill={
                    "complex": valid_complex_describe_fill()["complex"],
                },
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        left_future = pool.submit(submit, "writer-left")
        right_future = pool.submit(submit, "writer-right")
        responses = [
            left_future.result(),
            right_future.result(),
        ]

    statuses = sorted(
        response.status_code
        for response in responses
    )
    assert statuses == [200, 409]

    packets = [
        response.get_json()
        for response in responses
    ]
    assert len({
        packet["request_id"]
        for packet in packets
    }) == 2

    committed = [
        packet
        for packet in packets
        if packet["write_committed"] is True
    ]
    rejected = [
        packet
        for packet in packets
        if packet["rejected"] is True
    ]

    assert len(committed) == 1
    assert committed[0]["dispatch_outcome"] == "applied"

    assert len(rejected) == 1
    assert rejected[0]["dispatch_outcome"] == "stale_rejected"
    assert rejected[0]["rejection_kind"] == "stale_conflict"
    assert rejected[0]["write_committed"] is False


def test_stale_rejection_is_eventless(app) -> None:
    access_id = _handles(app)["maker"]
    client = app.test_client()
    C = _latest(client, access_id)

    first = _dispatch(
        client,
        access_id,
        cursor=C,
        user_fill={
            "complex": valid_complex_describe_fill()["complex"],
        },
    )
    assert first.status_code == 200
    assert first.get_json()["write_committed"] is True

    A = _latest(client, access_id)

    queue_before_response = _event_page(
        client,
        access_id,
        identity_id="eventless-before",
        cursor=0,
        limit=500,
    )
    assert queue_before_response.status_code == 200
    queue_before = queue_before_response.get_json()

    stale = _dispatch(
        client,
        access_id,
        cursor=C,
        identity_id="stale-eventless-client",
        user_fill={
            "complex": {
                "decision": "accept",
                "publish": True,
            },
        },
    )

    assert stale.status_code == 409
    assert stale.get_json()["rejection_kind"] == "stale_conflict"
    assert _latest(client, access_id) == A

    queue_after_response = _event_page(
        client,
        access_id,
        identity_id="eventless-before",
        cursor=0,
        limit=500,
    )
    assert queue_after_response.status_code == 200
    assert queue_after_response.get_json() == queue_before


def test_stale_client_can_poll_rebuild_and_retry(app) -> None:
    """
    Complete outside-client recovery story.

    Client B must not blindly replay its old payload. It catches up, observes
    the new confirmation shell, builds the confirmation fill appropriate to
    that refreshed surface, and dispatches a new correlated request.
    """
    access_id = _handles(app)["maker"]
    client = app.test_client()
    shared_C = _latest(client, access_id)

    first_request_id = _request_id("client-a")
    first = _dispatch(
        client,
        access_id,
        cursor=shared_C,
        request_id=first_request_id,
        identity_id="client-a",
        user_fill={
            "complex": valid_complex_describe_fill()["complex"],
        },
    )
    assert first.status_code == 200
    assert first.get_json()["request_id"] == first_request_id
    assert first.get_json()["write_committed"] is True

    stale_request_id = _request_id("client-b-stale")
    stale = _dispatch(
        client,
        access_id,
        cursor=shared_C,
        request_id=stale_request_id,
        identity_id="client-b",
        user_fill={
            "complex": {
                "decision": "accept",
                "publish": True,
            },
        },
    )
    assert stale.status_code == 409
    assert stale.get_json()["request_id"] == stale_request_id
    assert stale.get_json()["dispatch_outcome"] == "stale_rejected"

    refreshed_C, events, _, event_page_polls = _catch_up(
        client,
        access_id,
        identity_id="client-b",
        cursor=shared_C,
        limit=1,
    )
    assert events
    assert event_page_polls >= 1

    refreshed_state = client.get(_path(access_id))
    assert refreshed_state.status_code == 200
    refreshed_ctx = refreshed_state.get_json()["ctx"]

    complex_decl = refreshed_ctx["datum_widget_decls"]["complex"]
    datum_args = dict(complex_decl.get("datum_args") or {})
    micros = (
        datum_args.get("micro_input_fields")
        or datum_args.get("micros")
        or []
    )
    refreshed_names = {
        str(row.get("name") or "")
        for row in micros
        if isinstance(row, Mapping)
    }
    assert {"decision", "publish"}.issubset(refreshed_names)

    retry_request_id = _request_id("client-b-retry")
    retry = _dispatch(
        client,
        access_id,
        cursor=refreshed_C,
        request_id=retry_request_id,
        identity_id="client-b",
        user_fill={
            "complex": {
                "decision": "accept",
                "publish": True,
            },
        },
    )
    assert retry.status_code == 200
    assert retry.get_json()["request_id"] == retry_request_id
    assert retry.get_json()["write_committed"] is True
    assert retry_request_id != stale_request_id


# =============================================================================
# H. Independent sessions
# =============================================================================

def test_many_sessions_have_independent_write_lanes() -> None:
    reset_access_handles()

    left = create_app_for_program(
        launch_spec=_launch_spec(),
    )
    right = create_app_for_program(
        launch_spec=_launch_spec(),
    )
    left.config.update(TESTING=True)
    right.config.update(TESTING=True)

    try:
        left_access = _handles(left)["maker"]
        right_access = _handles(right)["maker"]

        with left.test_client() as client:
            left_C = _latest(client, left_access)
        with right.test_client() as client:
            right_C = _latest(client, right_access)

        barrier = Barrier(2)

        def submit(
            app_value,
            access_id: str,
            cursor: int,
            label: str,
        ):
            with app_value.test_client() as client:
                barrier.wait()
                return _dispatch(
                    client,
                    access_id,
                    cursor=cursor,
                    request_id=_request_id(label),
                    identity_id=label,
                    user_fill={
                        "complex": (
                            valid_complex_describe_fill()["complex"]
                        ),
                    },
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            left_future = pool.submit(
                submit,
                left,
                left_access,
                left_C,
                "left-session",
            )
            right_future = pool.submit(
                submit,
                right,
                right_access,
                right_C,
                "right-session",
            )
            responses = [
                left_future.result(),
                right_future.result(),
            ]

        assert [
            response.status_code
            for response in responses
        ] == [200, 200]
        assert all(
            response.get_json()["write_committed"] is True
            for response in responses
        )

        with left.test_client() as client:
            left_A = _latest(client, left_access)
        with right.test_client() as client:
            right_A = _latest(client, right_access)

        assert left_A > left_C
        assert right_A > right_C
    finally:
        close_app_sessions(left)
        close_app_sessions(right)
        reset_access_handles()


def test_one_sessions_stale_rejection_does_not_move_another_session() -> None:
    reset_access_handles()

    left = create_app_for_program(
        launch_spec=_launch_spec(),
    )
    right = create_app_for_program(
        launch_spec=_launch_spec(),
    )
    left.config.update(TESTING=True)
    right.config.update(TESTING=True)

    try:
        left_access = _handles(left)["maker"]
        right_access = _handles(right)["maker"]

        with left.test_client() as client:
            left_C = _latest(client, left_access)
            first = _dispatch(
                client,
                left_access,
                cursor=left_C,
                identity_id="left-writer",
                user_fill={
                    "complex": valid_complex_describe_fill()["complex"],
                },
            )
            assert first.status_code == 200
            left_A = _latest(client, left_access)

        with right.test_client() as client:
            right_A_before = _latest(client, right_access)

        with left.test_client() as client:
            stale = _dispatch(
                client,
                left_access,
                cursor=left_C,
                identity_id="left-stale-writer",
                user_fill={
                    "complex": {
                        "decision": "accept",
                        "publish": True,
                    },
                },
            )
            assert stale.status_code == 409
            assert _latest(client, left_access) == left_A

        with right.test_client() as client:
            assert _latest(client, right_access) == right_A_before
    finally:
        close_app_sessions(left)
        close_app_sessions(right)
        reset_access_handles()


# =============================================================================
# I. Process ownership guard
# =============================================================================

def test_request_is_rejected_when_app_owner_pid_does_not_match(app) -> None:
    access_id = _handles(app)["maker"]
    original_pid = app.extensions[
        LOCAL_FLASK_OWNER_PID_EXTENSION_KEY
    ]

    app.extensions[
        LOCAL_FLASK_OWNER_PID_EXTENSION_KEY
    ] = original_pid + 1

    try:
        response = app.test_client().get(_path(access_id))
    finally:
        app.extensions[
            LOCAL_FLASK_OWNER_PID_EXTENSION_KEY
        ] = original_pid

    assert response.status_code == 503
    packet = response.get_json()

    assert packet["runtime_profile"] == LOCAL_FLASK_RUNTIME_PROFILE
    assert "single-process" in packet["error"]
    assert "forked or secondary worker" in packet["error"]


# =============================================================================
# J. Final browser module bundle across aggregated package static roots
# =============================================================================

@pytest.mark.parametrize(
    "module_path",
    [
        WEB_SHIM_FILENAME,
    ],
)
def test_browser_shell_serves_main_static_modules_confrirming_wiring_e2e(
    app,
    module_path: str,
) -> None:
    response = app.test_client().get(
        f"/think/static/{module_path}"
    )

    assert response.status_code == 200
    assert response.mimetype in {
        "application/javascript",
        "text/javascript",
    }
    assert response.get_data()



def test_front_shim_imports_the_final_browser_application(app) -> None:
    response = app.test_client().get(
        f"/think/static/{WEB_SHIM_FILENAME}"
    )

    assert response.status_code == 200

    source = response.get_data(as_text=True)
    assert "platform/app.js" in source
    assert "thinkumentLoopback" in source
    assert "plugins.drink" not in source


def test_app_module_wires_theta_epsilon_into_one_drinker_and_loopback(app) -> None:
    response = app.test_client().get(
        "/think/static/platform/app.js"
    )

    assert response.status_code == 200

    source = response.get_data(as_text=True)
    assert "INFORMATION_TRIGGER_THETA" in source
    assert "INFORMATION_TRIGGER_EPSILON" in source
    assert "disseminateInformation" in source
    assert "createThinkumentLoopbackApi" in source
    assert "request_id" in source
    assert "gamma" not in source


def test_backend_event_modules_are_present(app) -> None:
    client = app.test_client()

    digest = client.get(
        "/think/static/platform/_backend_events/digest.js"
    )
    pollpull = client.get(
        "/think/static/platform/_backend_events/pollpull.js"
    )
    dissemination = client.get(
        "/think/static/inbound.js"
    )

    assert digest.status_code == 200
    assert pollpull.status_code == 200
    assert dissemination.status_code == 200

    assert digest.get_data()
    assert pollpull.get_data()
    source = dissemination.get_data(as_text=True)
    assert "thinkument_information_inbound_v1" in source
    assert "INFORMATION_TRIGGER_THETA" in source
    assert "INFORMATION_TRIGGER_EPSILON" in source
