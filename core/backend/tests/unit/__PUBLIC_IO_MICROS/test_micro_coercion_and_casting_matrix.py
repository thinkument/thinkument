from __future__ import annotations

from typing import Any, Type

import pytest

from _thinkprogram._iomicrosTM.core.api_coercion import (
    can_cast_micro_to_python,
    can_coerce_micro,
    cast_micro_value_to_python,
    coerce_micro_value,
)
from _thinkprogram._iomicrosTM.core.micro_registry import get_micro_type_definition, list_public_micro_types


def _identity_sample(micro_type: str) -> Any:
    return {
        "text": "hello",
        "textarea": "hello\nworld",
        "slug": "hello-world",
        "integer": "12",
        "number": "12.5",
        "boolean": "true",
        "checkbox": 1,
        "select": "option_1",
        "multi_select": ["a", "b"],
        "email": "a@example.com",
        "url": "https://example.com/a",
        "date": "2026-01-01",
        "time": "09:30",
        "datetime": "2026-01-01T09:30:00Z",
        "code": "print(1)",
        "latex_math": r"x^2",
        "image_url": "https://example.com/image.png",
        "image_filepath": "./image.png",
        "file_url": "https://example.com/file.bin",
        "file_filepath": "./file.bin",
        "json_object": {"k": "v"},
        "json_array": [1, 2],
        "object-json": {"k": [1, 2]},
        "hidden-pause": True,
    }[micro_type]


def _edge_sample(src: str, dst: str) -> Any:
    if src == dst:
        return _identity_sample(src)
    if dst == "integer":
        return "12" if src in {"text", "textarea"} else 12.0
    if dst == "number":
        return "12.5" if src in {"text", "textarea"} else 12
    if dst in {"boolean", "checkbox"}:
        return True
    if dst == "select":
        return "option_1"
    if dst == "date":
        return "2026-01-01"
    if dst == "time":
        return "09:30"
    if dst == "datetime":
        return "2026-01-01T09:30:00Z"
    if dst in {"url", "file_url", "image_url"}:
        return "https://example.com/image.png"
    if dst in {"file_filepath", "image_filepath"}:
        return "./image.png"
    if dst == "code":
        return "print(1)"
    if dst == "latex_math":
        return r"x^2"
    if dst == "json_object":
        return {"k": "v"}
    if dst == "json_array":
        return ["a", "b"] if src == "multi_select" else [1, 2]
    if dst == "object-json":
        return _identity_sample(src)
    if dst in {"text", "textarea"}:
        return _identity_sample(src)
    return _identity_sample(src)


def test_full_micro_to_micro_policy_matrix() -> None:
    micro_types = list_public_micro_types()
    assert len(micro_types) >= 20

    for src in micro_types:
        for dst in micro_types:
            allowed = can_coerce_micro(src_micro_type=src, dst_micro_type=dst)
            if not allowed:
                with pytest.raises(ValueError):
                    coerce_micro_value(
                        src_micro_type=src,
                        dst_micro_type=dst,
                        raw=_identity_sample(src),
                    )
                continue

            out = coerce_micro_value(
                src_micro_type=src,
                dst_micro_type=dst,
                raw=_edge_sample(src, dst),
            )
            if out is not None:
                assert isinstance(out, tuple(get_micro_type_definition(dst).python_types)), (src, dst, out)


def _cast_sample(micro_type: str, target: Type[Any]) -> Any:
    if micro_type == "number" and target is int:
        return 12.0
    if micro_type == "json_object":
        return {"a": 1}
    if micro_type == "json_array":
        return [1, 2]
    if micro_type == "object-json":
        return {"a": 1} if target is dict else [1, 2]
    return _identity_sample(micro_type)


def test_full_micro_to_python_cast_matrix() -> None:
    targets: list[Type[Any]] = [str, int, float, bool, dict, list]
    for micro_type in list_public_micro_types():
        for target in targets:
            if can_cast_micro_to_python(micro_type=micro_type, py_type=target):
                out = cast_micro_value_to_python(
                    micro_type=micro_type,
                    py_type=target,
                    raw=_cast_sample(micro_type, target),
                )
                if out is not None:
                    assert isinstance(out, target)
            else:
                with pytest.raises(ValueError):
                    cast_micro_value_to_python(
                        micro_type=micro_type,
                        py_type=target,
                        raw=_cast_sample(micro_type, target),
                    )


def test_value_dependent_allowed_coercion_can_still_reject_bad_content() -> None:
    assert can_coerce_micro(src_micro_type="text", dst_micro_type="integer")
    with pytest.raises(ValueError):
        coerce_micro_value(src_micro_type="text", dst_micro_type="integer", raw="not-an-int")
