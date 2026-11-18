from __future__ import annotations

from typing import Any, Dict
from collections.abc import Mapping

from _thinksessions.sesh_metadata.sesh_metadata_surface_puppeteering import (
    effective_symbol_values_v1 as _effective_symbol_values_v1,
    lookup_symbol_path_v1 as _lookup_symbol_path_v1,
    normalize_puppeteering_overlay_v1,
    overlay_puppeteering_onto_symbol_surface_v1,
    resolve_symbol_references_v1,
)

from ._constants import (
    _ALLOWED_TOP_LEVEL_KEYS_V1,
    THINK_PROGRAM_KIND_V1,
    THINK_PROGRAM_SURFACE_VERSION_V1,
)
from ._helpers import (
    assert_dead_json,
    deepcopy_json,
    reject_unknown_keys_v1,
    require_mapping,
)


def normalize_initial_parameter_overrides_v1(
    initial_parameter_overrides: Any,
) -> Dict[str, Any]:
    """ThinkProgram-facing name for the shared C normalizer."""
    return normalize_puppeteering_overlay_v1(
        initial_parameter_overrides
    )


def overlay_initial_parameter_overrides_onto_program_v1(
    program: Mapping[str, Any],
    *,
    initial_parameter_overrides: Any = None,
) -> Dict[str, Any]:
    """
    Apply C to ThinkProgram as one standalone shared-grammar symbol surface.

    The highest run façade performs joint P+SM routing before calling the lower
    program machinery; direct ThinkProgram lowering uses this one-surface form.
    """
    return overlay_puppeteering_onto_symbol_surface_v1(
        program,
        initial_parameter_overrides=initial_parameter_overrides,
        surface_path="program",
    )


def effective_symbols_v1(program: Mapping[str, Any]) -> Dict[str, Any]:
    return _effective_symbol_values_v1(
        program,
        surface_path="program",
    )


def lookup_symbol_path_v1(ref: str, symbols: Mapping[str, Any]) -> Any:
    return _lookup_symbol_path_v1(ref, symbols)


def resolve_symbols_in_run_v1(
    value: Any,
    symbols: Mapping[str, Any],
    *,
    path: str,
) -> Any:
    return resolve_symbol_references_v1(
        value,
        symbols,
        path=path,
    )


def bind_think_program_symbols_v1(
    program: Mapping[str, Any],
    *,
    initial_parameter_overrides: Any = None,
) -> Dict[str, Any]:
    """Bind the shared symbol grammar specifically over ThinkProgram.run."""
    p = overlay_initial_parameter_overrides_onto_program_v1(
        program,
        initial_parameter_overrides=initial_parameter_overrides,
    )

    reject_unknown_keys_v1(
        p,
        _ALLOWED_TOP_LEVEL_KEYS_V1,
        path="program",
    )

    if str(p.get("kind") or "") != THINK_PROGRAM_KIND_V1:
        raise ValueError(f"program.kind must be {THINK_PROGRAM_KIND_V1!r}")

    if str(p.get("surface_version") or "") != THINK_PROGRAM_SURFACE_VERSION_V1:
        raise ValueError(
            f"program.surface_version must be {THINK_PROGRAM_SURFACE_VERSION_V1!r}"
        )

    assert_dead_json(p, path="program")

    symbols = effective_symbols_v1(p)

    if "run" not in p:
        raise ValueError("program.run is required")

    run = resolve_symbols_in_run_v1(
        deepcopy_json(p["run"]),
        symbols,
        path="run",
    )

    assert_dead_json(run, path="resolved run")
    return run
