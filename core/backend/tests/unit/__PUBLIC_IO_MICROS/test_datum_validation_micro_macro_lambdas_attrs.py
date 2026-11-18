from __future__ import annotations

import sys
import types
from typing import Any, Dict

import pytest

from _thinkprogram._iomicrosTM.core.api_validation import DatumFillValidator
from _thinkprogram._iomicrosTM.core.value_semantics import unbox_leaf

validators = types.ModuleType("datum_test_validators")


def is_nonempty_str(value: Any):
    value = unbox_leaf(value)
    ok = isinstance(value, str) and bool(value.strip())
    return ok, None if ok else "must be a non-empty string"


def is_positive_int(value: Any):
    try:
        number = int(unbox_leaf(value))
        ok = number > 0
    except Exception:
        ok = False
    return ok, None if ok else "must be a positive integer"


def units_allowed(_self: Any, macro: Dict[str, Any]):
    ok = macro.get("units") in {"kg", "lb", "cm", "mm"}
    return ok, None if ok else "units not allowed"


def value_units_combo_ok(_self: Any, macro: Dict[str, Any]):
    try:
        value = float(unbox_leaf(macro.get("value")))
    except Exception:
        return False, "value is not a number"
    if macro.get("units") in {"cm", "mm"} and value > 1000:
        return False, "value exceeds allowed maximum for length units"
    return True, None


validators.is_nonempty_str = is_nonempty_str
validators.is_positive_int = is_positive_int
validators.units_allowed = units_allowed
validators.value_units_combo_ok = value_units_combo_ok
sys.modules["datum_test_validators"] = validators


def test_micro_and_macro_validation_matrix() -> None:
    text = DatumFillValidator(
        id="T",
        title="Text",
        micros=[{
            "name": "value",
            "type": "text",
            "required": True,
            "validators": ["datum_test_validators:is_nonempty_str"],
        }],
    )
    quantity = DatumFillValidator(
        id="Q",
        title="Quantity",
        micros=[
            {
                "name": "value",
                "type": "number",
                "required": True,
                "validators": ["datum_test_validators:is_positive_int"],
            },
            {"name": "units", "type": "select", "required": True},
        ],
        macro_validation_lambdas=[
            "datum_test_validators:units_allowed",
            "datum_test_validators:value_units_combo_ok",
        ],
    )

    assert text.parse_and_validate_fill(raw={"value": "hello"}) == {"value": "hello"}
    with pytest.raises(ValueError, match="Missing required micros"):
        text.parse_and_validate_fill(raw={"value": ""})

    assert quantity.parse_and_validate_fill(raw={"value": 10, "units": "kg"})["units"] == "kg"
    with pytest.raises(ValueError, match="units not allowed"):
        quantity.parse_and_validate_fill(raw={"value": 10, "units": "stone"})
    with pytest.raises(ValueError, match="exceeds allowed maximum"):
        quantity.parse_and_validate_fill(raw={"value": 5000, "units": "cm"})


def test_argful_forms_are_equivalent() -> None:
    mod = sys.modules["datum_test_validators"]

    def min_number(value: Any, *, min_value: int):
        try:
            ok = float(unbox_leaf(value)) >= float(min_value)
        except Exception:
            ok = False
        return ok, None if ok else f"must be >= {min_value}"

    def total_words_max(macro: Dict[str, Any], *, max_words: int):
        total = sum(len(str(value).split()) for value in macro.values() if isinstance(value, str))
        ok = total <= max_words
        return ok, None if ok else f"total words must be <= {max_words}"

    mod.min_number = min_number
    mod.total_words_max = total_words_max

    datum = DatumFillValidator(
        id="D",
        title="Doc",
        micros=[{
            "name": "n",
            "type": "number",
            "required": True,
            "validators": [
                {"path": "datum_test_validators:min_number", "args": {"min_value": 3}},
            ],
        }],
    )
    assert datum.parse_and_validate_fill(raw={"n": 3.5}) == {"n": 3.5}
    with pytest.raises(ValueError, match="must be >= 3"):
        datum.parse_and_validate_fill(raw={"n": 2.9})

    macro = DatumFillValidator(
        id="M",
        title="Macro",
        micros=[
            {"name": "a", "type": "text", "required": True},
            {"name": "b", "type": "text", "required": True},
        ],
        macro_validation_lambdas={
            "datum_test_validators:total_words_max": {"max_words": 3}
        },
    )
    assert macro.parse_and_validate_fill(raw={"a": "one", "b": "two three"})
    with pytest.raises(ValueError, match="total words"):
        macro.parse_and_validate_fill(raw={"a": "one two", "b": "three four"})


def test_internal_typeerror_is_not_retried_with_another_call_shape() -> None:
    calls = {"count": 0}

    def explodes(value: Any):
        calls["count"] += 1
        raise TypeError("validator implementation bug")

    datum = DatumFillValidator(
        id="BUG",
        title="Bug",
        micros=[{
            "name": "value",
            "type": "text",
            "required": True,
            "validators": [explodes],
        }],
    )
    with pytest.raises(TypeError, match="implementation bug"):
        datum.parse_and_validate_fill(raw={"value": "x"})
    assert calls["count"] == 1
