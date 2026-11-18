from __future__ import annotations

"""
Central registry for app-owned session_metadata pockets.

This registry lets side projects/apps extend the public session metadata surface
without changing engine keys or core machinery.

The engine-owned stable keys remain normal Python functions/surfaces, for example:

    roles
    role_mismatch_policy
    manual_io
    session_storage

Apps may register additional top-level pockets at startup:

    SessionMetadataSurfaceRegistry.register_pocket(
        key="grading",
        schema={...},
    )

The registered pocket schema must be inert JSON-safe metadata. It may describe
validation expectations, docs, labels, field shapes, examples, defaults, etc.
It may not contain callables or runtime behavior.

This file intentionally does not validate arbitrary business data deeply. It
validates the extension declaration itself and offers a small optional validator
for common object-shaped pocket values.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping


CORE_SESSION_METADATA_KEYS = frozenset(
    {
        "roles",
        "role_mismatch_policy",
        "manual_io",
        "session_storage",
    }
)


JSON_PRIMITIVE_TYPES = (str, int, float, bool, type(None))


ALLOWED_FIELD_TYPES = frozenset(
    {
        "any",
        "object",
        "array",
        "string",
        "number",
        "integer",
        "boolean",
        "null",
    }
)


def _is_json_safe(value: Any) -> bool:
    if isinstance(value, JSON_PRIMITIVE_TYPES):
        return True

    if isinstance(value, list):
        return all(_is_json_safe(item) for item in value)

    if isinstance(value, tuple):
        return all(_is_json_safe(item) for item in value)

    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_safe(item)
            for key, item in value.items()
        )

    return False


def _reject_callables_deep(value: Any, *, path: str) -> None:
    if callable(value):
        raise TypeError(f"{path} may not contain a live callable")

    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_callables_deep(item, path=f"{path}.{key}")

    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_callables_deep(item, path=f"{path}[{index}]")


def _require_json_safe(value: Any, *, path: str) -> None:
    if not _is_json_safe(value):
        raise TypeError(f"{path} must be JSON-safe inert metadata")


def _coerce_string_list(value: Any, *, path: str) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if not isinstance(value, list):
        raise TypeError(f"{path} must be a string or list of strings")

    out: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"{path}[{index}] must be a string")
        if item not in out:
            out.append(item)
    return out


def _validate_field_schema(
    field_name: str,
    field_schema: Any,
    *,
    path: str,
) -> Dict[str, Any]:
    if not isinstance(field_schema, Mapping):
        raise TypeError(f"{path} must be a mapping")

    field = dict(field_schema)

    unknown = set(field) - {
        "type",
        "required",
        "label",
        "description",
        "default",
        "enum",
        "items",
        "fields",
        "required_fields",
        "additional_keys",
        "additional_values",
        "examples",
    }

    if unknown:
        raise KeyError(f"{path} has unknown key(s): {sorted(unknown)}")

    typ = field.get("type", "any")
    if not isinstance(typ, str):
        raise TypeError(f"{path}.type must be a string")
    if typ not in ALLOWED_FIELD_TYPES:
        raise ValueError(
            f"{path}.type must be one of {sorted(ALLOWED_FIELD_TYPES)}; got {typ!r}"
        )

    if "required" in field and not isinstance(field["required"], bool):
        raise TypeError(f"{path}.required must be a boolean")

    if "enum" in field:
        if not isinstance(field["enum"], list) or not field["enum"]:
            raise TypeError(f"{path}.enum must be a non-empty list")
        _require_json_safe(field["enum"], path=f"{path}.enum")

    if "default" in field:
        _require_json_safe(field["default"], path=f"{path}.default")

    if "examples" in field:
        if not isinstance(field["examples"], list):
            raise TypeError(f"{path}.examples must be a list")
        _require_json_safe(field["examples"], path=f"{path}.examples")

    if "items" in field:
        if typ != "array":
            raise ValueError(f"{path}.items is only valid when type='array'")
        field["items"] = _validate_field_schema(
            f"{field_name}[]",
            field["items"],
            path=f"{path}.items",
        )

    if "fields" in field:
        if typ != "object":
            raise ValueError(f"{path}.fields is only valid when type='object'")
        if not isinstance(field["fields"], Mapping):
            raise TypeError(f"{path}.fields must be a mapping")

        field["fields"] = {
            str(child_name): _validate_field_schema(
                str(child_name),
                child_schema,
                path=f"{path}.fields.{child_name}",
            )
            for child_name, child_schema in field["fields"].items()
        }

        explicit_required = _coerce_string_list(
            field.get("required_fields"),
            path=f"{path}.required_fields",
        )
        required_from_children = [
            child_name
            for child_name, child_schema in field["fields"].items()
            if child_schema.get("required") is True
        ]

        required_fields: list[str] = []
        for child_name in [*explicit_required, *required_from_children]:
            if child_name not in field["fields"]:
                raise KeyError(
                    f"{path}.required_fields references undeclared field "
                    f"{child_name!r}"
                )
            if child_name not in required_fields:
                required_fields.append(child_name)

        field["required_fields"] = required_fields

    if "additional_values" in field:
        if typ != "object":
            raise ValueError(f"{path}.additional_values is only valid when type='object'")
        field["additional_values"] = _validate_field_schema(
            f"{field_name}.*", field["additional_values"], path=f"{path}.additional_values")

    if "additional_keys" in field and not isinstance(field["additional_keys"], bool):
        raise TypeError(f"{path}.additional_keys must be a boolean")

    return field


def coerce_session_metadata_pocket_schema(
    key: str,
    schema: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Validate and canonicalize one app-owned session_metadata pocket schema.

    Required shape:

        {
            "kind": "session_metadata_pocket_schema_v1",
            "label": "...",
            "fields": {
                "field_name": {"type": "string", "required": True}
            },
            "additional_keys": False
        }

    The schema is documentation/validation metadata only. It must be JSON-safe.
    """
    if not isinstance(key, str) or not key:
        raise TypeError("pocket key must be a non-empty string")

    if key in CORE_SESSION_METADATA_KEYS:
        raise KeyError(f"{key!r} is a core session_metadata key and cannot be registered")

    if key.startswith("_"):
        raise ValueError("pocket key may not start with '_'")

    if "." in key:
        raise ValueError("pocket key must be a top-level metadata key, not a dotted path")

    if not isinstance(schema, Mapping):
        raise TypeError("pocket schema must be a mapping")

    _reject_callables_deep(schema, path=f"pocket_schema[{key!r}]")
    _require_json_safe(schema, path=f"pocket_schema[{key!r}]")

    out = dict(schema)

    unknown = set(out) - {
        "kind",
        "label",
        "description",
        "owner",
        "version",
        "fields",
        "required_fields",
        "additional_keys",
        "allow_none",
        "examples",
        "laws",
    }
    if unknown:
        raise KeyError(f"pocket schema {key!r} has unknown key(s): {sorted(unknown)}")

    kind = out.get("kind", "session_metadata_pocket_schema_v1")
    if kind != "session_metadata_pocket_schema_v1":
        raise ValueError(
            f"pocket schema {key!r} kind must be "
            "'session_metadata_pocket_schema_v1'"
        )
    out["kind"] = kind

    label = out.get("label", key)
    if not isinstance(label, str) or not label:
        raise TypeError(f"pocket schema {key!r}.label must be a non-empty string")
    out["label"] = label

    fields = out.get("fields", {})
    if not isinstance(fields, Mapping):
        raise TypeError(f"pocket schema {key!r}.fields must be a mapping")

    out["fields"] = {
        str(field_name): _validate_field_schema(
            str(field_name),
            field_schema,
            path=f"pocket_schema[{key!r}].fields.{field_name}",
        )
        for field_name, field_schema in fields.items()
    }

    explicit_required = _coerce_string_list(
        out.get("required_fields"),
        path=f"pocket_schema[{key!r}].required_fields",
    )
    required_from_fields = [
        field_name
        for field_name, field_schema in out["fields"].items()
        if field_schema.get("required") is True
    ]

    required: list[str] = []
    for field_name in [*explicit_required, *required_from_fields]:
        if field_name not in out["fields"]:
            raise KeyError(
                f"pocket schema {key!r} required field {field_name!r} "
                "is not declared in fields"
            )
        if field_name not in required:
            required.append(field_name)
    out["required_fields"] = required

    if "additional_keys" not in out:
        out["additional_keys"] = True
    if not isinstance(out["additional_keys"], bool):
        raise TypeError(f"pocket schema {key!r}.additional_keys must be a boolean")

    if "allow_none" not in out:
        out["allow_none"] = False
    if not isinstance(out["allow_none"], bool):
        raise TypeError(f"pocket schema {key!r}.allow_none must be a boolean")

    if "examples" in out:
        if not isinstance(out["examples"], list):
            raise TypeError(f"pocket schema {key!r}.examples must be a list")
        _require_json_safe(out["examples"], path=f"pocket_schema[{key!r}].examples")

    if "laws" in out:
        if not isinstance(out["laws"], list) or not all(
            isinstance(item, str) for item in out["laws"]
        ):
            raise TypeError(f"pocket schema {key!r}.laws must be a list of strings")

    return out


def _value_matches_type(value: Any, typ: str) -> bool:
    if typ == "any":
        return True
    if typ == "object":
        return isinstance(value, Mapping)
    if typ == "array":
        return isinstance(value, list)
    if typ == "string":
        return isinstance(value, str)
    if typ == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if typ == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if typ == "boolean":
        return isinstance(value, bool)
    if typ == "null":
        return value is None
    raise AssertionError(f"unknown field type {typ!r}")


def _validate_value_against_field_schema(
    value: Any,
    field_schema: Mapping[str, Any],
    *,
    path: str,
) -> None:
    typ = field_schema.get("type", "any")
    if not _value_matches_type(value, typ):
        raise TypeError(f"{path} must be of type {typ!r}")

    if "enum" in field_schema and value not in field_schema["enum"]:
        raise ValueError(f"{path} must be one of {field_schema['enum']!r}")

    if typ == "array" and "items" in field_schema:
        for index, item in enumerate(value):
            _validate_value_against_field_schema(
                item,
                field_schema["items"],
                path=f"{path}[{index}]",
            )

    if typ == "object" and ("fields" in field_schema or "additional_values" in field_schema):
        validate_session_metadata_pocket_value(
            value,
            field_schema,
            path=path,
        )


def validate_session_metadata_pocket_value(
    value: Any,
    schema: Mapping[str, Any],
    *,
    path: str = "session_metadata pocket",
) -> None:
    """
    Optional lightweight validator for object-shaped pocket values.

    This intentionally supports a small schema vocabulary. It is enough to make
    app metadata pockets verified without turning this package into a full JSON
    Schema implementation.
    """
    if value is None and bool(schema.get("allow_none", False)):
        return

    _reject_callables_deep(value, path=path)
    _require_json_safe(value, path=path)

    if not isinstance(value, Mapping):
        raise TypeError(f"{path} must be a mapping")

    fields = schema.get("fields", {})
    required_fields = schema.get("required_fields", [])
    additional_keys = schema.get("additional_keys", True)

    for field_name in required_fields:
        if field_name not in value:
            raise KeyError(f"{path} missing required field {field_name!r}")

    if additional_keys is False:
        unknown = set(value) - set(fields)
        if unknown:
            raise KeyError(f"{path} has unknown key(s): {sorted(unknown)}")

    for field_name, field_value in value.items():
        if field_name in fields:
            _validate_value_against_field_schema(
                field_value,
                fields[field_name],
                path=f"{path}.{field_name}",
            )
        elif "additional_values" in schema:
            _validate_value_against_field_schema(
                field_value, schema["additional_values"], path=f"{path}.{field_name}")


class SessionMetadataSurfaceRegistry:
    """
    Process-local registry for app-owned session_metadata pocket schemas.

    Apps call register_pocket(...) once at startup.

    Tests may use clear_registered_pockets_for_tests() to reset process state.
    """

    _registered_pockets: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def register_pocket(
        *,
        key: str,
        schema: Mapping[str, Any],
        replace: bool = False,
    ) -> Dict[str, Any]:
        canonical = coerce_session_metadata_pocket_schema(key, schema)

        if key in SessionMetadataSurfaceRegistry._registered_pockets and not replace:
            raise KeyError(f"session_metadata pocket {key!r} is already registered")

        SessionMetadataSurfaceRegistry._registered_pockets[key] = canonical
        return deepcopy(canonical)

    @staticmethod
    def registered_pockets() -> Dict[str, Dict[str, Any]]:
        return deepcopy(SessionMetadataSurfaceRegistry._registered_pockets)

    @staticmethod
    def registered_keys() -> list[str]:
        return sorted(SessionMetadataSurfaceRegistry._registered_pockets)

    @staticmethod
    def validate_registered_session_metadata(
        session_metadata: Mapping[str, Any],
    ) -> None:
        if not isinstance(session_metadata, Mapping):
            raise TypeError("session_metadata must be a mapping")

        for key, schema in SessionMetadataSurfaceRegistry._registered_pockets.items():
            if key not in session_metadata:
                continue

            validate_session_metadata_pocket_value(
                session_metadata[key],
                schema,
                path=f"session_metadata[{key!r}]",
            )

    @staticmethod
    def clear_registered_pockets_for_tests() -> None:
        SessionMetadataSurfaceRegistry._registered_pockets.clear()