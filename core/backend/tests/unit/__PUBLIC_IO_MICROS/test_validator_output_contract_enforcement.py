from __future__ import annotations

import sys
import types

import pytest

from _thinkprogram._iomicrosTM.core.api_validation import DatumFillValidator

bad = types.ModuleType("bad_validators")


def bare_bool_ok(value):
    return True


def one_tuple(value):
    return (True,)


def wrong_types(value):
    return ("yes", {"not": "a string"})


bad.bare_bool_ok = bare_bool_ok
bad.one_tuple = one_tuple
bad.wrong_types = wrong_types
sys.modules["bad_validators"] = bad


@pytest.mark.parametrize(
    "path",
    ["bad_validators:bare_bool_ok", "bad_validators:one_tuple", "bad_validators:wrong_types"],
)
def test_micro_validator_bad_return_contract_is_system_error(path: str) -> None:
    datum = DatumFillValidator(
        id="T",
        title="Text",
        micros=[{
            "name": "value",
            "type": "text",
            "required": True,
            "validators": [path],
        }],
    )
    with pytest.raises(Exception) as exc:
        datum.parse_and_validate_fill(raw={"value": "hello"})
    assert exc.value.__class__.__name__ == "ValidatorReturnContractError"
    assert "must return (bool, str|None)" in str(exc.value)


def test_macro_validator_bad_return_contract_is_system_error() -> None:
    datum = DatumFillValidator(
        id="M",
        title="Macro",
        micros=[{"name": "value", "type": "text", "required": True}],
        macro_validation_lambdas=["bad_validators:wrong_types"],
    )
    with pytest.raises(Exception) as exc:
        datum.parse_and_validate_fill(raw={"value": "ok"})
    assert exc.value.__class__.__name__ == "ValidatorReturnContractError"
    assert "macro validator" in str(exc.value)
