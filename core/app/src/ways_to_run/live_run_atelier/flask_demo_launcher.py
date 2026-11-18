from __future__ import annotations

"""Flask live-demo host for one authored P / SM / C tape.

This is deliberately not a dry-run strategy. It launches one live session
through the existing local Flask facade, exposes the real role-sealed HTML
pages, and keeps the WSGI server alive for manual browser I/O.

The app-level host crosses ``bootstrap_higher_app.runtime`` rather than importing
the lower frontend server wrapper directly. That preserves one installed
composition artery for ordinary Flask, live/scripted Flask, Django, and future
higher hosts.

The local Flask launch spec is an older seam that consumes an already-effective
program plus already-resolved/split SM. The shared live-run atelier therefore
materializes canonical joint C semantics exactly once before crossing that
boundary: C ranges over Param(P) union Param(SM).
"""

import argparse
import threading
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import urljoin

from _thinkprogram.thinkprogramTM.api import LANG_THINK_PROGRAM_V1
from bootstrap_higher_app.runtime import (
    close_app_sessions,
    create_app_for_program,
    get_app_launch_bundle,
)
from live_vial._flask._helpers_for_local_server import (
    build_local_flask_launch_spec,
)
from live_vial._flask.adapter import build_access_handle_urls
from werkzeug.serving import WSGIRequestHandler, make_server

from ._whichserver_agnostic_demo_launcher import (
    BaseLiveDemoLauncherV1,
    LiveDemoHandleV1,
    LiveDemoLaunchReceiptV1,
    LiveDemoOpinionationSelectionV1,
    LiveDemoRoleAccessV1,
    LiveRunTapeV1,
    add_live_run_opinionation_arguments_v1,
    add_live_run_source_arguments_v1,
    choose_public_view_role_v1,
    live_run_opinionation_from_namespace_v1,
    live_run_tape_from_namespace_v1,
    materialize_joint_p_sm_c_v1,
    prepare_runtime_refs_v1,
    render_launch_receipt_v1,
    split_session_metadata_v1,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 0
DEFAULT_SERVER_POLL_SECONDS = 0.05


class _QuietWSGIRequestHandler(WSGIRequestHandler):
    def log(self, type: str, message: str, *args: Any) -> None:
        del type, message, args


@dataclass(slots=True)
class FlaskLiveDemoHandleV1:
    app: Any
    server: Any
    base_url: str
    session_id: str
    selected_role: Optional[str]
    accesses: tuple[LiveDemoRoleAccessV1, ...]
    serving: bool = False
    serving_thread_ident: Optional[int] = None
    closed: bool = False


class FlaskLiveDemoLauncherV1(BaseLiveDemoLauncherV1):
    """Launch and host manual Thinkument browser sessions through Flask."""

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        server_poll_seconds: float = DEFAULT_SERVER_POLL_SECONDS,
        quiet: bool = True,
        opinionation: Optional[LiveDemoOpinionationSelectionV1] = None,
        opinionation_module: Optional[str] = None,
    ) -> None:
        normalized_host = str(host or "").strip()
        if not normalized_host:
            raise ValueError("host must be non-empty")

        normalized_port = int(port)
        if normalized_port < 0 or normalized_port > 65535:
            raise ValueError("port must be between 0 and 65535")

        poll = float(server_poll_seconds)
        if poll <= 0:
            raise ValueError("server_poll_seconds must be > 0")

        if opinionation is not None and opinionation_module not in (None, ""):
            raise ValueError(
                "supply either opinionation or opinionation_module, not both"
            )

        if opinionation is None:
            normalized_opinionation = None
            if opinionation_module not in (None, ""):
                normalized_opinionation = str(opinionation_module).strip() or None
            opinionation = LiveDemoOpinionationSelectionV1(
                module=normalized_opinionation,
                use_installed_default=True,
            )

        self._host = normalized_host
        self._port = normalized_port
        self._server_poll_seconds = poll
        self._quiet = bool(quiet)
        self._opinionation = opinionation

    @property
    def launcher_name(self) -> str:
        return "flask-live-demo-launcher-v1"

    @staticmethod
    def _absolute_urls(
        *,
        app: Any,
        access_ids: Mapping[str, str],
        base_url: str,
    ) -> dict[str, dict[str, str]]:
        with app.test_request_context("/"):
            relative = build_access_handle_urls(
                access_ids={
                    str(key): str(value)
                    for key, value in dict(access_ids).items()
                }
            )

        out: dict[str, dict[str, str]] = {}
        for key, row in dict(relative).items():
            if not isinstance(row, Mapping):
                raise RuntimeError(
                    f"Flask access URL row {key!r} is not a mapping: {row!r}"
                )
            urls = {
                str(name): urljoin(
                    f"{base_url.rstrip('/')}/",
                    str(value).lstrip("/"),
                )
                for name, value in dict(row).items()
                if name != "role" and value not in (None, "")
            }
            if not str(urls.get("page") or "").strip():
                raise RuntimeError(
                    f"Flask live access {key!r} does not expose a page URL"
                )
            out[str(key)] = urls
        return out

    @staticmethod
    def _role_access_ids(
        *,
        bundle: Mapping[str, Any],
        roles: Mapping[str, Any],
    ) -> tuple[tuple[Optional[str], str], ...]:
        raw = bundle.get("access_ids")
        access_ids = dict(raw) if isinstance(raw, Mapping) else {}

        if roles:
            rows: list[tuple[Optional[str], str]] = []
            for role in roles:
                access_id = str(access_ids.get(role) or "").strip()
                if not access_id:
                    raise RuntimeError(
                        f"Flask launch omitted access capability for role {role!r}"
                    )
                rows.append((str(role), access_id))
            return tuple(rows)

        candidate = str(access_ids.get("default") or "").strip()
        if candidate:
            return ((None, candidate),)
        if len(access_ids) == 1:
            return ((None, str(next(iter(access_ids.values())))),)

        unmodulated = str(
            bundle.get("unmodulated_access_id") or ""
        ).strip()
        if unmodulated:
            return ((None, unmodulated),)

        raise RuntimeError(
            "roleless Flask launch did not expose one public access capability"
        )

    def start_v1(
        self,
        *,
        tape: LiveRunTapeV1,
        public_view_role: Optional[str],
    ) -> LiveDemoHandleV1:
        if not isinstance(tape, LiveRunTapeV1):
            raise TypeError("tape must be LiveRunTapeV1")

        effective = materialize_joint_p_sm_c_v1(tape)
        metadata, roles, role_mismatch_policy = split_session_metadata_v1(
            effective.session_metadata
        )
        selected_role = choose_public_view_role_v1(
            roles=roles,
            requested=public_view_role,
        )

        session_surface: dict[str, Any] = {
            "session_metadata": metadata,
            "roles": roles,
            "role_mismatch_policy": role_mismatch_policy,
            "public_view_role": selected_role,
            "start_on_create": True,
            "include_unmodulated_access": False,
        }

        if self._opinionation.module is not None:
            session_surface["opinionation_module"] = self._opinionation.module
        elif not self._opinionation.use_installed_default:
            session_surface["opinionation_module"] = None

        wrapper = {
            "program_language": LANG_THINK_PROGRAM_V1,
            "program": effective.program,
            "session_surface": session_surface,
        }

        app = create_app_for_program(
            launch_spec=build_local_flask_launch_spec(wrapper=wrapper)
        )
        server: Any = None
        try:
            bundle = get_app_launch_bundle(app)
            session_id = str(bundle.get("session_id") or "").strip()
            if not session_id:
                raise RuntimeError("Flask launch bundle omitted session_id")

            request_handler = (
                _QuietWSGIRequestHandler
                if self._quiet
                else WSGIRequestHandler
            )
            server = make_server(
                self._host,
                self._port,
                app,
                threaded=True,
                request_handler=request_handler,
            )
            base_url = f"http://{self._host}:{int(server.server_port)}"

            role_access_ids = self._role_access_ids(
                bundle=bundle,
                roles=roles,
            )
            keyed_access_ids = {
                (role if role is not None else "default"): access_id
                for role, access_id in role_access_ids
            }
            absolute = self._absolute_urls(
                app=app,
                access_ids=keyed_access_ids,
                base_url=base_url,
            )

            accesses: list[LiveDemoRoleAccessV1] = []
            for role, _access_id in role_access_ids:
                key = role if role is not None else "default"
                urls = absolute.get(str(key))
                if urls is None:
                    raise RuntimeError(
                        f"Flask URL builder omitted access row {key!r}"
                    )
                accesses.append(
                    LiveDemoRoleAccessV1(
                        role=role,
                        urls=urls,
                    )
                )

            return FlaskLiveDemoHandleV1(
                app=app,
                server=server,
                base_url=base_url,
                session_id=session_id,
                selected_role=selected_role,
                accesses=tuple(accesses),
            )
        except Exception:
            if server is not None:
                try:
                    server.server_close()
                except Exception:
                    pass
            close_app_sessions(app)
            raise

    @staticmethod
    def _handle(handle: LiveDemoHandleV1) -> FlaskLiveDemoHandleV1:
        if not isinstance(handle, FlaskLiveDemoHandleV1):
            raise TypeError("wrong handle for FlaskLiveDemoLauncherV1")
        return handle

    def receipt_v1(
        self,
        *,
        handle: LiveDemoHandleV1,
    ) -> LiveDemoLaunchReceiptV1:
        value = self._handle(handle)
        return LiveDemoLaunchReceiptV1(
            launcher_name=self.launcher_name,
            session_id=value.session_id,
            base_url=value.base_url,
            selected_role=value.selected_role,
            accesses=value.accesses,
        )

    def serve_v1(self, *, handle: LiveDemoHandleV1) -> None:
        value = self._handle(handle)
        if value.closed:
            raise RuntimeError("cannot serve a closed Flask live-demo handle")
        if value.serving:
            raise RuntimeError("Flask live-demo handle is already serving")

        value.serving = True
        value.serving_thread_ident = threading.get_ident()
        try:
            value.server.serve_forever(
                poll_interval=self._server_poll_seconds,
            )
        finally:
            value.serving = False
            value.serving_thread_ident = None

    def close_v1(self, *, handle: LiveDemoHandleV1) -> None:
        value = self._handle(handle)
        if value.closed:
            return

        if (
            value.serving
            and value.serving_thread_ident != threading.get_ident()
        ):
            value.server.shutdown()

        try:
            value.server.server_close()
        finally:
            try:
                close_app_sessions(value.app)
            finally:
                value.closed = True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ways_to_run.live_run_atelier.flask_demo_launcher",
        description=(
            "Launch one authored Thinkument P/SM/C tape through the real local "
            "Flask facade and print one live browser URL per role."
        ),
    )
    add_live_run_source_arguments_v1(parser)
    add_live_run_opinionation_arguments_v1(parser)
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Bind host (default: {DEFAULT_HOST}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=(
            "Bind port. Default 0 asks the OS for a free ephemeral port, "
            "which avoids collisions between concurrent demos."
        ),
    )
    parser.add_argument(
        "--request-log",
        action="store_true",
        help="Enable Werkzeug per-request logging.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    tape = live_run_tape_from_namespace_v1(args)
    prepare_runtime_refs_v1(tuple(args.prepare or ()))

    launcher = FlaskLiveDemoLauncherV1(
        host=args.host,
        port=args.port,
        quiet=not bool(args.request_log),
        opinionation=live_run_opinionation_from_namespace_v1(args),
    )
    handle: Any = None
    try:
        handle = launcher.start_v1(
            tape=tape,
            public_view_role=args.public_view_role,
        )
        receipt = launcher.receipt_v1(handle=handle)
        print(
            render_launch_receipt_v1(
                receipt,
                as_json=bool(args.json_output),
            ),
            flush=True,
        )
        launcher.serve_v1(handle=handle)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        if handle is not None:
            launcher.close_v1(handle=handle)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_SERVER_POLL_SECONDS",
    "FlaskLiveDemoHandleV1",
    "FlaskLiveDemoLauncherV1",
    "main",
]
