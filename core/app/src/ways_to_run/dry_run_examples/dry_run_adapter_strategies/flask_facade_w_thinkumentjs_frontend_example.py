from __future__ import annotations

"""Flask server + real opinionless ThinkumentJS frontend dry-run strategy.

The server sheet owns Flask bootstrap/teardown and Flask-specific response
normalization only. All frontend behavior lives once in
``_thinkumentjs_client_example_opinionless``.

Execution path for an ordinary shared A is:

    standard A
      -> role-selected stable ThinkumentJS client
      -> captured higher-app loopback
      -> outbound station guard
      -> app dispatch lane
      -> real createPortal HTTP
      -> real threaded Flask facade
      -> backend session
      -> provisional roleful epsilon back through ThinkumentJS
      -> canonical theta back through ThinkumentJS
      -> opinionless womb observations / local Q

The only test-only deviations are the reusable shared membrane's explicit
cursor injection and narrowly enumerated malformed-signal server-boundary
fixture. No DOM code or Flask-specific branch appears in the shared catalogs.
"""

import threading
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
    overlay_initial_parameter_overrides_onto_program_v1,
)
from live_vial._flask._helpers_for_local_server import (
    build_local_flask_launch_spec,
)
from live_vial._flask.adapter import build_access_handle_urls
from live_vial._flask.server_wrapper import (
    close_app_sessions,
    create_app_for_program,
    get_app_launch_bundle,
)
from werkzeug.serving import WSGIRequestHandler, make_server

from ._thinkumentjs_client_example_opinionless import (
    DEFAULT_NODE_BINARY,
    DEFAULT_PROGRESS_POLL_SECONDS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ThinkumentJSDispatchObservationV1,
    ThinkumentJSFrontendBackendRunV1,
    ThinkumentJSFrontendEndpointSetV1,
    ThinkumentJSOpinionlessFrontendDryRunStrategy,
    invalid_event_cursor_packet_v1,
    normalize_harmonized_server_receipt_v1,
    raise_remote_exception_packet_v1,
    raise_thinkumentjs_station_guard_exception_v1,
    targets_from_standard_A_v1,
)


TYPED_EXCEPTION_KIND_V1 = "thinkument_local_flask_typed_exception_v1"
DEFAULT_SERVER_SHUTDOWN_POLL_SECONDS = 0.01


class _QuietWSGIRequestHandler(WSGIRequestHandler):
    def log(self, type: str, message: str, *args: Any) -> None:
        del type, message, args


@dataclass(slots=True)
class _FlaskThinkumentJSHostV1:
    app: Any
    server: Any
    thread: threading.Thread


class FlaskFacadeWithThinkumentJSFrontendOpinionlessDryRunStrategy(
    ThinkumentJSOpinionlessFrontendDryRunStrategy
):
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        node_binary: str = DEFAULT_NODE_BINARY,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        progress_poll_seconds: float = DEFAULT_PROGRESS_POLL_SECONDS,
        server_shutdown_poll_seconds: float = (
            DEFAULT_SERVER_SHUTDOWN_POLL_SECONDS
        ),
    ) -> None:
        super().__init__(
            node_binary=node_binary,
            request_timeout_seconds=request_timeout_seconds,
            progress_poll_seconds=progress_poll_seconds,
        )
        normalized_host = str(host or "").strip()
        if not normalized_host:
            raise ValueError("host must be non-empty")
        self._host = normalized_host
        self._server_shutdown_poll_seconds = max(
            0.001,
            float(server_shutdown_poll_seconds),
        )

    @property
    def strategy_name(self) -> str:
        return "flask-facade-w-thinkumentjs-frontend-opinionless-strategy"

    @staticmethod
    def _effective_program_v1(
        program: Mapping[str, Any],
        C: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not C:
            return deepcopy(dict(program))
        return deepcopy(
            overlay_initial_parameter_overrides_onto_program_v1(
                deepcopy(dict(program)),
                initial_parameter_overrides=deepcopy(dict(C)),
            )
        )

    @staticmethod
    def _split_SM_v1(
        SM: Mapping[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        metadata = deepcopy(dict(SM or {}))
        roles = metadata.pop("roles", {}) or {}
        policy = metadata.pop("role_mismatch_policy", {}) or {}

        if not isinstance(roles, Mapping):
            raise TypeError("session_metadata.roles must be a mapping")
        if not isinstance(policy, Mapping):
            raise TypeError(
                "session_metadata.role_mismatch_policy must be a mapping"
            )

        return (
            metadata,
            {
                str(name): deepcopy(value)
                for name, value in dict(roles).items()
            },
            deepcopy(dict(policy)),
        )

    @staticmethod
    def _relative_endpoints_v1(
        app: Any,
        access_id: str,
    ) -> ThinkumentJSFrontendEndpointSetV1:
        with app.test_request_context("/"):
            row = build_access_handle_urls(
                access_ids={"selected": str(access_id)}
            )["selected"]
        return ThinkumentJSFrontendEndpointSetV1.from_mapping_v1(
            {
                key: value
                for key, value in row.items()
                if key != "role"
            }
        )

    def _serve_forever_v1(self, server: Any) -> None:
        server.serve_forever(
            poll_interval=self._server_shutdown_poll_seconds,
        )

    def _start_backend_v1(
        self,
        *,
        program: Mapping[str, Any],
        session_metadata: Mapping[str, Any],
        initial_parameter_overrides: Mapping[str, Any],
    ) -> ThinkumentJSFrontendBackendRunV1:
        metadata, roles, policy = self._split_SM_v1(session_metadata)
        wrapper = {
            "program_language": LANG_THINK_PROGRAM_V1,
            "program": self._effective_program_v1(
                program,
                initial_parameter_overrides,
            ),
            "session_surface": {
                "session_metadata": metadata,
                "roles": roles,
                "role_mismatch_policy": policy,
                "public_view_role": next(iter(roles), None),
                "start_on_create": False,
                "include_unmodulated_access": True,
                "expose_typed_exceptions": True,
            },
        }

        app = create_app_for_program(
            launch_spec=build_local_flask_launch_spec(wrapper=wrapper)
        )
        bundle = get_app_launch_bundle(app)

        unmodulated_access_id = str(
            bundle.get("unmodulated_access_id") or ""
        ).strip()
        if not unmodulated_access_id:
            close_app_sessions(app)
            raise AssertionError(
                "Flask ThinkumentJS launch omitted unmodulated access"
            )

        endpoints_by_role: Dict[
            Optional[str], ThinkumentJSFrontendEndpointSetV1
        ] = {
            None: self._relative_endpoints_v1(
                app,
                unmodulated_access_id,
            )
        }
        for role in roles:
            access_id = str(
                dict(bundle.get("access_ids") or {}).get(str(role)) or ""
            ).strip()
            if not access_id:
                close_app_sessions(app)
                raise AssertionError(
                    f"Flask launch omitted access handle for role {role!r}"
                )
            endpoints_by_role[str(role)] = self._relative_endpoints_v1(
                app,
                access_id,
            )

        server = make_server(
            self._host,
            0,
            app,
            threaded=True,
            request_handler=_QuietWSGIRequestHandler,
        )
        thread = threading.Thread(
            target=self._serve_forever_v1,
            args=(server,),
            name=(
                "thinkument-dry-run-flask-thinkumentjs-"
                f"{bundle['session_id']}"
            ),
            daemon=True,
        )
        thread.start()

        return ThinkumentJSFrontendBackendRunV1(
            base_url=f"http://{self._host}:{int(server.server_port)}",
            session_id=str(bundle["session_id"]),
            endpoints_by_role=endpoints_by_role,
            proof_obweb_RESTful=endpoints_by_role[None],
            host_resource=_FlaskThinkumentJSHostV1(
                app=app,
                server=server,
                thread=thread,
            ),
        )

    def _close_backend_v1(
        self,
        *,
        backend: ThinkumentJSFrontendBackendRunV1,
    ) -> None:
        host = backend.host_resource
        if not isinstance(host, _FlaskThinkumentJSHostV1):
            raise TypeError("wrong Flask ThinkumentJS host resource")

        try:
            host.server.shutdown()
        finally:
            try:
                host.server.server_close()
            finally:
                host.thread.join(timeout=5)
                close_app_sessions(host.app)

    def _normalize_dispatch_observation_v1(
        self,
        *,
        backend: ThinkumentJSFrontendBackendRunV1,
        A: Mapping[str, Any],
        observation: ThinkumentJSDispatchObservationV1,
    ) -> Mapping[str, Any]:
        node = observation.node
        error = node.get("dispatch_error")
        result = node.get("dispatch_result")

        if isinstance(error, Mapping):
            if error.get("name") == "ThinkumentOutboundDispatchValidationError":
                raise_thinkumentjs_station_guard_exception_v1(
                    A=A,
                    error=error,
                )

            status = error.get("status")
            body = error.get("body")
            body = dict(body) if isinstance(body, Mapping) else {}

            if status == 403:
                targets = targets_from_standard_A_v1(A)
                raise PermissionError(
                    "permission denied for "
                    + (", ".join(targets) or "submitted action")
                )

            raw_cursor = A.get("my_current_event_seq_number")
            if (
                status == 400
                and raw_cursor is not None
                and type(raw_cursor) is not int
            ):
                return invalid_event_cursor_packet_v1(
                    session_id=backend.session_id,
                    observed_event_seq=int(node.get("after_cursor") or 0),
                    A=A,
                )

            if (
                isinstance(status, int)
                and status >= 500
                and body.get("kind") == TYPED_EXCEPTION_KIND_V1
            ):
                raise_remote_exception_packet_v1(
                    body,
                    default_name="RemoteFlaskDryRunError",
                )

            raise AssertionError(
                "Flask + ThinkumentJS dispatch failed: "
                f"error={dict(error)!r}, A={dict(A)!r}"
            )

        if not isinstance(result, Mapping):
            raise AssertionError(
                "Flask + ThinkumentJS dispatch produced neither result nor "
                f"error: observation={dict(node)!r}"
            )

        return normalize_harmonized_server_receipt_v1(result)


__all__ = [
    "DEFAULT_SERVER_SHUTDOWN_POLL_SECONDS",
    "FlaskFacadeWithThinkumentJSFrontendOpinionlessDryRunStrategy",
]
