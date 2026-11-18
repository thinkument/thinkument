from __future__ import annotations

"""Canonical datum/micro fill contract.

Order for accepted runtime data:
    shape/requiredness -> activated semantic validators -> coercion -> revalidate
    -> strict dead-JSON membrane.
"""

from typing import Any, Dict, List, Mapping

from _thinkprogram._iomicrosTM.core.api_validation import DatumFillValidator
from _thinkprogram._iomicrosTM.core.micro_registry import get_micro_type_definition
from _thinkprogram._iomicrosTM.core.value_semantics import (
    DeadJSONError,
    assert_dead_json,
    is_blank_value,
    unbox_leaf,
)


def merge_macro_values(*values: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for value in values:
        if not isinstance(value, Mapping):
            continue
        for key, item in value.items():
            out[str(key)] = item
    return out


def _micro_specs(datum: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = datum.get("micros") or []
    try:
        values = list(raw)
    except TypeError:
        values = []
    return [item for item in values if isinstance(item, Mapping)]


def datum_required_micro_names(datum: Mapping[str, Any]) -> List[str]:
    micros = _micro_specs(datum)
    if not micros:
        return ["value"]
    return [
        str(micro.get("name") or "value")
        for micro in micros
        if micro.get("required", True) is not False
    ]


def datum_micro_names(datum: Mapping[str, Any]) -> List[str]:
    micros = _micro_specs(datum)
    if not micros:
        return ["value"]
    return [str(micro.get("name") or "value") for micro in micros]


def macro_micro_value(macro_value: Any, micro_name: str) -> Any:
    if isinstance(macro_value, Mapping):
        return unbox_leaf(macro_value.get(str(micro_name)))
    if str(micro_name) == "value":
        return unbox_leaf(macro_value)
    return None


def datum_fill_data_meets_its_structural_micros_shell(
    datum: Mapping[str, Any],
    macro_value: Any,
) -> bool:
    return all(
        not is_blank_value(macro_micro_value(macro_value, name))
        for name in datum_required_micro_names(datum)
    )


def build_datum_validator(
    datum: Mapping[str, Any],
    *,
    enforce_validator_legality: bool = True,
    enforce_known_micros: bool = False,
) -> DatumFillValidator:
    return DatumFillValidator(
        id=str(datum.get("id") or datum.get("datum_id") or ""),
        title=str(datum.get("title") or ""),
        micros=[dict(micro) for micro in _micro_specs(datum)],
        macro_validation_lambdas=datum.get("macro_validation_lambdas"),
        enforce_validator_legality=bool(enforce_validator_legality),
        enforce_known_micros=bool(enforce_known_micros),
    )


def parse_and_validate_macro_fill(
    *,
    datum: Mapping[str, Any],
    raw: Any,
    enforce_required_micros: bool = True,
    enforce_micro_lambdas: bool = True,
    enforce_macro_lambdas: bool = True,
) -> Any:
    validator = build_datum_validator(datum)
    validated = validator.parse_and_validate_fill(
        raw=raw,
        enforce_required_micros=bool(enforce_required_micros),
        enforce_micro_lambdas=bool(enforce_micro_lambdas),
        enforce_macro_lambdas=bool(enforce_macro_lambdas),
    )
    assert_dead_json(
        validated,
        path=f"validated[{str(datum.get('id') or datum.get('datum_id') or 'DATUM')}]",
    )
    return validated


def _micro_type_by_name_for_datum(datum: Mapping[str, Any]) -> Dict[str, str]:
    micros = _micro_specs(datum)
    if not micros:
        return {"value": "text"}
    return {
        str(micro.get("name") or "value"): (
            str(micro.get("type") or "text").strip().lower() or "text"
        )
        for micro in micros
    }


def _coerce_one_accepted_micro_value(
    *,
    datum_id: str,
    micro_name: str,
    micro_type: str,
    value: Any,
) -> Any:
    value = unbox_leaf(value)
    if value is None:
        return None

    try:
        definition = get_micro_type_definition(micro_type)
    except KeyError as exc:
        raise ValueError(
            f"Unknown micro type {micro_type!r} while coercing datum "
            f"{datum_id!r} micro {micro_name!r}"
        ) from exc

    try:
        coerced = definition.coerce(value) if callable(definition.coerce) else value
    except Exception as exc:
        raise ValueError(
            f"Could not coerce datum {datum_id!r} micro {micro_name!r} "
            f"as {micro_type!r}: {value!r}: {exc}"
        ) from exc

    allowed = tuple(definition.python_types or ())
    if coerced is not None and allowed and not isinstance(coerced, allowed):
        raise ValueError(
            f"Coercer for datum {datum_id!r} micro {micro_name!r} type "
            f"{micro_type!r} produced {type(coerced).__name__}; "
            f"expected {[item.__name__ for item in allowed]}"
        )

    assert_dead_json(
        coerced,
        path=f"coerced_accepted_fill[{datum_id}].{micro_name}",
    )
    return coerced


def coerce_accepted_macro_fill_for_datum(
    *,
    datum: Mapping[str, Any],
    accepted: Any,
    allow_unknown_keys: bool = True,
) -> Any:
    datum_id = str(datum.get("id") or datum.get("datum_id") or "DATUM")
    micro_types = _micro_type_by_name_for_datum(datum)

    if not isinstance(accepted, Mapping):
        if set(micro_types) == {"value"}:
            return _coerce_one_accepted_micro_value(
                datum_id=datum_id,
                micro_name="value",
                micro_type=micro_types["value"],
                value=accepted,
            )
        raise ValueError(
            f"Expected mapping accepted fill for datum {datum_id!r}; "
            f"got {type(accepted).__name__}"
        )

    extras = sorted(str(key) for key in accepted if str(key) not in micro_types)
    if extras and not allow_unknown_keys:
        raise ValueError(f"Unknown micros for datum {datum_id!r}: {extras}")

    out: Dict[str, Any] = {}
    for key_raw, value in accepted.items():
        key = str(key_raw)
        if key not in micro_types:
            out[key] = unbox_leaf(value)
            continue
        out[key] = _coerce_one_accepted_micro_value(
            datum_id=datum_id,
            micro_name=key,
            micro_type=micro_types[key],
            value=value,
        )

    assert_dead_json(out, path=f"coerced_accepted_fill[{datum_id}]")
    return out


def parse_validate_and_coerce_macro_fill(
    *,
    datum: Mapping[str, Any],
    raw: Any,
    enforce_required_micros: bool = True,
    enforce_micro_lambdas: bool = True,
    enforce_macro_lambdas: bool = True,
    revalidate_after_coercion: bool = True,
) -> Any:
    validator = build_datum_validator(datum)
    accepted = validator.parse_and_validate_fill(
        raw=raw,
        enforce_required_micros=bool(enforce_required_micros),
        enforce_micro_lambdas=bool(enforce_micro_lambdas),
        enforce_macro_lambdas=bool(enforce_macro_lambdas),
    )
    coerced = coerce_accepted_macro_fill_for_datum(datum=datum, accepted=accepted)

    if revalidate_after_coercion:
        coerced = validator.parse_and_validate_fill(
            raw=coerced,
            enforce_required_micros=bool(enforce_required_micros),
            enforce_micro_lambdas=bool(enforce_micro_lambdas),
            enforce_macro_lambdas=bool(enforce_macro_lambdas),
        )

    assert_dead_json(
        coerced,
        path=f"validated_coerced[{str(datum.get('id') or datum.get('datum_id') or 'DATUM')}]",
    )
    return coerced


__all__ = [
    "DeadJSONError",
    "assert_dead_json",
    "merge_macro_values",
    "unbox_leaf",
    "is_blank_value",
    "datum_required_micro_names",
    "datum_micro_names",
    "macro_micro_value",
    "datum_fill_data_meets_its_structural_micros_shell",
    "build_datum_validator",
    "parse_and_validate_macro_fill",
    "coerce_accepted_macro_fill_for_datum",
    "parse_validate_and_coerce_macro_fill",
]
