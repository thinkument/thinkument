from __future__ import annotations

"""Highest open-source runtime façade over the installed Thinkument composition."""

from typing import Any, Mapping

from live_vial._flask.launch_local_flask_server import (
    serve_program_wrapper_on_flask as _serve_program_wrapper_on_flask,
)
from live_vial._flask.server_wrapper import (
    close_app_sessions,
    create_app_for_program as _create_app_for_program,
    get_app_launch_bundle,
    print_access_handles_for_program,
)

from .higher_bootstrap import activate_installed_thinkument_composition_v1


def create_app_for_program(*, launch_spec: Mapping[str, Any]):
    """Create Flask over the same installed composition used by higher hosts."""

    activate_installed_thinkument_composition_v1()
    return _create_app_for_program(launch_spec=launch_spec)


def serve_program_wrapper_on_flask(
    wrapper: Mapping[str, Any],
    **kwargs: Any,
) -> None:
    """Serve Flask after activating the complete installed composition."""

    activate_installed_thinkument_composition_v1()
    _serve_program_wrapper_on_flask(wrapper, **kwargs)


__all__ = [
    "close_app_sessions",
    "create_app_for_program",
    "get_app_launch_bundle",
    "print_access_handles_for_program",
    "serve_program_wrapper_on_flask",
]
