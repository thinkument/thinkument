from __future__ import annotations

"""Deterministic machine-readable publication catalog for public micros."""

import inspect
import math
from typing import Any, Callable, Dict, Mapping

import _thinkprogram._iomicrosTM.table_micros  # noqa: F401
import _thinkprogram._iomicrosTM.validators  # noqa: F401
from _thinkprogram._iomicrosTM.core.micro_registry import (
    get_micro_type_definition,
    list_public_micro_types,
)
from _thinkprogram._iomicrosTM.core.micro_validator_registry import all_validators, get_callable_by_path
from _thinkprogram._iomicrosTM.core.value_semantics import assert_dead_json
from _thinkprogram._iomicrosTM.validators import datum as datum_validators

CATALOG_SCHEMA = "thinkument.micro-publication-catalog/v2"


def _callable_path(fn: Callable[..., Any] | None) -> str | None:
    if fn is None:
        return None
    module = getattr(fn, "__module__", None)
    name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None)
    if not module or not name or "<locals>" in name:
        raise ValueError(f"callable lacks stable import path: {fn!r}")
    return f"{module}:{name}"


def _type_path(py_type: type) -> str:
    return f"{py_type.__module__}:{py_type.__qualname__}"


def _encode_python_only(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        if math.isnan(value):
            tag = "nan"
        elif value > 0:
            tag = "inf"
        else:
            tag = "-inf"
        return {"$python": "float", "value": tag}
    if isinstance(value, tuple):
        return {"$python": "tuple", "items": [_encode_python_only(v) for v in value]}
    if isinstance(value, list):
        return {"$python": "list", "items": [_encode_python_only(v) for v in value]}
    if isinstance(value, dict):
        return {
            "$python": "mapping",
            "items": [
                [_encode_python_only(key), _encode_python_only(item)]
                for key, item in value.items()
            ],
        }
    if isinstance(value, type):
        return {"$python": "type", "path": _type_path(value)}
    if callable(value):
        return {"$python": "callable", "path": _callable_path(value)}
    return {
        "$python": "repr",
        "type": _type_path(type(value)),
        "repr": repr(value),
    }


def encode_python_example(value: Any) -> Any:
    """Encode any example without reserving keys inside legitimate JSON data."""
    try:
        assert_dead_json(value, path="example")
    except Exception:
        return {"$example": "python", "value": _encode_python_only(value)}
    return {"$example": "json", "value": value}


def _decode_python_only(value: Any) -> Any:
    if not isinstance(value, dict) or "$python" not in value:
        return value
    kind = value.get("$python")
    if kind == "float":
        tag = value.get("value")
        return {"nan": float("nan"), "inf": float("inf"), "-inf": float("-inf")}[tag]
    if kind == "tuple":
        return tuple(_decode_python_only(v) for v in value.get("items") or [])
    if kind == "list":
        return [_decode_python_only(v) for v in value.get("items") or []]
    if kind == "mapping":
        return {
            _decode_python_only(pair[0]): _decode_python_only(pair[1])
            for pair in value.get("items") or []
        }
    raise ValueError(f"catalog example tag {kind!r} is not runtime-decodable")


def decode_python_example(value: Any) -> Any:
    if not isinstance(value, dict) or set(value) != {"$example", "value"}:
        raise ValueError("invalid encoded example envelope")
    kind = value.get("$example")
    if kind == "json":
        return value.get("value")
    if kind == "python":
        return _decode_python_only(value.get("value"))
    raise ValueError(f"unknown example encoding {kind!r}")

def _jsonish(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _jsonish(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_jsonish(item) for item in value]
    if isinstance(value, type):
        return {"python_type": _type_path(value)}
    if callable(value):
        return {"callable": _callable_path(value)}
    assert_dead_json(value)
    return value


def build_micro_publication_catalog() -> Dict[str, Any]:
    registered: Dict[str, Any] = {}
    for meta in all_validators():
        module_name, validator_name = meta.dotted_path.split(":", 1)
        guidance_path = f"{module_name}:{validator_name}_guidance"
        validator_fn = get_callable_by_path(meta.dotted_path)
        guidance_fn = get_callable_by_path(guidance_path)
        combos = []
        for combo in meta.arg_combos:
            guidance = guidance_fn(**dict(combo.args))
            combos.append(
                {
                    "args": _jsonish(combo.args),
                    "modality": combo.modality,
                    "valid_examples": [encode_python_example(v) for v in combo.valid_examples],
                    "invalid_examples": [encode_python_example(v) for v in combo.invalid_examples],
                    "guidance": _jsonish(guidance),
                }
            )
        registered[meta.dotted_path] = {
            "path": meta.dotted_path,
            "description": meta.description,
            "signature": str(inspect.signature(validator_fn)),
            "guidance_path": guidance_path,
            "argument_combinations": combos,
        }

    micros: Dict[str, Any] = {}
    for name in list_public_micro_types():
        definition = get_micro_type_definition(name)
        if callable(definition.json_schema):
            schema_record: Any = {"callable": _callable_path(definition.json_schema)}
        else:
            schema_record = _jsonish(definition.json_schema)
        micros[name] = {
            "name": definition.name,
            "description": definition.description,
            "json_schema": schema_record,
            "requiredness_policy": definition.requiredness_policy,
            "visibility_policy": definition.visibility_policy,
            "modality": definition.modality,
            "validator_modalities": sorted(set(definition.validator_modalities or ())),
            "validators": [
                {
                    "path": policy.path,
                    "mandatory_enforced": bool(policy.mandatory_enforced),
                    "arg_map": _jsonish(policy.arg_map),
                    "guidance_channel": policy.guidance_channel,
                }
                for policy in sorted(definition.validators, key=lambda item: item.path)
            ],
            "python_types": [_type_path(t) for t in definition.python_types],
            "coercer": _callable_path(definition.coerce),
            "coerce_to_micro_types": sorted(set(definition.coerce_to_micro_types or ())),
            "python_casts": [
                {"python_type": _type_path(py_type), "caster": _callable_path(caster)}
                for py_type, caster in sorted(
                    dict(definition.python_casts or {}).items(),
                    key=lambda pair: _type_path(pair[0]),
                )
            ],
        }

    macro_validators: Dict[str, Any] = {}
    for validator_name, fn in inspect.getmembers(datum_validators, inspect.isfunction):
        if validator_name.startswith("_") or fn.__module__ != datum_validators.__name__:
            continue
        path = f"{datum_validators.__name__}:{validator_name}"
        macro_validators[path] = {
            "path": path,
            "signature": str(inspect.signature(fn)),
            "description": inspect.getdoc(fn) or "",
        }

    catalog = {
        "schema": CATALOG_SCHEMA,
        "micros": micros,
        "registered_validators": dict(sorted(registered.items())),
        "macro_validators": dict(sorted(macro_validators.items())),
    }
    assert_dead_json(catalog, path="micro_publication_catalog")
    return catalog


__all__ = [
    "CATALOG_SCHEMA",
    "build_micro_publication_catalog",
    "decode_python_example",
    "encode_python_example",
]
