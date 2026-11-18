from __future__ import annotations

from dataclasses import dataclass

import pytest

import _thinkprogram._iomicrosTM.validators  # noqa: F401
from _thinkprogram._iomicrosTM.core.api_fills import (
    DeadJSONError,
    assert_dead_json,
    build_datum_validator,
    datum_fill_data_meets_its_structural_micros_shell,
    datum_required_micro_names,
    is_blank_value,
    parse_and_validate_macro_fill,
    parse_validate_and_coerce_macro_fill,
    unbox_leaf,
)


@dataclass
class _DC:
    x: int


def test_strict_dead_json_membrane() -> None:
    for value in (None, "x", 1, True, 1.25, {"a": [1, 2]}, ["x", {"y": 2}]):
        assert_dead_json(value)

    for bad in (
        float("nan"),
        float("inf"),
        _DC(3),
        {2: "not-a-json-object-key"},
        (1, 2),
    ):
        with pytest.raises(DeadJSONError):
            assert_dead_json(bad)


def test_unboxing_is_explicit_and_plain_json_mappings_are_never_envelopes() -> None:
    literal = {"value": "x"}
    typed_literal = {"value": "x", "micro_type": "text"}
    assert unbox_leaf(literal) is literal
    assert unbox_leaf(typed_literal) is typed_literal
    assert unbox_leaf({"__boxed__": True, "value": 7}) == 7
    assert unbox_leaf({"__boxed__": True, "value": "x", "extra": 1}) == {
        "__boxed__": True,
        "value": "x",
        "extra": 1,
    }

    for blank in (
        None,
        "",
        " ",
        [],
        {},
        {"__boxed__": True, "value": ""},
        {"__boxed__": True, "value": []},
    ):
        assert is_blank_value(blank)
    for present in (0, False, "x", [0], {"x": None}, {"value": ""}):
        assert not is_blank_value(present)


def test_required_names_and_structural_satisfaction() -> None:
    assert datum_required_micro_names({"id": "single-value-shorthand"}) == ["value"]
    optional = {"micros": [{"name": "a", "required": False}]}
    assert datum_required_micro_names(optional) == []
    assert datum_fill_data_meets_its_structural_micros_shell(optional, {})

    required = {
        "micros": [
            {"name": "value", "required": True},
            {"name": "units", "required": True},
        ]
    }
    assert datum_fill_data_meets_its_structural_micros_shell(required, {"value": 1, "units": "kg"})
    assert not datum_fill_data_meets_its_structural_micros_shell(required, {"value": 1})


def test_json_object_with_value_key_survives_validation_and_coercion() -> None:
    datum = {
        "id": "JSON",
        "micros": [{
            "name": "payload",
            "type": "json_object",
            "required": True,
            "validators": ["_thinkprogram._iomicrosTM.validators.object_json:is_json_object"],
        }],
    }
    payload = {"value": 1}
    out = parse_validate_and_coerce_macro_fill(
        datum=datum,
        raw={"payload": payload},
    )
    assert out == {"payload": payload}


def test_platform_wall_preserves_overlay_keys_and_checks_builtin_compatibility() -> None:
    datum = {
        "id": "N",
        "micros": [{
            "name": "n",
            "type": "number",
            "required": True,
            "validators": [{
                "path": "_thinkprogram._iomicrosTM.validators.number:min_number",
                "args": {"min_value": 3},
            }],
        }],
    }
    assert parse_and_validate_macro_fill(datum=datum, raw={"n": 3.5}) == {"n": 3.5}

    overlay = {"n": 4, "prior_shell_key": 1}

    assert parse_and_validate_macro_fill(
        datum=datum,
        raw=overlay,
    ) == overlay

    assert parse_validate_and_coerce_macro_fill(
        datum=datum,
        raw=overlay,
    ) == overlay

    strict = build_datum_validator(
        datum,
        enforce_known_micros=True,
    )
    with pytest.raises(ValueError, match="Unknown micros"):
        strict.parse_and_validate_fill(raw=overlay)

    illegal = {
        "id": "E",
        "micros": [{
            "name": "email",
            "type": "email",
            "required": True,
            "validators": ["_thinkprogram._iomicrosTM.validators.number:min_number"],
        }],
    }
    with pytest.raises(ValueError, match="not allowed for micro type"):
        parse_and_validate_macro_fill(datum=illegal, raw={"email": "a@example.com"})


def test_validate_then_coerce_then_revalidate() -> None:
    datum = {
        "id": "I",
        "micros": [{
            "name": "count",
            "type": "integer",
            "required": True,
            "validators": [{
                "path": "_thinkprogram._iomicrosTM.validators.number:min_number",
                "args": {"min_value": 3},
            }],
        }],
    }
    out = parse_validate_and_coerce_macro_fill(datum=datum, raw={"count": "4"})
    assert out == {"count": 4}
    assert isinstance(out["count"], int)

    with pytest.raises(ValueError):
        parse_validate_and_coerce_macro_fill(datum=datum, raw={"count": "not-an-int"})
