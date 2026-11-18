from __future__ import annotations

import pytest

from _thinkprogram._iomicrosTM.core.api_validation import DatumFillValidator


def test_all_optional_micros_do_not_require_value_key() -> None:
    validator = DatumFillValidator(
        id="DOWN",
        title="Downstream",
        micros=[{"name": "got", "type": "number", "required": False}],
    )
    assert validator.parse_and_validate_fill(raw={"got": 1}) == {"got": 1}


def test_empty_micros_use_single_value_shorthand() -> None:
    validator = DatumFillValidator(id="D0", title="Single value", micros=[])
    with pytest.raises(ValueError, match="Missing required micros"):
        validator.parse_and_validate_fill(raw={"x": 1})


def test_blank_definition_is_consistent_for_explicit_boxes_and_containers() -> None:
    validator = DatumFillValidator(
        id="B",
        title="Blank",
        micros=[{"name": "value", "type": "text", "required": True}],
    )
    for blank in (
        None,
        "",
        "   ",
        [],
        {},
        {"__boxed__": True, "value": ""},
        {"__boxed__": True, "value": None},
    ):
        with pytest.raises(ValueError, match="Missing required micros"):
            validator.parse_and_validate_fill(raw={"value": blank})

    assert validator.parse_and_validate_fill(raw={"value": 0}) == {"value": 0}
    assert validator.parse_and_validate_fill(raw={"value": False}) == {"value": False}
    assert validator.parse_and_validate_fill(raw={"value": {"value": ""}}) == {
        "value": {"value": ""}
    }


def test_optional_micro_validators_do_not_make_omission_required() -> None:
    validator = DatumFillValidator(
        id="OPT",
        title="Optional",
        micros=[{
            "name": "units",
            "type": "select",
            "required": False,
            "validators": [{
                "path": "_thinkprogram._iomicrosTM.validators.choice:in_allowed",
                "args": {"options": ["kg", "lb"]},
            }],
        }],
    )
    assert validator.parse_and_validate_fill(raw={}) == {}
    assert validator.parse_and_validate_fill(raw={"units": ""}) == {"units": ""}
    with pytest.raises(ValueError, match="allowed"):
        validator.parse_and_validate_fill(raw={"units": "stone"})
