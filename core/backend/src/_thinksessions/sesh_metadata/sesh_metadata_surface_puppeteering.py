from __future__ import annotations

"""
Joint ThinkProgram / ThinkSession puppeteering core.

Both authoring surfaces use the same symbol grammar:

    symbols:
        symbol_name -> {
            "value": dead_json_default,
            "parametrize": bool,
        }

    puppeteering:
        parametrized_symbol_name -> dead_json_authored_value

One launch-time ``initial_parameter_overrides`` mapping may target several
symbol-bearing surfaces at once. The highest run façade uses that fact for:

    ThinkProgram P
    ThinkSession metadata SM

The lower session stack never sees these authoring controls. Session metadata
``symbols`` and ``puppeteering`` are consumed here and only the resolved
ordinary metadata body is passed downward.

Joint-domain law:

    Param(P, SM) = Param(P) union Param(SM)

An assignment is legal when at least one target surface exposes the name with
``parametrize=true``. If several surfaces expose it, the same assigned value is
applied independently to every such surface.

Overlay operations are shallow by symbol name. A structured symbol value is one
assigned value; it is never deep-merged with the old symbol value.
"""

import json
from collections.abc import Mapping
from typing import Any, Dict


PUPPETEERING_OVERLAY_KEY_V1 = "__puppeteering_overrides_v1__"
PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1 = "merge_onto"
PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1 = "take_over"

_ALLOWED_PUPPETEERING_OVERLAY_MODES_V1 = frozenset(
    {
        PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
        PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
    }
)
_ALLOWED_PUPPETEERING_OVERLAY_CONTROL_KEYS_V1 = frozenset(
    {
        "mode",
        "strict",
    }
)

SESSION_METADATA_AUTHORING_KEYS_V1 = frozenset(
    {
        "symbols",
        "puppeteering",
    }
)


def _require_mapping_v1(
    value: Any,
    *,
    path: str,
) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be mapping")
    return dict(value)


def _require_nonempty_name_v1(
    value: Any,
    *,
    path: str,
) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError(f"{path} must be non-empty string")
    return name


def _dead_json_copy_v1(
    value: Any,
    *,
    path: str,
) -> Any:
    try:
        encoded = json.dumps(value, sort_keys=True)
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} must be dead JSON") from exc


def _overlay_is_empty_v1(value: Any) -> bool:
    return value is None or (
        isinstance(value, Mapping)
        and not value
    )


def normalize_puppeteering_overlay_v1(
    initial_parameter_overrides: Any,
) -> Dict[str, Any]:
    """
    Normalize the one launch-time C container.

    Exact grammar:

        {
            "__puppeteering_overrides_v1__": {
                "mode": "merge_onto" | "take_over",
                "strict": bool,
            },
            "<symbol-name>": <dead JSON value>,
            ...
        }

    The control object is optional:

        mode   defaults to merge_onto
        strict defaults to True
    """
    if initial_parameter_overrides is None:
        initial_parameter_overrides = {}

    if not isinstance(initial_parameter_overrides, Mapping):
        raise ValueError("initial_parameter_overrides must be mapping")

    raw = dict(initial_parameter_overrides)
    control_raw = raw.pop(PUPPETEERING_OVERLAY_KEY_V1, {})

    if control_raw is None:
        control_raw = {}
    if not isinstance(control_raw, Mapping):
        raise ValueError(
            f"{PUPPETEERING_OVERLAY_KEY_V1} must be mapping"
        )

    control = dict(control_raw)
    unknown_control = (
        set(control)
        - _ALLOWED_PUPPETEERING_OVERLAY_CONTROL_KEYS_V1
    )
    if unknown_control:
        raise ValueError(
            "initial_parameter_overrides control has unknown keys: "
            f"{sorted(unknown_control)}"
        )

    mode = str(
        control.get(
            "mode",
            PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
        )
        or ""
    ).strip()
    if mode not in _ALLOWED_PUPPETEERING_OVERLAY_MODES_V1:
        raise ValueError(
            "initial_parameter_overrides control.mode must be one of "
            f"{sorted(_ALLOWED_PUPPETEERING_OVERLAY_MODES_V1)}"
        )

    strict = control.get("strict", True)
    if not isinstance(strict, bool):
        raise ValueError(
            "initial_parameter_overrides control.strict must be boolean"
        )

    values: Dict[str, Any] = {}
    for name_raw, value in raw.items():
        name = _require_nonempty_name_v1(
            name_raw,
            path="initial_parameter_overrides symbol name",
        )
        if name.startswith("$"):
            raise ValueError(
                "initial_parameter_overrides symbol name may not start "
                f"with '$': {name!r}"
            )

        values[name] = _dead_json_copy_v1(
            value,
            path=f"initial_parameter_overrides[{name!r}]",
        )

    return {
        "mode": mode,
        "strict": strict,
        "values": values,
    }


def symbol_name_sets_v1(
    surface: Mapping[str, Any],
    *,
    surface_path: str,
) -> tuple[set[str], set[str]]:
    """
    Return ``(all_declared_names, parametrized_names)`` for one surface.

    This validates the common symbol declaration grammar while remaining
    agnostic about the rest of the owning P or SM surface.
    """
    source = _require_mapping_v1(
        surface,
        path=surface_path,
    )

    symbols_raw = source.get("symbols", {})
    if symbols_raw is None:
        symbols_raw = {}
    if not isinstance(symbols_raw, Mapping):
        raise ValueError(f"{surface_path}.symbols must be mapping")

    all_names: set[str] = set()
    parametrized_names: set[str] = set()

    for name_raw, spec_raw in dict(symbols_raw).items():
        name = _require_nonempty_name_v1(
            name_raw,
            path=f"{surface_path} symbol name",
        )
        if name.startswith("$"):
            raise ValueError(
                f"{surface_path} symbol name may not start with '$': {name!r}"
            )
        if name == PUPPETEERING_OVERLAY_KEY_V1:
            raise ValueError(
                f"{surface_path} symbol name {name!r} is reserved for "
                "puppeteering overlay control"
            )

        spec = _require_mapping_v1(
            spec_raw,
            path=f"{surface_path}.symbols[{name!r}]",
        )
        if "value" not in spec:
            raise ValueError(
                f"{surface_path}.symbols[{name!r}] must contain value"
            )
        _dead_json_copy_v1(
            spec["value"],
            path=f"{surface_path}.symbols[{name!r}].value",
        )

        parametrized = spec.get("parametrize", False)
        if not isinstance(parametrized, bool):
            raise ValueError(
                f"{surface_path}.symbols[{name!r}].parametrize "
                "must be boolean"
            )

        all_names.add(name)
        if parametrized:
            parametrized_names.add(name)

    return all_names, parametrized_names


def _apply_normalized_overlay_v1(
    surface: Mapping[str, Any],
    *,
    normalized: Mapping[str, Any],
    accepted_values: Mapping[str, Any],
    parametrized_names: set[str],
    surface_path: str,
) -> Dict[str, Any]:
    source = _dead_json_copy_v1(
        _require_mapping_v1(surface, path=surface_path),
        path=surface_path,
    )

    authored_raw = source.get("puppeteering", {})
    if authored_raw is None:
        authored_raw = {}
    if not isinstance(authored_raw, Mapping):
        raise ValueError(f"{surface_path}.puppeteering must be mapping")

    mode = str(normalized["mode"])
    if mode == PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1:
        final_puppeteering: Dict[str, Any] = {}
    elif mode == PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1:
        final_puppeteering = _dead_json_copy_v1(
            dict(authored_raw),
            path=f"{surface_path}.puppeteering",
        )
    else:
        raise AssertionError(f"unreachable puppeteering mode {mode!r}")

    for name, value in accepted_values.items():
        if name not in parametrized_names:
            continue
        final_puppeteering[name] = _dead_json_copy_v1(
            value,
            path=f"initial_parameter_overrides[{name!r}]",
        )

    source["puppeteering"] = final_puppeteering
    return source


def overlay_puppeteering_onto_symbol_surface_v1(
    surface: Mapping[str, Any],
    *,
    initial_parameter_overrides: Any = None,
    surface_path: str = "surface",
) -> Dict[str, Any]:
    """
    Apply C to one symbol-bearing surface.

    This is the standalone form used by ThinkProgram lowering. Joint P+SM
    launch routing uses ``route_puppeteering_overlay_to_symbol_surfaces_v1``.
    """
    source = _require_mapping_v1(surface, path=surface_path)
    if _overlay_is_empty_v1(initial_parameter_overrides):
        return dict(source)

    normalized = normalize_puppeteering_overlay_v1(
        initial_parameter_overrides
    )
    all_names, parametrized_names = symbol_name_sets_v1(
        source,
        surface_path=surface_path,
    )
    values = dict(normalized["values"])

    unknown = sorted(set(values) - all_names)
    unparametrized = sorted(
        set(values)
        - parametrized_names
        - set(unknown)
    )

    if normalized["strict"]:
        if unknown:
            raise ValueError(
                "initial_parameter_overrides references unknown symbol(s): "
                f"{unknown}"
            )
        if unparametrized:
            raise ValueError(
                "initial_parameter_overrides references symbol(s) that are "
                f"not parametrized: {unparametrized}"
            )
        accepted = values
    else:
        accepted = {
            name: value
            for name, value in values.items()
            if name in parametrized_names
        }

    return _apply_normalized_overlay_v1(
        source,
        normalized=normalized,
        accepted_values=accepted,
        parametrized_names=parametrized_names,
        surface_path=surface_path,
    )


def route_puppeteering_overlay_to_symbol_surfaces_v1(
    *,
    surfaces: Mapping[str, Mapping[str, Any]],
    initial_parameter_overrides: Any,
) -> Dict[str, Dict[str, Any]]:
    """
    Apply one C container across several symbol-bearing authoring surfaces.

    Strictness is evaluated once against the union of those surfaces'
    parametrized symbol interfaces.
    """
    if not isinstance(surfaces, Mapping) or not surfaces:
        raise ValueError("surfaces must be a non-empty mapping")

    normalized_surfaces = {
        str(name): _require_mapping_v1(
            surface,
            path=str(name),
        )
        for name, surface in surfaces.items()
    }

    if _overlay_is_empty_v1(initial_parameter_overrides):
        return {
            name: dict(surface)
            for name, surface in normalized_surfaces.items()
        }

    normalized = normalize_puppeteering_overlay_v1(
        initial_parameter_overrides
    )

    names_by_surface: Dict[str, tuple[set[str], set[str]]] = {}
    all_names: set[str] = set()
    parametrized_names: set[str] = set()

    for surface_name, surface in normalized_surfaces.items():
        name_sets = symbol_name_sets_v1(
            surface,
            surface_path=surface_name,
        )
        names_by_surface[surface_name] = name_sets
        all_names.update(name_sets[0])
        parametrized_names.update(name_sets[1])

    values = dict(normalized["values"])
    unknown = sorted(set(values) - all_names)
    unparametrized = sorted(
        set(values)
        - parametrized_names
        - set(unknown)
    )

    if normalized["strict"]:
        if unknown:
            raise ValueError(
                "joint initial_parameter_overrides references unknown "
                f"symbol(s): {unknown}"
            )
        if unparametrized:
            raise ValueError(
                "joint initial_parameter_overrides references symbol(s) "
                "that are not parametrized on any target surface: "
                f"{unparametrized}"
            )
        accepted = values
    else:
        accepted = {
            name: value
            for name, value in values.items()
            if name in parametrized_names
        }

    return {
        surface_name: _apply_normalized_overlay_v1(
            surface,
            normalized=normalized,
            accepted_values=accepted,
            parametrized_names=names_by_surface[surface_name][1],
            surface_path=surface_name,
        )
        for surface_name, surface in normalized_surfaces.items()
    }


def effective_symbol_values_v1(
    surface: Mapping[str, Any],
    *,
    surface_path: str,
) -> Dict[str, Any]:
    """
    Resolve declared defaults plus the surface's authored/effective puppet pocket.
    """
    source = _require_mapping_v1(surface, path=surface_path)
    _all_names, parametrized_names = symbol_name_sets_v1(
        source,
        surface_path=surface_path,
    )

    symbols_raw = source.get("symbols", {})
    symbols_raw = {} if symbols_raw is None else symbols_raw

    out: Dict[str, Any] = {}
    for name_raw, spec_raw in dict(symbols_raw).items():
        name = str(name_raw)
        spec = dict(spec_raw)
        out[name] = _dead_json_copy_v1(
            spec["value"],
            path=f"{surface_path}.symbols[{name!r}].value",
        )

    puppeteering_raw = source.get("puppeteering", {})
    if puppeteering_raw is None:
        puppeteering_raw = {}
    if not isinstance(puppeteering_raw, Mapping):
        raise ValueError(f"{surface_path}.puppeteering must be mapping")

    for name_raw, replacement in dict(puppeteering_raw).items():
        name = _require_nonempty_name_v1(
            name_raw,
            path=f"{surface_path}.puppeteering key",
        )
        if name not in out:
            raise ValueError(
                f"{surface_path}.puppeteering references unknown "
                f"symbol {name!r}"
            )
        if name not in parametrized_names:
            raise ValueError(
                f"{surface_path} symbol {name!r} is not parametrized"
            )

        out[name] = _dead_json_copy_v1(
            replacement,
            path=f"{surface_path}.puppeteering[{name!r}]",
        )

    return out


def lookup_symbol_path_v1(
    ref: str,
    symbols: Mapping[str, Any],
) -> Any:
    if not ref.startswith("$"):
        return ref

    path = ref[1:]
    if not path:
        raise ValueError("empty symbol reference '$'")

    parts = path.split(".")
    candidate_names = sorted(
        symbols.keys(),
        key=lambda value: len(str(value).split(".")),
        reverse=True,
    )

    for name in candidate_names:
        name_parts = str(name).split(".")
        if parts[: len(name_parts)] != name_parts:
            continue

        value: Any = _dead_json_copy_v1(
            symbols[name],
            path=f"symbol {name!r}",
        )

        for segment in parts[len(name_parts) :]:
            if isinstance(value, Mapping) and segment in value:
                value = value[segment]
                continue

            if isinstance(value, list) and segment.isdigit():
                index = int(segment)
                if 0 <= index < len(value):
                    value = value[index]
                    continue

            raise ValueError(
                f"symbol reference {ref!r} resolved symbol {name!r} "
                f"but missing nested segment {segment!r}"
            )

        return _dead_json_copy_v1(
            value,
            path=f"symbol reference {ref!r}",
        )

    raise ValueError(f"unresolved symbol reference {ref!r}")


def resolve_symbol_references_v1(
    value: Any,
    symbols: Mapping[str, Any],
    *,
    path: str,
) -> Any:
    if isinstance(value, str):
        if value.startswith("$"):
            return lookup_symbol_path_v1(value, symbols)
        if "$" in value:
            raise ValueError(
                f"{path} looks like interpolation; v1 supports exact refs only"
            )
        return value

    if isinstance(value, list):
        return [
            resolve_symbol_references_v1(
                child,
                symbols,
                path=f"{path}[{index}]",
            )
            for index, child in enumerate(value)
        ]

    if isinstance(value, Mapping):
        return {
            str(key): resolve_symbol_references_v1(
                child,
                symbols,
                path=f"{path}.{key}",
            )
            for key, child in value.items()
        }

    return value


def bind_session_metadata_symbols_v1(
    session_metadata: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Resolve authored SM symbols and remove SM authoring-only control pockets.

    Input:

        {
            "symbols": {...},
            "puppeteering": {...},
            "roles": {...},
            "manual_io": {...},
            ...
        }

    Output passed below the highest façade:

        {
            "roles": {...resolved...},
            "manual_io": {...resolved...},
            ...
        }
    """
    source = _require_mapping_v1(
        session_metadata,
        path="session_metadata",
    )
    symbols = effective_symbol_values_v1(
        source,
        surface_path="session_metadata",
    )

    body = {
        str(key): value
        for key, value in source.items()
        if key not in SESSION_METADATA_AUTHORING_KEYS_V1
    }
    resolved = resolve_symbol_references_v1(
        body,
        symbols,
        path="session_metadata",
    )
    return _dead_json_copy_v1(
        resolved,
        path="resolved session_metadata",
    )


__all__ = [
    "PUPPETEERING_OVERLAY_KEY_V1",
    "PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1",
    "PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1",
    "SESSION_METADATA_AUTHORING_KEYS_V1",
    "bind_session_metadata_symbols_v1",
    "effective_symbol_values_v1",
    "lookup_symbol_path_v1",
    "normalize_puppeteering_overlay_v1",
    "overlay_puppeteering_onto_symbol_surface_v1",
    "resolve_symbol_references_v1",
    "route_puppeteering_overlay_to_symbol_surfaces_v1",
    "symbol_name_sets_v1",
]
