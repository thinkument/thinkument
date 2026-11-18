from __future__ import annotations

"""Flask live server + real Chromium + ThinkumentJS + sufficience DOM.

This is the Flask sibling of the proven Django browser strategy.  The shared
browser membrane owns Chromium, one isolated role page per client, A -> DOM
translation, rendered theta/Q/U reconstruction, roleful DOM epsilon proof, and
trusted unmodulated epsilon observation.

This concrete strategy owns only Flask lambda/omega plus normalization of the
harmonized browser dispatch observation back into the standard dry-run receipt
vocabulary.

Important hosting fact
----------------------
The local Flask adapter already mirrors every roleful provisional dispatch
lifecycle into the trusted role=None capability whenever
``include_unmodulated_access=True``.  Therefore Task G does not need a second
observer-routing subsystem or any Flask endpoint changes: the browser role
performs the real dispatch while the existing unmodulated progress capability
supplies the generic dry-run epsilon lens.
"""

import builtins
import threading
from copy import deepcopy
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
    overlay_initial_parameter_overrides_onto_program_v1,
)
from ways_to_run.dry_run_examples.dry_run_adapter_strategies._thinkumentjs_client_example_opinionless import (
    normalize_harmonized_server_receipt_v1,
    raise_remote_exception_text_v1,
    raise_thinkumentjs_station_guard_exception_v1,
    remote_exception_type_v1,
    targets_from_standard_A_v1,
)
from ways_to_run.dry_run_examples.dry_run_adapter_strategies._thinkumentjs_client_w_sufficience_opinionation import (
    DEFAULT_BROWSER_COMMAND_TIMEOUT_SECONDS,
    DEFAULT_NODE_BINARY,
    DEFAULT_PROGRESS_POLL_SECONDS,
    DEFAULT_PROGRESS_TERMINAL_TIMEOUT_SECONDS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    SufficienceBrowserBackendRunV1,
    SufficienceBrowserDispatchObservationV1,
    ThinkumentJSSufficienceBrowserDryRunStrategy,
)
from ways_to_run.dry_run_examples.dry_run_adapter_strategies.flask_facade_backend_only import (
    DEFAULT_SERVER_SHUTDOWN_POLL_SECONDS,
)
from live_vial._flask._helpers_for_local_server import (
    build_local_flask_launch_spec,
)
from live_vial._flask.adapter import (
    TYPED_EXCEPTION_KIND_V1,
    build_access_handle_urls,
)
from bootstrap_higher_app.runtime import (
    close_app_sessions,
    create_app_for_program,
    get_app_launch_bundle,
)
from werkzeug.serving import WSGIRequestHandler, make_server


SUFFICIENCE_OPINIONATION_LOGICAL_NAME = "test_opinionations/sufficience.js"

# This shared sheet deliberately forges malformed/stale transport facts.  A
# real human-facing ThinkumentJS browser correctly owns role/identity/cursor
# serialization and cannot expose those lower-wire controls.
P7_TRANSPORT_BOUNDARY_CASE = (
    "dry_run_lib_widgets_flows.P7.dispatch_failure_boundaries"
)


class _QuietWSGIRequestHandler(WSGIRequestHandler):
    def log(self, type: str, message: str, *args: Any) -> None:
        del type, message, args


@dataclass(slots=True)
class _FlaskSufficienceBrowserHostV1:
    app: Any
    server: Any
    thread: threading.Thread


class FlaskFacadeWithThinkumentJSSufficienceBrowserDryRunStrategy(
    ThinkumentJSSufficienceBrowserDryRunStrategy
):
    """Drive shared P/SM/C/A/E through Flask + real browser sufficience DOM."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        node_binary: str = DEFAULT_NODE_BINARY,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        progress_poll_seconds: float = DEFAULT_PROGRESS_POLL_SECONDS,
        progress_terminal_timeout_seconds: float = (
            DEFAULT_PROGRESS_TERMINAL_TIMEOUT_SECONDS
        ),
        browser_command_timeout_seconds: float = (
            DEFAULT_BROWSER_COMMAND_TIMEOUT_SECONDS
        ),
        server_shutdown_poll_seconds: float = (
            DEFAULT_SERVER_SHUTDOWN_POLL_SECONDS
        ),
    ) -> None:
        super().__init__(
            node_binary=node_binary,
            request_timeout_seconds=request_timeout_seconds,
            progress_poll_seconds=progress_poll_seconds,
            progress_terminal_timeout_seconds=progress_terminal_timeout_seconds,
            browser_command_timeout_seconds=browser_command_timeout_seconds,
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
        return "flask-facade-w-thinkumentjs-sufficience-browser-strategy"

    @property
    def server_shutdown_poll_seconds(self) -> float:
        """Werkzeug serve-loop cadence used by every case-local live server."""
        return self._server_shutdown_poll_seconds

    def case_skip_reason_v1(
        self,
        *,
        case_name: str,
        funked: bool,
    ) -> Optional[str]:
        if not funked and str(case_name) == P7_TRANSPORT_BOUNDARY_CASE:
            return (
                "P7 contains adversarial transport-boundary fixtures, including "
                "forged canonical cursors/malformed lower-wire shapes. The real "
                "sufficience browser intentionally exposes only public higher-app "
                "A; ThinkumentJS owns identity/role/cursor serialization. Those "
                "fixtures remain proven by lower backend/server/ThinkumentJS "
                "strategies rather than weakening the browser membrane."
            )
        return None

    # ---------------------------------------------------------------- lambda

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
    def _relative_endpoints_v1(app: Any, access_id: str) -> Dict[str, str]:
        with app.test_request_context("/"):
            row = build_access_handle_urls(
                access_ids={"selected": str(access_id)}
            )["selected"]
        return {
            str(key): str(value)
            for key, value in row.items()
            if key != "role"
        }

    @staticmethod
    def _absolute_v1(base_url: str, path: str) -> str:
        parsed = urlsplit(str(path))
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return str(path)
        return urljoin(
            f"{str(base_url).rstrip('/')}/",
            str(path).lstrip("/"),
        )

    def _serve_forever_v1(self, server: Any) -> None:
        server.serve_forever(
            poll_interval=self._server_shutdown_poll_seconds,
        )

    def _assert_server_ready_v1(self, url: str) -> None:
        request = Request(
            str(url),
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urlopen(
            request,
            timeout=self._request_timeout_seconds,
        ) as response:
            if int(response.status) != 200:
                raise AssertionError(
                    "Flask browser dry-run readiness check failed: "
                    f"status={response.status}, url={url!r}"
                )
            response.read()

    @staticmethod
    def _close_host_v1(host: _FlaskSufficienceBrowserHostV1) -> None:
        cleanup_error: Optional[BaseException] = None

        try:
            try:
                host.server.shutdown()
            except BaseException as exc:
                cleanup_error = exc

            try:
                host.server.server_close()
            except BaseException as exc:
                cleanup_error = cleanup_error or exc

            try:
                host.thread.join(timeout=5)
            except BaseException as exc:
                cleanup_error = cleanup_error or exc

            if host.thread.is_alive():
                cleanup_error = cleanup_error or RuntimeError(
                    "Flask browser dry-run server thread did not terminate"
                )
        finally:
            try:
                close_app_sessions(host.app)
            except BaseException as exc:
                cleanup_error = cleanup_error or exc

        if cleanup_error is not None:
            raise RuntimeError(
                "Flask sufficience browser omega encountered a cleanup error"
            ) from cleanup_error

    def _start_backend_v1(
        self,
        *,
        program: Mapping[str, Any],
        session_metadata: Mapping[str, Any],
        initial_parameter_overrides: Mapping[str, Any],
    ) -> SufficienceBrowserBackendRunV1:
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
                "opinionation_module": SUFFICIENCE_OPINIONATION_LOGICAL_NAME,
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
                "Flask browser launch omitted trusted unmodulated access"
            )

        proof_endpoints = self._relative_endpoints_v1(
            app,
            unmodulated_access_id,
        )
        endpoints_by_role: Dict[Optional[str], Dict[str, str]] = {
            None: proof_endpoints
        }

        for role in roles:
            role_access_id = str(
                dict(bundle.get("access_ids") or {}).get(str(role)) or ""
            ).strip()
            if not role_access_id:
                close_app_sessions(app)
                raise AssertionError(
                    f"Flask browser launch omitted role handle {role!r}"
                )
            endpoints_by_role[str(role)] = self._relative_endpoints_v1(
                app,
                role_access_id,
            )

        server = None
        thread = None
        try:
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
                    "thinkument-dry-run-flask-sufficience-"
                    f"{bundle['session_id']}"
                ),
                daemon=True,
            )
            thread.start()

            base_url = f"http://{self._host}:{int(server.server_port)}"
            page_urls_by_role = {
                role: self._absolute_v1(base_url, endpoints["page"])
                for role, endpoints in endpoints_by_role.items()
            }
            backend = SufficienceBrowserBackendRunV1(
                base_url=base_url,
                session_id=str(bundle["session_id"]),
                page_urls_by_role=page_urls_by_role,
                proof_dispatch_progress_url=self._absolute_v1(
                    base_url,
                    proof_endpoints.get("eps") or proof_endpoints["dispatchProgress"],
                ),
                host_resource=_FlaskSufficienceBrowserHostV1(
                    app=app,
                    server=server,
                    thread=thread,
                ),
            )

            # make_server() has already bound the socket.  This real loopback
            # request proves the request loop itself is accepting traffic before
            # Chromium begins booting multiple independent role pages.
            self._assert_server_ready_v1(
                self._absolute_v1(
                    base_url,
                    proof_endpoints["latestEventSeq"],
                )
            )
            return backend
        except Exception:
            if server is not None and thread is not None:
                self._close_host_v1(
                    _FlaskSufficienceBrowserHostV1(
                        app=app,
                        server=server,
                        thread=thread,
                    )
                )
            else:
                close_app_sessions(app)
            raise

    # ----------------------------------------------------------------- omega

    def _close_backend_v1(
        self,
        *,
        backend: SufficienceBrowserBackendRunV1,
    ) -> None:
        host = backend.host_resource
        if not isinstance(host, _FlaskSufficienceBrowserHostV1):
            raise TypeError("wrong Flask sufficience browser host resource")
        self._close_host_v1(host)

    # ----------------------------------------------------- browser normalization

    @staticmethod
    def _raise_typed_flask_body_v1(body: Mapping[str, Any]) -> None:
        if body.get("kind") != TYPED_EXCEPTION_KIND_V1:
            return

        name = str(body.get("exception_type") or "RemoteFlaskDryRunError")
        message = str(body.get("message") or "remote Flask exception")
        exc_type = remote_exception_type_v1(name)

        try:
            exc = exc_type(message)
        except Exception:
            candidate = getattr(builtins, name, None)
            if isinstance(candidate, type) and issubclass(candidate, Exception):
                exc = candidate(message)
            else:
                for module_name in ("__exceptions.engine", "__exceptions"):
                    try:
                        candidate = getattr(
                            import_module(module_name),
                            name,
                            None,
                        )
                    except Exception:
                        continue
                    if (
                        isinstance(candidate, type)
                        and issubclass(candidate, Exception)
                    ):
                        exc = candidate(message)
                        break
                else:
                    exc = RuntimeError(message)

        raise exc

    @classmethod
    def _raise_local_error_v1(
        cls,
        *,
        A: Mapping[str, Any],
        observation: SufficienceBrowserDispatchObservationV1,
        receipt: Mapping[str, Any],
    ) -> None:
        name = str(receipt.get("name") or "Error")
        message = str(receipt.get("message") or "browser dispatch failed")
        status = receipt.get("status")

        if name == "ThinkumentOutboundDispatchValidationError":
            raise_thinkumentjs_station_guard_exception_v1(
                A=A,
                error={
                    "code": receipt.get("code"),
                    "message": message,
                    "receipt": receipt.get("receipt"),
                },
            )

        if status == 403:
            targets = targets_from_standard_A_v1(A)
            raise PermissionError(
                "permission denied for "
                + (", ".join(targets) or "submitted action")
            )

        if isinstance(status, int) and status >= 500:
            if observation.proof_progress_error:
                raise_remote_exception_text_v1(
                    observation.proof_progress_error
                )

            body = receipt.get("body")
            if isinstance(body, Mapping):
                cls._raise_typed_flask_body_v1(body)

            raise AssertionError(
                "Flask browser dispatch failed without a typed terminal "
                f"progress/body error: local_receipt={dict(receipt)!r}, "
                f"A={dict(A)!r}"
            )

        exc_type = remote_exception_type_v1(name)
        try:
            exc = exc_type(message)
        except Exception:
            exc = RuntimeError(message)
        raise exc

    @staticmethod
    def _raise_station_guard_rejection_v1(
        *,
        A: Mapping[str, Any],
        receipt: Mapping[str, Any],
    ) -> None:
        errors = [
            dict(row)
            for row in list(receipt.get("errors") or [])
            if isinstance(row, Mapping)
        ]
        role_denial = next(
            (
                row
                for row in errors
                if row.get("code") == "write_role_denied"
            ),
            None,
        )
        if role_denial is not None:
            targets = targets_from_standard_A_v1(A)
            raise PermissionError(
                "permission denied for "
                + (", ".join(targets) or "submitted action")
            )

        first = errors[0] if errors else {}
        raise_thinkumentjs_station_guard_exception_v1(
            A=A,
            error={
                "code": first.get("code"),
                "message": first.get("message")
                or "ThinkumentJS browser preflight rejected A",
                "receipt": deepcopy(dict(receipt)),
            },
        )

    def _normalize_dispatch_observation_v1(
        self,
        *,
        backend: SufficienceBrowserBackendRunV1,
        A: Mapping[str, Any],
        observation: SufficienceBrowserDispatchObservationV1,
    ) -> Mapping[str, Any]:
        del backend
        browser = observation.browser

        page_errors = [
            row
            for row in list(browser.get("page_errors") or [])
            if isinstance(row, Mapping)
        ]
        if page_errors:
            raise AssertionError(
                "real Flask browser page raised JavaScript error(s): "
                f"{page_errors!r}"
            )

        local_receipt = browser.get("local_receipt")
        if isinstance(local_receipt, Mapping):
            if (
                local_receipt.get("kind")
                == "thinkument_outbound_dispatch_validation_v1"
                and local_receipt.get("ok") is False
            ):
                self._raise_station_guard_rejection_v1(
                    A=A,
                    receipt=local_receipt,
                )

            if (
                local_receipt.get("kind")
                == "thinkument_sufficience_local_error_v1"
            ):
                self._raise_local_error_v1(
                    A=A,
                    observation=observation,
                    receipt=local_receipt,
                )

        result = browser.get("dispatch_result")
        if not isinstance(result, Mapping):
            raise AssertionError(
                "sufficience DOM produced neither a dispatch result nor a "
                f"typed local rejection: browser={dict(browser)!r}"
            )

        return normalize_harmonized_server_receipt_v1(result)


__all__ = [
    "FlaskFacadeWithThinkumentJSSufficienceBrowserDryRunStrategy",
    "P7_TRANSPORT_BOUNDARY_CASE",
    "SUFFICIENCE_OPINIONATION_LOGICAL_NAME",
]
