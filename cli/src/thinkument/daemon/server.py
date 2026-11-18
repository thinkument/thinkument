"""Flask REST & SSE loopback daemon for Thinkument Local Studio (localhost:5052)."""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Optional

from flask import Flask, Response, jsonify, request

from thinkument.daemon.interceptor import (
    VendorInvocation,
    create_ollama_interceptor,
    create_webhook_interceptor,
    default_mock_interceptor,
    load_interceptor_from_file,
)
from thinkument.daemon.runner import LocalSessionRunner


def create_daemon_app(
    runner: Optional[LocalSessionRunner] = None,
    mode: str = "mock",
    mocks_file: Optional[str] = None,
    vendor_ollama: Optional[str] = None,
    vendor_proxy: Optional[str] = None,
) -> Flask:
    """Create and configure the local Flask daemon application."""
    app = Flask(__name__)

    # Configure interceptor
    interceptor: Callable[[VendorInvocation], Dict[str, Any]] = default_mock_interceptor
    if mocks_file:
        interceptor = load_interceptor_from_file(mocks_file)
    elif vendor_ollama:
        interceptor = create_ollama_interceptor(endpoint=vendor_ollama)
    elif vendor_proxy:
        interceptor = create_webhook_interceptor(target_url=vendor_proxy)

    session_runner = runner or LocalSessionRunner(default_interceptor=interceptor)
    app.config["RUNNER"] = session_runner

    @app.route("/healthz/", methods=["GET"])
    def healthz():
        return jsonify({
            "status": "ok",
            "service": "thinkument-local-daemon",
            "version": "0.1.0",
            "mode": mode,
        })

    @app.route("/api/v1/sessions/", methods=["POST"])
    def create_session():
        data = request.get_json(force=True) or {}
        P = data.get("P")
        if not P and "program" in data:
            P = data.get("program")
        if not P:
            return jsonify({"error": "P (or program) must be provided"}), 400

        SM = data.get("SM") or data.get("session_metadata")
        C = data.get("C") or data.get("initial_parameter_overrides")
        roles = data.get("roles")
        metadata = data.get("metadata")
        public_view_role = data.get("public_view_role")

        try:
            result = session_runner.create_session(
                P=P,
                SM=SM,
                C=C,
                roles=roles,
                metadata=metadata,
                public_view_role=public_view_role,
                base_url=request.host_url.rstrip("/"),
            )
            return jsonify(result), 201
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/v1/sessions/<session_id>/", methods=["GET"])
    def get_session_state(session_id: str):
        role = request.args.get("role")
        try:
            state = session_runner.get_state(session_id, role=role)
            return jsonify(state), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 404

    @app.route("/api/v1/sessions/<session_id>/dispatch/", methods=["POST"])
    def dispatch_action(session_id: str):
        data = request.get_json(force=True) or {}
        action = data.get("action", "STEP")
        user_fill = data.get("user_fill")
        user_signal = data.get("user_signal")
        role = data.get("role")
        cursor = data.get("my_current_event_seq_number") or data.get("cursor")
        identity_id = data.get("identity_id")

        try:
            receipt = session_runner.dispatch(
                session_id,
                action=action,
                user_fill=user_fill,
                user_signal=user_signal,
                role=role,
                cursor=cursor,
                identity_id=identity_id,
            )
            return jsonify(receipt), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/v1/sessions/<session_id>/events/", methods=["GET"])
    def get_events(session_id: str):
        after_seq = request.args.get("after_seq", type=int)
        role = request.args.get("role")

        accept = request.headers.get("Accept", "")
        if "text/event-stream" in accept:
            def event_stream():
                current_seq = after_seq or 0
                while True:
                    packet = session_runner.get_events(session_id, after_seq=current_seq, role=role)
                    events = packet.get("events") or []
                    for ev in events:
                        yield f"data: {json.dumps(ev)}\n\n"
                        current_seq = max(current_seq, ev.get("event_seq", current_seq))
                    time.sleep(0.1)

            return Response(event_stream(), mimetype="text/event-stream")

        events_data = session_runner.get_events(session_id, after_seq=after_seq, role=role)
        return jsonify(events_data), 200

    @app.route("/api/v1/sessions/<session_id>/", methods=["DELETE"])
    def delete_session(session_id: str):
        try:
            session_runner.close_session(session_id)
            return jsonify({"status": "deleted", "session_id": session_id}), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/v1/blackbox/run/", methods=["POST"])
    def run_blackbox():
        data = request.get_json(force=True) or {}
        P = data.get("P") or data.get("program")
        if not P:
            return jsonify({"error": "P must be provided"}), 400
        C = data.get("C") or data.get("context")
        SM = data.get("SM") or data.get("session_metadata")
        roles = data.get("roles")
        timeout_seconds = data.get("timeout_seconds", 60)

        try:
            result = session_runner.run_blackbox(
                P=P,
                C=C,
                SM=SM,
                roles=roles,
                timeout_seconds=timeout_seconds,
            )
            return jsonify(result), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/v1/ops/execute/", methods=["POST"])
    def execute_ops_relay():
        data = request.get_json(force=True) or {}
        operation = data.get("operation") or data.get("fn")
        channel = data.get("channel") or ("vibe_coder" if "goal" in data else "vendor_op")
        if not operation and not data.get("chain") and "goal" not in data:
            return jsonify({"error": "operation, chain, or goal required"}), 400

        try:
            job = session_runner.submit_job(data)
            poll_url = f"/api/v1/ops/jobs/{job['job_id']}/"
            
            # Check if caller explicitly requested asynchronous background execution
            is_async = data.get("async") is True or request.args.get("async") in ("true", "1")
            if is_async:
                return jsonify({
                    "status": "queued",
                    "job_id": job["job_id"],
                    "call_key": job.get("call_key"),
                    "channel": channel,
                    "poll_url": poll_url,
                }), 202

            resp_dict = {
                "status": "success",
                "job_id": job["job_id"],
                "call_key": job.get("call_key"),
                "channel": channel,
                "poll_url": poll_url,
                "result": job.get("result", {}),
                "program": job.get("program"),
                "outputs": job.get("outputs", {}),
            }
            if isinstance(job.get("result"), dict):
                for k, v in job["result"].items():
                    if k not in resp_dict:
                        resp_dict[k] = v
                    elif k == "status" and v:
                        resp_dict["status"] = v

            return jsonify(resp_dict), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/v1/ops/jobs/<job_id>/", methods=["GET"])
    def get_ops_job_status(job_id: str):
        job = session_runner.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found", "job_id": job_id}), 404
        return jsonify({
            "job_id": job["job_id"],
            "status": job.get("status", "success"),
            "progress": job.get("progress", {"percent": 100, "message": "Completed"}),
            "result": job.get("result"),
            "program": job.get("program"),
            "outputs": job.get("outputs", {}),
            "error": job.get("error"),
        }), 200

    return app
