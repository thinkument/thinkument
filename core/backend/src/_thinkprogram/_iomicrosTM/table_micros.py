from __future__ import annotations

"""Canonical public data-atom capability sheet.

This table is intentionally the single place that grows the canonical input
surface.  UI controls are allowed to be many-to-one over these data atoms.
"""

from typing import Any, Dict, Tuple

from _thinkprogram._iomicrosTM.core.micro_registry import (
    MICRO_TYPES,
    MicroTypeDefinition,
    ValidatorPolicy,
    validate_micro_registry_integrity,
)
from _thinkprogram._iomicrosTM.tiny_coercers import (
    coerce_bool,
    coerce_integer,
    coerce_number,
    coerce_object_json,
    coerce_str,
    coerce_str_list,
)

PATH = "_thinkprogram._iomicrosTM.validators"


def _vp(
    module: str,
    name: str,
    *,
    hard: bool = False,
    arg_map: Dict[str, str] | None = None,
) -> ValidatorPolicy:
    return ValidatorPolicy(
        path=f"{PATH}.{module}:{name}",
        mandatory_enforced=hard,
        arg_map=dict(arg_map or {}),
        guidance_channel="local_guidance",
    )


_TEXT_VALIDATORS: Tuple[ValidatorPolicy, ...] = (
    _vp("text", "is_nonempty_str"),
    _vp("text", "min_words", arg_map={"min_words": "min_words"}),
    _vp("text", "max_words", arg_map={"max_words": "max_words"}),
    _vp("text", "min_length", hard=True, arg_map={"min_length": "minLength"}),
    _vp("text", "max_length", hard=True, arg_map={"max_length": "maxLength"}),
    _vp("text", "pattern", hard=True, arg_map={"pattern": "pattern"}),
)

_INTEGER_VALIDATORS: Tuple[ValidatorPolicy, ...] = (
    _vp("number", "is_integer", hard=True),
    _vp("number", "is_positive_int", hard=True),
    _vp("number", "min_number", hard=True, arg_map={"min_value": "minimum"}),
    _vp("number", "max_number", hard=True, arg_map={"max_value": "maximum"}),
)

_NUMBER_VALIDATORS: Tuple[ValidatorPolicy, ...] = (
    _vp("number", "is_finite_number", hard=True),
    _vp("number", "is_positive_int", hard=True),
    _vp("number", "min_number", hard=True, arg_map={"min_value": "minimum"}),
    _vp("number", "max_number", hard=True, arg_map={"max_value": "maximum"}),
)

_CODE_VALIDATORS: Tuple[ValidatorPolicy, ...] = (
    _vp("code", "is_nonempty_code"),
    _vp("code", "min_code_lines", arg_map={"min_lines": "min_lines"}),
    _vp("code", "max_code_lines", arg_map={"max_lines": "max_lines"}),
)

_MULTI_SELECT_VALIDATORS: Tuple[ValidatorPolicy, ...] = (
    _vp("choice", "all_in_allowed", hard=True, arg_map={"options": "items.enum"}),
    _vp("collection", "min_items", hard=True, arg_map={"min_items": "minItems"}),
    _vp("collection", "max_items", hard=True, arg_map={"max_items": "maxItems"}),
    _vp("collection", "unique_items", hard=True),
)


_IMAGE_URL_VALIDATORS: Tuple[ValidatorPolicy, ...] = (
    _vp("image", "image_url"),
    _vp(
        "image",
        "image_url_has_allowed_extension",
        arg_map={"allowed_extensions": "extensions"},
    ),
)

_IMAGE_FILEPATH_VALIDATORS: Tuple[ValidatorPolicy, ...] = (
    _vp("image", "image_filepath"),
)


def _float_cast(value: Any) -> float:
    out = coerce_number(value)
    if out is None:
        return None  # type: ignore[return-value]
    return float(out)


def _int_cast_from_number(value: Any) -> int:
    out = coerce_number(value)
    if out is None:
        return None  # type: ignore[return-value]
    if isinstance(out, int):
        return out
    if float(out).is_integer():
        return int(out)
    raise ValueError(f"number {out!r} is not integral")


def _json_object_cast(value: Any) -> dict:
    out = coerce_object_json(value)
    if out is None:
        return None  # type: ignore[return-value]
    if not isinstance(out, dict):
        raise ValueError("value is not a JSON object")
    return out


def _json_array_cast(value: Any) -> list:
    out = coerce_object_json(value)
    if out is None:
        return None  # type: ignore[return-value]
    if not isinstance(out, list):
        raise ValueError("value is not a JSON array")
    return out


_STRING_DESTS = (
    "text",
    "textarea",
    "slug",
    "email",
    "url",
    "date",
    "time",
    "datetime",
    "code",
    "latex_math",
    "image_url",
    "image_filepath",
    "file_url",
    "file_filepath",
    "select",
    "number",
    "integer",
    "object-json",
)


my_micro_table: Dict[str, MicroTypeDefinition] = {
    "text": MicroTypeDefinition(
        name="text",
        description="Single-line freeform Unicode text.",
        json_schema={"type": "string"},
        modality="text",
        validators=_TEXT_VALIDATORS,
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=tuple(x for x in _STRING_DESTS if x != "text"),
        python_casts={str: coerce_str},
    ),
    "textarea": MicroTypeDefinition(
        name="textarea",
        description="Multiline freeform Unicode text; same canonical value as text.",
        json_schema={"type": "string"},
        modality="textarea",
        validators=_TEXT_VALIDATORS,
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=tuple(x for x in _STRING_DESTS if x != "textarea"),
        python_casts={str: coerce_str},
    ),
    "slug": MicroTypeDefinition(
        name="slug",
        description="Identifier/URL slug string; concrete format is author validator-defined.",
        json_schema={"type": "string"},
        modality="text",
        validators=(_vp("text", "pattern", hard=True, arg_map={"pattern": "pattern"}),),
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "integer": MicroTypeDefinition(
        name="integer",
        description="Whole numeric value; bool is never an integer.",
        json_schema={"type": "integer"},
        modality="number",
        validators=_INTEGER_VALIDATORS,
        python_types=(int,),
        coerce=coerce_integer,
        coerce_to_micro_types=("number", "text", "textarea", "object-json"),
        python_casts={int: coerce_integer, float: _float_cast},
    ),
    "number": MicroTypeDefinition(
        name="number",
        description="Finite integer or floating-point numeric value; bool excluded.",
        json_schema={"type": "number"},
        modality="number",
        validators=_NUMBER_VALIDATORS,
        python_types=(int, float),
        coerce=coerce_number,
        coerce_to_micro_types=("integer", "text", "textarea", "object-json"),
        python_casts={int: _int_cast_from_number, float: _float_cast},
    ),
    "boolean": MicroTypeDefinition(
        name="boolean",
        description="Canonical boolean value.",
        json_schema={"type": "boolean"},
        modality="boolean",
        validators=(_vp("boolean", "is_boolean", hard=True),),
        python_types=(bool,),
        coerce=coerce_bool,
        coerce_to_micro_types=("checkbox", "text", "textarea", "object-json"),
        python_casts={bool: coerce_bool},
    ),
    "checkbox": MicroTypeDefinition(
        name="checkbox",
        description="Checkbox renderer variant of canonical boolean semantics.",
        json_schema={"type": "boolean"},
        modality="checkbox",
        validators=(_vp("boolean", "is_boolean", hard=True),),
        python_types=(bool,),
        coerce=coerce_bool,
        coerce_to_micro_types=("boolean", "text", "textarea", "object-json"),
        python_casts={bool: coerce_bool},
    ),
    "select": MicroTypeDefinition(
        name="select",
        description="One string value selected from an authored option set.",
        json_schema={"type": "string"},
        modality="select",
        validators=(_vp("choice", "in_allowed", hard=True, arg_map={"options": "enum"}),),
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "multi_select": MicroTypeDefinition(
        name="multi_select",
        description="Zero or more string option values.",
        json_schema={"type": "array", "items": {"type": "string"}},
        modality="multi_select",
        validators=_MULTI_SELECT_VALIDATORS,
        python_types=(list,),
        coerce=coerce_str_list,
        coerce_to_micro_types=("json_array", "object-json"),
        python_casts={list: coerce_str_list},
    ),
    "email": MicroTypeDefinition(
        name="email",
        description="Email address string; syntax validation does not prove delivery.",
        json_schema={"type": "string", "format": "email"},
        modality="email",
        validators=(_vp("email", "is_basic_email"),),
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "url": MicroTypeDefinition(
        name="url",
        description="Credential-free absolute HTTP(S) URL.",
        json_schema={"type": "string", "format": "uri"},
        modality="url",
        validators=(_vp("url", "is_http_url"),),
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "date": MicroTypeDefinition(
        name="date",
        description="ISO-8601 calendar date string YYYY-MM-DD.",
        json_schema={"type": "string", "format": "date"},
        modality="date",
        validators=(
            _vp("date", "is_iso_date"),
            _vp("date", "min_date", arg_map={"min_date": "min_date"}),
            _vp("date", "max_date", arg_map={"max_date": "max_date"}),
        ),
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "time": MicroTypeDefinition(
        name="time",
        description="ISO-8601 local time string.",
        json_schema={"type": "string", "format": "time"},
        modality="time",
        validators=(_vp("date", "is_iso_time"),),
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "datetime": MicroTypeDefinition(
        name="datetime",
        description="ISO-8601 datetime string with T separator and optional offset.",
        json_schema={"type": "string", "format": "date-time"},
        modality="datetime",
        validators=(_vp("date", "is_iso_datetime"),),
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "code": MicroTypeDefinition(
        name="code",
        description="Code snippet string; language semantics are outside this atom layer.",
        json_schema={"type": "string"},
        modality="code",
        validators=_CODE_VALIDATORS,
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "latex_math": MicroTypeDefinition(
        name="latex_math",
        description="LaTeX math fragment string; full TeX parsing is intentionally external.",
        json_schema={"type": "string"},
        modality="latex_math",
        validators=(_vp("latex_math", "is_nonempty_latex"),),
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("text", "textarea", "code", "object-json"),
        python_casts={str: coerce_str},
    ),
    "image_url": MicroTypeDefinition(
        name="image_url",
        description="HTTP(S) reference to a concrete image resource.",
        json_schema={"type": "string", "format": "uri"},
        modality="image_url",
        validators=_IMAGE_URL_VALIDATORS,
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("url", "file_url", "text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "image_filepath": MicroTypeDefinition(
        name="image_filepath",
        description="Local image path reference; file existence is not checked here.",
        json_schema={"type": "string"},
        modality="image_filepath",
        validators=_IMAGE_FILEPATH_VALIDATORS,
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("file_filepath", "text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "file_url": MicroTypeDefinition(
        name="file_url",
        description="HTTP(S) reference to a remote file/resource.",
        json_schema={"type": "string", "format": "uri"},
        modality="file_url",
        validators=(_vp("url", "is_http_url"),),
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("url", "text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "file_filepath": MicroTypeDefinition(
        name="file_filepath",
        description="Local file path reference; file existence is intentionally external.",
        json_schema={"type": "string"},
        modality="file_filepath",
        validators=(
            _vp("file", "local_filepath"),
            _vp("file", "filepath_has_allowed_extension", arg_map={"allowed_extensions": "extensions"}),
        ),
        python_types=(str,),
        coerce=coerce_str,
        coerce_to_micro_types=("text", "textarea", "object-json"),
        python_casts={str: coerce_str},
    ),
    "json_object": MicroTypeDefinition(
        name="json_object",
        description="Strict dead-JSON object with string keys.",
        json_schema={"type": "object"},
        modality="json_object",
        validators=(_vp("object_json", "is_json_object", hard=True),),
        python_types=(dict,),
        coerce=_json_object_cast,
        coerce_to_micro_types=("object-json", "text", "textarea"),
        python_casts={dict: _json_object_cast},
    ),
    "json_array": MicroTypeDefinition(
        name="json_array",
        description="Strict dead-JSON array.",
        json_schema={"type": "array"},
        modality="json_array",
        validators=(_vp("object_json", "is_json_array", hard=True),),
        python_types=(list,),
        coerce=_json_array_cast,
        coerce_to_micro_types=("object-json", "text", "textarea"),
        python_casts={list: _json_array_cast},
    ),
    "object-json": MicroTypeDefinition(
        name="object-json",
        description="Any strict dead-JSON value after explicit supported object normalization.",
        json_schema={},
        modality="object-json",
        validators=(_vp("object_json", "is_dead_json", hard=True),),
        python_types=(dict, list, str, int, float, bool, type(None)),
        coerce=coerce_object_json,
        coerce_to_micro_types=("json_object", "json_array", "text", "textarea", "code"),
        python_casts={dict: _json_object_cast, list: _json_array_cast},
    ),
    "hidden-pause": MicroTypeDefinition(
        name="hidden-pause",
        description="Invisible lifecycle control represented canonically as bool.",
        json_schema={"type": "boolean"},
        requiredness_policy="auto_satisfied",
        visibility_policy="hidden",
        modality="hidden",
        validators=(),
        python_types=(bool,),
        coerce=coerce_bool,
        coerce_to_micro_types=("boolean", "checkbox", "object-json"),
        python_casts={bool: coerce_bool},
    ),
}

MICRO_TYPES.update(my_micro_table)
validate_micro_registry_integrity()


__all__ = [
    "MICRO_TYPES",
    "MicroTypeDefinition",
    "ValidatorPolicy",
    "my_micro_table",
    "_TEXT_VALIDATORS",
    "_INTEGER_VALIDATORS",
    "_NUMBER_VALIDATORS",
    "_CODE_VALIDATORS",
    "_MULTI_SELECT_VALIDATORS",
    "_IMAGE_URL_VALIDATORS",
    "_IMAGE_FILEPATH_VALIDATORS",
]