from __future__ import annotations

"""Flask P/SM/C -> DOMScriptrTM server starter and scripted-run CLI.

This adapter is intentionally thin:

* P / SM / C loading and opinionation selection come from ``live_run_atelier``;
* the existing local Flask facade still owns Thinkument session creation,
  role-sealed URLs, HTML, JS assets, dispatch, polling, and cleanup;
* DOMScriptrTM owns browser/client/page lifetime;
* the scenario owns every DOM/JS action and expectation.

It imports no dry-run runner, A/E matcher, strategy, or proof facade.

``start_on_create`` defaults to False for scripted runs so the script can own
and observe the first STEP. A caller may opt into live-demo bootstrap semantics
explicitly.

C compatibility seam
--------------------
The local Flask launch spec still consumes one already-effective program plus
already-separated session metadata/roles/policy; it exposes no C argument.
The canonical run-from-here parameter semantics route one C over the joint
Param(P) union Param(SM) surface and bind symbolic SM. This adapter therefore
reuses ``materialize_joint_p_sm_c_v1`` exactly once immediately before crossing
that older Flask launch-spec boundary. It does not define another overlay
language.
"""

import argparse
import asyncio
import json
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from _thinkprogram.thinkprogramTM.api import LANG_THINK_PROGRAM_V1
from live_vial._flask._helpers_for_local_server import build_local_flask_launch_spec
from live_vial._flask.adapter import build_access_handle_urls
from live_vial._flask.server_wrapper import (
    close_app_sessions,
    create_app_for_program,
    get_app_launch_bundle,
)
from werkzeug.serving import WSGIRequestHandler, make_server

from ways_to_run.live_run_atelier._whichserver_agnostic_demo_launcher import (
    LiveDemoOpinionationSelectionV1,
    LiveRunTapeV1,
    add_live_run_opinionation_arguments_v1,
    add_live_run_source_arguments_v1,
    choose_public_view_role_v1,
    live_run_opinionation_from_namespace_v1,
    live_run_tape_from_namespace_v1,
    materialize_joint_p_sm_c_v1,
    prepare_runtime_hooks_v1,
    prepare_runtime_refs_v1,
    split_session_metadata_v1,
)
from ._whichserver_agnostic_scripted_DOM_run_launcher import (
    DOMScriptV1,
    ScriptedDOMAtelierV1,
    ScriptedDOMRunReceiptV1,
    resolve_dom_script_ref_v1,
    run_scripted_dom_once_v1,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 0
# This value affects only the idle/shutdown selector cadence of Werkzeug's
# serve_forever loop. Requests wake the selector immediately, so 50 ms keeps
# live request handling crisp while avoiding a needless 100 wakeups/second per
# otherwise idle demo server.
DEFAULT_SERVER_POLL_SECONDS = 0.05
DEFAULT_READINESS_TIMEOUT_SECONDS = 10.0


class _QuietWSGIRequestHandler(WSGIRequestHandler):
    def log(self, type: str, message: str, *args: Any) -> None:
        del type, message, args


def flask_role_url_key_v1(role: Optional[str]) -> str:
    """Stable named-URL key for one role-sealed browser page."""
    return "role:<none>" if role in (None, "") else f"role:{str(role).strip()}"


def _absolute_urls_v1(
    *,
    app: Any,
    access_ids: Mapping[str, str],
    base_url: str,
) -> dict[str, dict[str, str]]:
    with app.test_request_context("/"):
        relative = build_access_handle_urls(
            access_ids={str(key): str(value) for key, value in access_ids.items()}
        )

    out: dict[str, dict[str, str]] = {}
    for key, row in dict(relative).items():
        if not isinstance(row, Mapping):
            raise RuntimeError(
                f"Flask access URL row {key!r} is not a mapping: {row!r}"
            )
        out[str(key)] = {
            str(name): urljoin(
                f"{base_url.rstrip('/')}/",
                str(value).lstrip("/"),
            )
            for name, value in dict(row).items()
            if name != "role" and value not in (None, "")
        }
    return out


def _role_access_ids_v1(
    *,
    bundle: Mapping[str, Any],
    roles: Mapping[str, Any],
) -> tuple[tuple[Optional[str], str], ...]:
    raw = bundle.get("access_ids")
    access_ids = dict(raw) if isinstance(raw, Mapping) else {}

    if roles:
        rows: list[tuple[Optional[str], str]] = []
        for role in roles:
            access_id = str(access_ids.get(str(role)) or "").strip()
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

    raise RuntimeError(
        "roleless Flask launch did not expose one public access capability"
    )


@dataclass(slots=True)
class FlaskScriptedDOMServerV1:
    """Zero-argument DOMScriptr-compatible starter for one Flask P/SM/C run."""

    tape: LiveRunTapeV1
    opinionation: LiveDemoOpinionationSelectionV1
    public_view_role: Optional[str] = None
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    server_poll_seconds: float = DEFAULT_SERVER_POLL_SECONDS
    readiness_timeout_seconds: float = DEFAULT_READINESS_TIMEOUT_SECONDS
    quiet: bool = True
    start_on_create: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.tape, LiveRunTapeV1):
            raise TypeError("tape must be LiveRunTapeV1")
        if not isinstance(self.opinionation, LiveDemoOpinionationSelectionV1):
            raise TypeError("opinionation must be LiveDemoOpinionationSelectionV1")

        self.host = str(self.host or "").strip()
        if not self.host:
            raise ValueError("host must be non-empty")

        self.port = int(self.port)
        if self.port < 0 or self.port > 65535:
            raise ValueError("port must be between 0 and 65535")

        self.server_poll_seconds = float(self.server_poll_seconds)
        if self.server_poll_seconds <= 0:
            raise ValueError("server_poll_seconds must be > 0")

        self.readiness_timeout_seconds = float(self.readiness_timeout_seconds)
        if self.readiness_timeout_seconds <= 0:
            raise ValueError("readiness_timeout_seconds must be > 0")

    def __call__(self):
        """Allow ``start_server=server`` as well as ``server.start_server_v1``."""
        return self.start_server_v1()

    @contextmanager
    def start_server_v1(self) -> Iterator[Mapping[str, str]]:
        """Start threaded Werkzeug and yield after one lightweight API probe."""
        effective = materialize_joint_p_sm_c_v1(self.tape)
        metadata, roles, role_mismatch_policy = split_session_metadata_v1(
            effective.session_metadata
        )
        selected_role = choose_public_view_role_v1(
            roles=roles,
            requested=self.public_view_role,
        )

        session_surface: dict[str, Any] = {
            "session_metadata": metadata,
            "roles": roles,
            "role_mismatch_policy": role_mismatch_policy,
            "public_view_role": selected_role,
            "start_on_create": bool(self.start_on_create),
            "include_unmodulated_access": False,
        }
        if self.opinionation.module is not None:
            session_surface["opinionation_module"] = self.opinionation.module
        elif not self.opinionation.use_installed_default:
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
        thread: Optional[threading.Thread] = None
        cleanup_error: Optional[BaseException] = None
        try:
            bundle = get_app_launch_bundle(app)
            request_handler = (
                _QuietWSGIRequestHandler if self.quiet else WSGIRequestHandler
            )
            server = make_server(
                self.host,
                self.port,
                app,
                threaded=True,
                request_handler=request_handler,
            )
            base_url = f"http://{self.host}:{int(server.server_port)}"

            role_access_ids = _role_access_ids_v1(bundle=bundle, roles=roles)
            access_by_key = {
                flask_role_url_key_v1(role): access_id
                for role, access_id in role_access_ids
            }
            absolute = _absolute_urls_v1(
                app=app,
                access_ids=access_by_key,
                base_url=base_url,
            )

            page_urls: dict[str, str] = {}
            for role, _access_id in role_access_ids:
                key = flask_role_url_key_v1(role)
                page = str(dict(absolute.get(key) or {}).get("page") or "").strip()
                if not page:
                    raise RuntimeError(
                        f"Flask scripted DOM access {key!r} has no page URL"
                    )
                page_urls[key] = page

            selected_key = flask_role_url_key_v1(selected_role)
            if selected_key not in page_urls:
                raise RuntimeError(
                    "selected Flask scripted DOM role has no page URL: "
                    f"selected_role={selected_role!r}, keys={sorted(page_urls)!r}"
                )
            page_urls["web"] = page_urls[selected_key]

            # Readiness does not need to render the HTML run page once before
            # Chromium immediately renders it again. Probe the same selected
            # access capability through its tiny queue-high-water endpoint.
            # This proves the request loop and capability wiring are live while
            # keeping the first real page render owned by the browser scenario.
            readiness_url = str(
                dict(absolute.get(selected_key) or {}).get("latestEventSeq") or ""
            ).strip()
            if not readiness_url:
                raise RuntimeError(
                    "selected Flask scripted DOM access has no latestEventSeq "
                    f"URL: selected_role={selected_role!r}"
                )

            thread = threading.Thread(
                target=server.serve_forever,
                kwargs={"poll_interval": self.server_poll_seconds},
                name="thinkument-flask-scripted-dom-server",
                daemon=True,
            )
            thread.start()

            # make_server() has already bound and listened. One real, cheap API
            # request is a causal readiness barrier; there is no sleep/backoff.
            request = Request(
                readiness_url,
                headers={"Accept": "application/json"},
                method="GET",
            )
            with urlopen(
                request,
                timeout=self.readiness_timeout_seconds,
            ) as response:
                if int(response.status) != 200:
                    raise RuntimeError(
                        "Flask scripted DOM readiness request failed: "
                        f"status={response.status}, url={readiness_url!r}"
                    )
                response.read(1)

            yield page_urls
        finally:
            primary_exception_active = sys.exc_info()[0] is not None

            if server is not None:
                try:
                    server.shutdown()
                except BaseException as exc:
                    cleanup_error = exc
                try:
                    server.server_close()
                except BaseException as exc:
                    cleanup_error = cleanup_error or exc

            if thread is not None:
                try:
                    thread.join(timeout=5)
                except BaseException as exc:
                    cleanup_error = cleanup_error or exc
                if thread.is_alive():
                    cleanup_error = cleanup_error or RuntimeError(
                        "Flask scripted DOM server thread did not terminate"
                    )

            try:
                close_app_sessions(app)
            except BaseException as exc:
                cleanup_error = cleanup_error or exc

            # Preserve the scenario's first useful failure. On success, cleanup
            # remains strict so resource-lifetime regressions cannot pass.
            if cleanup_error is not None and not primary_exception_active:
                raise RuntimeError(
                    "Flask scripted DOM server cleanup failed"
                ) from cleanup_error


async def run_flask_scripted_dom_in_atelier_v1(
    *,
    atelier: ScriptedDOMAtelierV1,
    tape: LiveRunTapeV1,
    script: DOMScriptV1[Any],
    opinionation: Optional[LiveDemoOpinionationSelectionV1] = None,
    public_view_role: Optional[str] = None,
    prepare_runtime: Sequence[Callable[[], Any]] = (),
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    quiet: bool = True,
    start_on_create: bool = False,
) -> ScriptedDOMRunReceiptV1:
    """Run one Flask scenario inside an already-entered reusable atelier.

    This is the throughput path for suites: registration can be done once, one
    Chromium process stays alive, and each scenario still gets a fresh Flask
    server/session plus fresh BrowserContexts.
    """
    prepare_runtime_hooks_v1(prepare_runtime)
    selection = opinionation or LiveDemoOpinionationSelectionV1(
        module=None,
        use_installed_default=True,
    )
    server = FlaskScriptedDOMServerV1(
        tape=tape,
        opinionation=selection,
        public_view_role=public_view_role,
        host=host,
        port=port,
        quiet=quiet,
        start_on_create=start_on_create,
    )
    return await atelier.run_v1(
        script=script,
        start_server=server,
    )


async def run_flask_scripted_dom_v1(
    *,
    tape: LiveRunTapeV1,
    script: DOMScriptV1[Any],
    opinionation: Optional[LiveDemoOpinionationSelectionV1] = None,
    public_view_role: Optional[str] = None,
    prepare_runtime: Sequence[Callable[[], Any]] = (),
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    quiet: bool = True,
    start_on_create: bool = False,
    headless: bool = True,
    slow_mo: Optional[float] = None,
    launch_options: Optional[Mapping[str, Any]] = None,
) -> ScriptedDOMRunReceiptV1:
    """One-shot Flask convenience; larger suites should reuse an atelier."""
    prepare_runtime_hooks_v1(prepare_runtime)
    selection = opinionation or LiveDemoOpinionationSelectionV1(
        module=None,
        use_installed_default=True,
    )
    server = FlaskScriptedDOMServerV1(
        tape=tape,
        opinionation=selection,
        public_view_role=public_view_role,
        host=host,
        port=port,
        quiet=quiet,
        start_on_create=start_on_create,
    )
    return await run_scripted_dom_once_v1(
        script=script,
        start_server=server,
        headless=headless,
        slow_mo=slow_mo,
        launch_options=launch_options,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ways_to_run.live_run_DOMscripted_atelier.flask_scripted_DOM_run_launcher",
        description=(
            "Launch one authored Thinkument P/SM/C tape through the real local "
            "Flask frontend and execute one direct DOM script with DOMScriptrTM."
        ),
    )
    add_live_run_source_arguments_v1(parser)
    add_live_run_opinionation_arguments_v1(parser)
    parser.add_argument(
        "--script",
        required=True,
        metavar="MODULE:CALLABLE",
        help="Callable receiving the raw DOMScriptrTM Run.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show Chromium instead of running headless.",
    )
    parser.add_argument(
        "--slow-mo",
        type=float,
        default=None,
        help="Optional Playwright slow_mo for visible debugging.",
    )
    parser.add_argument(
        "--start-on-create",
        action="store_true",
        help=(
            "Use live-demo bootstrap semantics. Default is false so the DOM "
            "script owns the first STEP explicitly."
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
    script = resolve_dom_script_ref_v1(args.script)
    opinionation = live_run_opinionation_from_namespace_v1(args)

    receipt = asyncio.run(
        run_flask_scripted_dom_v1(
            tape=tape,
            script=script,
            opinionation=opinionation,
            public_view_role=args.public_view_role,
            host=args.host,
            port=args.port,
            quiet=not bool(args.request_log),
            start_on_create=bool(args.start_on_create),
            headless=not bool(args.headed),
            slow_mo=args.slow_mo,
        )
    )

    if bool(args.json_output):
        print(json.dumps(receipt.to_dict(), indent=2, sort_keys=True, default=str))
    else:
        print(f"DOM script passed: {receipt.script_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_READINESS_TIMEOUT_SECONDS",
    "DEFAULT_SERVER_POLL_SECONDS",
    "FlaskScriptedDOMServerV1",
    "flask_role_url_key_v1",
    "run_flask_scripted_dom_in_atelier_v1",
    "run_flask_scripted_dom_v1",
]
