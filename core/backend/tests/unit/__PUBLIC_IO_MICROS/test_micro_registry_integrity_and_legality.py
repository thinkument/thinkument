from __future__ import annotations

import sys
import types

import pytest

import _thinkprogram._iomicrosTM.validators  # noqa: F401
from _thinkprogram._iomicrosTM.core.api_validation import (
    DatumFillValidator,
    validate_micro_validator_legality,
)
from _thinkprogram._iomicrosTM.core.micro_registry import (
    get_micro_type_definition,
    list_public_micro_types,
    validate_micro_registry_integrity,
)
from _thinkprogram._iomicrosTM.core.micro_validator_registry import registered_validator_paths


def test_every_micro_definition_is_complete_and_every_policy_is_registered() -> None:
    validate_micro_registry_integrity()
    registered = set(registered_validator_paths())
    for name in list_public_micro_types():
        definition = get_micro_type_definition(name)
        assert definition.name == name
        assert definition.description.strip()
        assert definition.modality
        assert definition.python_types
        assert definition.json_schema is not None
        for policy in definition.validators:
            assert policy.path in registered, (name, policy.path)


def test_legality_is_capability_superset_not_auto_attachment() -> None:
    micro = {"name": "n", "type": "integer", "required": True}
    validate_micro_validator_legality(micro)  # no validators is legal

    datum = DatumFillValidator(
        id="N",
        title="N",
        micros=[micro],
        enforce_validator_legality=True,
    )
    # No registry validator is auto-injected; -10 is accepted structurally.
    assert datum.parse_and_validate_fill(raw={"n": -10}) == {"n": -10}


def test_builtin_cross_family_validator_is_rejected_but_app_validator_is_open() -> None:
    builtin_mismatch = {
        "name": "email",
        "type": "email",
        "validators": ["_thinkprogram._iomicrosTM.validators.number:is_positive_int"],
    }

    with pytest.raises(ValueError, match="not allowed"):
        validate_micro_validator_legality(builtin_mismatch)

    custom_module = types.ModuleType("micro_legality_app_validators")

    def app_owned(value):
        return True, None

    custom_module.app_owned = app_owned
    sys.modules[custom_module.__name__] = custom_module

    custom = {
        "name": "email",
        "type": "email",
        "validators": [
            "micro_legality_app_validators:app_owned",
        ],
    }

    validate_micro_validator_legality(custom)

    datum = DatumFillValidator(
        id="E",
        title="E",
        micros=[custom],
        enforce_validator_legality=True,
    )

    assert datum.parse_and_validate_fill(
        raw={"email": "x"},
    ) == {"email": "x"}