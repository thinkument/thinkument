from __future__ import annotations

from dataclasses import dataclass

import pytest

from _thinkprogram._iomicrosTM.tiny_coercers import (
    coerce_bool,
    coerce_integer,
    coerce_number,
    coerce_object_json,
    coerce_str_list,
)


def test_integer_coercion_never_turns_malformed_nonblank_input_into_missing() -> None:
    assert coerce_integer("") is None
    assert coerce_integer("   ") is None
    assert coerce_integer("12") == 12
    assert coerce_integer(12.0) == 12
    with pytest.raises(ValueError):
        coerce_integer("nope")
    with pytest.raises(ValueError):
        coerce_integer(12.5)
    with pytest.raises(ValueError):
        coerce_integer(True)


def test_number_coercion_is_finite_and_excludes_bool() -> None:
    assert coerce_number("12") == 12
    assert coerce_number("12.5") == 12.5
    with pytest.raises(ValueError):
        coerce_number(True)
    for value in (float("nan"), float("inf"), "NaN", "Infinity"):
        with pytest.raises(ValueError):
            coerce_number(value)


def test_boolean_coercion_accepts_only_explicit_forms() -> None:
    for raw, expected in [
        (True, True), (False, False), (1, True), (0, False),
        ("yes", True), ("OFF", False), ("1", True), ("0", False),
    ]:
        assert coerce_bool(raw) is expected
    for bad in (2, -1, 0.5, "maybe"):
        with pytest.raises(ValueError):
            coerce_bool(bad)


def test_string_list_coercion_is_explicit_and_no_blank_items() -> None:
    assert coerce_str_list(None) == []
    assert coerce_str_list("") == []
    assert coerce_str_list("a") == ["a"]
    assert coerce_str_list(["a", "b"]) == ["a", "b"]
    with pytest.raises(ValueError):
        coerce_str_list(["a", 2])
    with pytest.raises(ValueError):
        coerce_str_list(["a", " "])


@dataclass
class _Payload:
    value: int


def test_object_json_normalizes_supported_objects_to_strict_json() -> None:
    assert coerce_object_json((1, 2)) == [1, 2]
    assert coerce_object_json(_Payload(3)) == {"value": 3}
    with pytest.raises(ValueError):
        coerce_object_json({1: "bad-key"})
