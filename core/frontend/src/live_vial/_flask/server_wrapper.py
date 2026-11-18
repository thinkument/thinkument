from __future__ import annotations

"""Thin local Flask application wrapper around one highest-facade launch spec."""

import os
from typing import Any, Dict, Mapping

from flask import Flask, jsonify, redirect, url_for

from __staticfiles_mgmt.globals import (
    BLUEPRINT_NAME,
    LOCAL_FLASK_OWNER_PID_EXTENSION_KEY,
    LOCAL_FLASK_RUNTIME_PROFILE,
    LOCAL_FLASK_RUNTIME_PROFILE_EXTENSION_KEY,
    LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY,
)
from live_vial._flask.adapter import (
    build_access_handle_urls,
    create_access_bundle,
    release_local_session,
    thinkument_blueprint,
)


DEFAULT_THINKUMENT_URL_PREFIX = "/think"
LAUNCH_BUNDLE_EXTENSION_KEY = (
    "thinkument_launch_bundle"
)


def create_app_for_program(
    *,
    launch_spec: Mapping[str, Any],
) -> Flask:
    app = Flask(
        __name__,
        static_folder=None,
    )

    # Build the blueprint before creating a session. Static namespace and
    # opinionation selection are launch-composition checks; if either is
    # invalid, fail without allocating a backend session that would need
    # compensating cleanup.
    blueprint = thinkument_blueprint(
        launch_spec=dict(launch_spec),
        url_prefix=DEFAULT_THINKUMENT_URL_PREFIX,
    )

    bundle = create_access_bundle(
        launch_spec=launch_spec
    )
    app.extensions[
        LAUNCH_BUNDLE_EXTENSION_KEY
    ] = bundle
    app.extensions[
        LOCAL_FLASK_RUNTIME_PROFILE_EXTENSION_KEY
    ] = LOCAL_FLASK_RUNTIME_PROFILE
    app.extensions[
        LOCAL_FLASK_OWNER_PID_EXTENSION_KEY
    ] = os.getpid()
    app.extensions[
        LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY
    ] = {str(bundle["session_id"])}

    app.register_blueprint(blueprint)

    @app.before_request
    def _require_owner_process():
        owner_pid = int(
            app.extensions[
                LOCAL_FLASK_OWNER_PID_EXTENSION_KEY
            ]
        )
        current_pid = os.getpid()
        if current_pid == owner_pid:
            return None

        return jsonify(
            {
                "error": (
                    "the local Thinkument Flask runtime is single-process; "
                    "this request reached a forked or secondary worker"
                ),
                "runtime_profile": LOCAL_FLASK_RUNTIME_PROFILE,
            }
        ), 503

    @app.route(
        "/",
        methods=["GET"],
    )
    def index():
        return redirect(
            url_for(
                f"{BLUEPRINT_NAME}.run_page",
                access_id=str(
                    bundle["selected_access_id"]
                ),
            )
        )

    return app


def close_app_sessions(
    app: Flask,
) -> list[Dict[str, Any]]:
    """Idempotently release every local session created by this app."""
    session_ids = app.extensions.setdefault(
        LOCAL_FLASK_SESSION_IDS_EXTENSION_KEY,
        set(),
    )
    reports: list[Dict[str, Any]] = []

    for session_id in list(session_ids):
        try:
            reports.append(
                release_local_session(
                    session_id=str(session_id)
                )
            )
        finally:
            session_ids.discard(session_id)

    return reports


def get_app_launch_bundle(
    app: Flask,
) -> Dict[str, Any]:
    try:
        return dict(
            app.extensions[
                LAUNCH_BUNDLE_EXTENSION_KEY
            ]
        )
    except KeyError as exc:
        raise RuntimeError(
            "Flask app has no Thinkument "
            "launch bundle"
        ) from exc


def _absolute(
    base: str,
    path: str,
) -> str:
    return (
        f"{base.rstrip('/')}/"
        f"{str(path).lstrip('/')}"
    )


def print_access_handles_for_program(
    *,
    app: Flask,
    host: str,
    port: int,
) -> None:
    bundle = get_app_launch_bundle(app)

    with app.test_request_context("/"):
        relative = build_access_handle_urls(
            access_ids=bundle["access_ids"]
        )

    base = f"http://{host}:{port}"
    print("🔗 role-sealed access handles")

    for key, access_id in bundle[
        "access_ids"
    ].items():
        selected = (
            access_id
            == bundle["selected_access_id"]
        )
        role = relative[key]["role"]

        print(
            f"  {'*' if selected else '-'} "
            f"{key} "
            f"role={role!r} "
            f"access_id={access_id}"
        )

        for name in (
            "context",
            "latestEventSeq",
            "events",
            "dispatchProgress",
            "dispatch",
            "dispatchFunked",
            "page",
        ):
            print(
                f"      {name:15} "
                f"{_absolute(base, relative[key][name])}"
            )


__all__ = [
    "close_app_sessions",
    "create_app_for_program",
    "get_app_launch_bundle",
    "print_access_handles_for_program",
]
