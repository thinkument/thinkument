# think-frontend/src/live_vial/_flask/launch_local_flask_server.py
#!/usr/bin/env python3
from __future__ import annotations

"""Launch a local Flask demo directly through _thinksessions.run.run_from_here."""

import argparse
import json
from typing import Any, Dict, Mapping, Optional

from live_vial._flask._helpers_for_local_server import (
    build_local_flask_launch_spec,
    load_program_wrapper_from_python_file,
    normalize_program_wrapper,
    parse_local_flask_target,
    print_launcher_debug_surface,
)
from live_vial._flask.server_wrapper import (
    close_app_sessions,
    create_app_for_program,
    print_access_handles_for_program,
)


_REMOVED_WEB_OPTION_KEYS = {
    "html",
    "embed_html",
    "rendered_html",
    "bootstrap_html",
    "template",
    "template_name",
    "renderer",
    "renderer_name",
    "dispatchUrl",
}


def _json_arg(
    value: Optional[str],
    *,
    name: str,
) -> Dict[str, Any]:
    if value in (None, ""):
        return {}

    try:
        parsed = json.loads(str(value))
    except Exception as exc:
        raise SystemExit(
            f"{name} must be valid JSON: {exc}"
        ) from exc

    if not isinstance(parsed, dict):
        raise SystemExit(
            f"{name} must be a JSON object"
        )

    return dict(parsed)


def _validate_ui_session_opts(
    value: Mapping[str, Any],
) -> Dict[str, Any]:
    stale = sorted(
        set(map(str, value))
        & _REMOVED_WEB_OPTION_KEYS
    )
    if stale:
        raise ValueError(
            "ui session options contain removed "
            f"presentation keys {stale}; "
            "web modules are selected by "
            "page/embed routes"
        )

    return dict(value)


def serve_program_wrapper_on_flask(
    wrapper: Mapping[str, Any],
    *,
    raw_target: str,
    ui_session_opts: Optional[
        Mapping[str, Any]
    ] = None,
    host: str = "127.0.0.1",
    port: int = 5000,
    debug: bool = True,
) -> None:
    launch_spec = build_local_flask_launch_spec(
        wrapper=normalize_program_wrapper(
            wrapper
        ),
        ui_session_opts=_validate_ui_session_opts(
            dict(ui_session_opts or {})
        ),
    )

    print_launcher_debug_surface(
        raw_target=raw_target,
        launch_spec=launch_spec,
    )
    app = create_app_for_program(
        launch_spec=launch_spec
    )
    print(
        f"🚀 Server listening at "
        f"http://{host}:{port}/"
    )
    print_access_handles_for_program(
        app=app,
        host=host,
        port=port,
    )

    try:
        # Formal local-runtime boundary:
        #
        # The highest facade owns process-local per-session serialization and
        # process-local scope/target staleness indexes. Therefore this demo
        # runtime must have exactly one OS process. Concurrent request threads
        # are supported, and writes for different sessions may execute
        # concurrently. Flask's reloader and multi-process mode are forbidden.
        app.run(
            host=host,
            port=port,
            debug=debug,
            use_reloader=False,
            threaded=True,
            processes=1,
        )
    finally:
        close_app_sessions(app)


def serve_manifest_on_flask(
    manifest_json: str,
    **kwargs: Any,
) -> None:
    serve_program_wrapper_on_flask(
        parse_local_flask_target(
            manifest_json
        ),
        raw_target=manifest_json,
        **kwargs,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local Flask server for "
            "a Thinkument program"
        )
    )
    parser.add_argument(
        "target",
        nargs="?",
        help=(
            "JSON wrapper with "
            "program_language and program"
        ),
    )
    parser.add_argument("--program-file")
    parser.add_argument("--program-symbol")
    parser.add_argument("--program-language")
    parser.add_argument(
        "--ui-session-opts-json"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
    )
    parser.add_argument(
        "--no-debug",
        action="store_true",
    )
    return parser


def _run_cli() -> None:
    parser = _parser()
    args = parser.parse_args()

    ui_opts = _json_arg(
        args.ui_session_opts_json,
        name="--ui-session-opts-json",
    )

    has_file = bool(args.program_file)
    has_symbol = bool(args.program_symbol)

    if has_file != has_symbol:
        parser.error(
            "--program-file and --program-symbol "
            "must be supplied together"
        )

    if has_file and args.target:
        parser.error(
            "choose a Python file/symbol or "
            "positional JSON wrapper, not both"
        )

    try:
        if has_file:
            wrapper = (
                load_program_wrapper_from_python_file(
                    file_path=args.program_file,
                    symbol=args.program_symbol,
                    program_language=(
                        args.program_language
                    ),
                )
            )
            serve_program_wrapper_on_flask(
                wrapper,
                raw_target=(
                    f"{args.program_file}:"
                    f"{args.program_symbol}"
                ),
                ui_session_opts=ui_opts,
                host=args.host,
                port=args.port,
                debug=not args.no_debug,
            )
            return

        if args.target:
            if args.program_language:
                parser.error(
                    "--program-language is only "
                    "for raw Python symbols"
                )

            serve_manifest_on_flask(
                args.target,
                ui_session_opts=ui_opts,
                host=args.host,
                port=args.port,
                debug=not args.no_debug,
            )
            return
    except ValueError as exc:
        parser.error(str(exc))

    parser.error(
        "provide --program-file/--program-symbol "
        "or a positional JSON wrapper"
    )


if __name__ == "__main__":
    _run_cli()


__all__ = [
    "normalize_program_wrapper",
    "serve_manifest_on_flask",
    "serve_program_wrapper_on_flask",
]