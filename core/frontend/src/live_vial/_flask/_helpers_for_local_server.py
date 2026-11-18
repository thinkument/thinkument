# think-frontend/src/live_vial/_flask/_helpers_for_local_server.py
from __future__ import annotations

"""Program-wrapper preparation for the highest-facade local Flask server."""

import importlib.util
import json
import os
import sys
import uuid
from copy import deepcopy
from typing import Any, Dict, Mapping, Optional

from __staticfiles_mgmt.globals import LOCAL_FLASK_RUNTIME_PROFILE


_MISSING = object()


def _mapping(value: Any, *, field: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be an object")
    return dict(value)


def _deep_merge(
    base: Mapping[str, Any] | None,
    update: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    out = deepcopy(dict(base or {}))
    for key, value in dict(update or {}).items():
        if (
            isinstance(out.get(key), Mapping)
            and isinstance(value, Mapping)
        ):
            out[str(key)] = _deep_merge(
                out[key],
                value,
            )  # type: ignore[arg-type]
        else:
            out[str(key)] = deepcopy(value)
    return out


def _opinionation_module_value(
    value: Any,
    *,
    field: str,
) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string or null")
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def normalize_program_wrapper(
    wrapper: Any,
    *,
    source: str = "program wrapper",
) -> Dict[str, Any]:
    if not isinstance(wrapper, Mapping):
        raise TypeError(f"{source} must be an object")

    data = dict(wrapper)
    if "language" in data:
        raise ValueError(
            f"{source} uses removed key 'language'; "
            "use 'program_language'"
        )

    if "program_language" not in data or "program" not in data:
        raise ValueError(
            f"{source} requires 'program_language' and 'program'"
        )

    language = str(data["program_language"] or "").strip()
    if not language:
        raise ValueError(f"{source}.program_language cannot be empty")

    out = {
        "program_language": language,
        "program": data["program"],
    }
    if "session_surface" in data:
        out["session_surface"] = _mapping(
            data["session_surface"],
            field=f"{source}.session_surface",
        )

    return out


def parse_local_flask_target(target: str) -> Dict[str, Any]:
    try:
        value = json.loads(str(target or ""))
    except Exception as exc:
        raise ValueError(
            f"target must be a JSON program wrapper: {exc}"
        ) from exc

    return normalize_program_wrapper(
        value,
        source="JSON target",
    )


def load_symbol_from_python_file(
    *,
    file_path: str,
    symbol: str,
) -> Any:
    path = os.path.abspath(
        os.path.expanduser(str(file_path or ""))
    )
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    symbol_name = str(symbol or "").strip()
    if not symbol_name:
        raise ValueError("program symbol cannot be empty")

    module_name = f"_thinkument_local_demo_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"could not import {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise

    if not hasattr(module, symbol_name):
        available = sorted(
            name
            for name in vars(module)
            if not name.startswith("__")
        )
        raise AttributeError(
            f"{symbol_name!r} not found in {path}; "
            f"available={available}"
        )

    return getattr(module, symbol_name)


def coerce_loaded_symbol_to_program_wrapper(
    value: Any,
    *,
    program_language: Optional[str],
    source: str,
) -> Dict[str, Any]:
    if (
        isinstance(value, Mapping)
        and {"program_language", "program"}.issubset(value)
    ):
        wrapper = normalize_program_wrapper(
            value,
            source=source,
        )
        forced = str(program_language or "").strip()
        if forced and forced != wrapper["program_language"]:
            raise ValueError(
                f"{source} declares "
                f"{wrapper['program_language']!r}, "
                f"but CLI forced {forced!r}"
            )
        return wrapper

    language = str(program_language or "").strip()
    if not language:
        raise ValueError(
            f"{source} is a raw program symbol; "
            "--program-language is required"
        )

    return {
        "program_language": language,
        "program": value,
    }


def load_program_wrapper_from_python_file(
    *,
    file_path: str,
    symbol: str,
    program_language: Optional[str] = None,
) -> Dict[str, Any]:
    return coerce_loaded_symbol_to_program_wrapper(
        load_symbol_from_python_file(
            file_path=file_path,
            symbol=symbol,
        ),
        program_language=program_language,
        source=f"{file_path}:{symbol}",
    )


def build_local_flask_launch_spec(
    *,
    wrapper: Mapping[str, Any],
    ui_session_opts: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    normalized = normalize_program_wrapper(wrapper)
    surface = _mapping(
        normalized.get("session_surface"),
        field="session_surface",
    )
    explicit = _mapping(
        ui_session_opts,
        field="ui_session_opts",
    )

    if "initial_parameter_overrides" in surface:
        raise ValueError(
            "local Flask wrappers run one exact authored program and may not "
            "declare session_surface.initial_parameter_overrides; "
            "ThinkProgramTM launch overrides belong to Django starters or "
            "direct _thinksessions.run.run_from_here callers"
        )

    session_metadata = _mapping(
        surface.get("session_metadata"),
        field="session_surface.session_metadata",
    )
    roles = _mapping(
        surface.get("roles"),
        field="session_surface.roles",
    )
    policy = _mapping(
        surface.get("role_mismatch_policy"),
        field="session_surface.role_mismatch_policy",
    )
    public_view_role = surface.get("public_view_role")

    explicit = dict(explicit)
    roles = _deep_merge(
        roles,
        _mapping(
            explicit.pop("roles", None),
            field="ui_session_opts.roles",
        ),
    )
    policy = _deep_merge(
        policy,
        _mapping(
            explicit.pop("role_mismatch_policy", None),
            field="ui_session_opts.role_mismatch_policy",
        ),
    )
    public_view_role = explicit.pop(
        "public_view_role",
        public_view_role,
    )
    include_unmodulated_access = bool(
        explicit.pop(
            "include_unmodulated_access",
            surface.get("include_unmodulated_access", False),
        )
    )
    expose_typed_exceptions = bool(
        explicit.pop(
            "expose_typed_exceptions",
            surface.get("expose_typed_exceptions", False),
        )
    )
    eps_visibility_of = explicit.pop(
        "eps_visibility_of",
        surface.get("eps_visibility_of", None),
    )
    eps_channel_validator = explicit.pop(
        "eps_channel_validator",
        surface.get("eps_channel_validator", None),
    )
    eps_ttl_seconds_of = explicit.pop(
        "eps_ttl_seconds_of",
        surface.get("eps_ttl_seconds_of", None),
    )
    eps_should_persist = explicit.pop(
        "eps_should_persist",
        surface.get("eps_should_persist", None),
    )

    # Frontend opinionation is a launch-level browser composition choice, not
    # session metadata. Absent means "use the one installed package default";
    # explicit null/blank means "disable opinionation for this launch"; a
    # string selects that registered logical static module. ui_session_opts
    # wins so individual tests/hosts can choose independently.
    opinionation_module: object = explicit.pop(
        "opinionation_module",
        _MISSING,
    )
    if opinionation_module is _MISSING:
        opinionation_module = surface.get(
            "opinionation_module",
            _MISSING,
        )

    explicit_metadata = _mapping(
        explicit.pop("session_metadata", None),
        field="ui_session_opts.session_metadata",
    )
    session_metadata = _deep_merge(
        session_metadata,
        explicit_metadata,
    )
    session_metadata = _deep_merge(
        session_metadata,
        explicit,
    )

    out: Dict[str, Any] = {
        "kind": "thinkument_local_flask_launch_spec_v1",
        "runtime_profile": LOCAL_FLASK_RUNTIME_PROFILE,
        "program_language": normalized["program_language"],
        "program": normalized["program"],
        "session_metadata": session_metadata,
        "roles": roles,
        "role_mismatch_policy": policy,
        "public_view_role": (
            None
            if public_view_role in (None, "")
            else str(public_view_role)
        ),
        "start_on_create": bool(
            surface.get("start_on_create", True)
        ),
        # Optional trusted local capability.  When enabled, the Flask adapter
        # creates one opaque role=None access handle even for roleful sessions.
        # It is used by server-to-server/testing clients that need the same
        # unmodulated read/write lens available at the highest facade.
        "include_unmodulated_access": include_unmodulated_access,
        # Optional local-only exception transport.  Ordinary launches keep
        # Flask's opaque 500 behavior; a trusted adapter may request typed
        # exception name/message packets so remote preflight exceptions can be
        # reified into its own standard execution vocabulary.
        "expose_typed_exceptions": expose_typed_exceptions,
        "eps_visibility_of": eps_visibility_of,
        "eps_channel_validator": eps_channel_validator,
        "eps_ttl_seconds_of": eps_ttl_seconds_of,
        "eps_should_persist": eps_should_persist,
    }

    if opinionation_module is not _MISSING:
        out["opinionation_module"] = _opinionation_module_value(
            opinionation_module,
            field="opinionation_module",
        )

    return out


def print_launcher_debug_surface(
    *,
    raw_target: str,
    launch_spec: Mapping[str, Any],
) -> None:
    print("=")
    print("🔎 launch debug surface")
    print(f"  raw_target={raw_target!r}")
    print(
        "  program_language="
        f"{launch_spec.get('program_language')!r}"
    )
    print(
        "  role_names="
        f"{sorted(dict(launch_spec.get('roles') or {}))}"
    )
    print(
        "  public_view_role="
        f"{launch_spec.get('public_view_role')!r}"
    )
    print(
        "  opinionation_module="
        + (
            "<installed default>"
            if "opinionation_module" not in launch_spec
            else repr(launch_spec.get("opinionation_module"))
        )
    )
    print(
        "  engine_entry="
        "_thinksessions.run.run_from_here."
        "create_live_session_from_program"
    )
    print(
        "  runtime_profile="
        f"{launch_spec.get('runtime_profile')!r}"
    )
    print(
        "  concurrency="
        "exactly one OS process; concurrent request threads; "
        "independent per-session highest-facade serialized write lanes"
    )
    print("  polling=stateless cursor polling over one canonical queue")


__all__ = [
    "build_local_flask_launch_spec",
    "coerce_loaded_symbol_to_program_wrapper",
    "load_program_wrapper_from_python_file",
    "load_symbol_from_python_file",
    "normalize_program_wrapper",
    "parse_local_flask_target",
    "print_launcher_debug_surface",
]
