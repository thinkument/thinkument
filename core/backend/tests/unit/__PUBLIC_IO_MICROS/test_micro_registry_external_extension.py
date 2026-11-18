from __future__ import annotations

"""Extension boundary tests: external packs only import think-backend APIs."""

from dataclasses import replace

import pytest

from _thinkprogram._iomicrosTM.core.micro_registry import (
    MICRO_TYPES,
    MicroTypeDefinition,
    ValidatorPolicy,
    get_micro_type_definition,
    list_public_micro_types,
    register_micro_type_definition,
    register_micro_type_definitions,
    validate_micro_registry_integrity,
)


EXTENSION_NAME = "vendor_reference"
SECOND_EXTENSION = "vendor_reference_batch"


def _coerce_reference(value: object) -> str:
    return str(value).strip().upper()


@pytest.fixture(autouse=True)
def cleanup_extension_micro():
    # Real workers keep registrations for their lifetime. Tests isolate the
    # global registry while preserving built-in definitions.
    get_micro_type_definition("text")
    MICRO_TYPES.pop(EXTENSION_NAME, None)
    MICRO_TYPES.pop(SECOND_EXTENSION, None)
    yield
    MICRO_TYPES.pop(EXTENSION_NAME, None)
    MICRO_TYPES.pop(SECOND_EXTENSION, None)


def _definition(**changes: object) -> MicroTypeDefinition:
    base = MicroTypeDefinition(
        name=EXTENSION_NAME,
        description="Vendor-owned reference code.",
        json_schema={"type": "string", "pattern": r"^VP-[0-9]{4}$"},
        modality="text",
        validators=(
            ValidatorPolicy(path="vendor_pack.validators:is_vendor_reference"),
        ),
        python_types=(str,),
        coerce=_coerce_reference,
        coerce_to_micro_types=("text",),
        python_casts={str: _coerce_reference},
    )
    return replace(base, **changes)


def test_external_micro_augments_builtin_registry_idempotently() -> None:
    definition = _definition()
    assert register_micro_type_definition(definition) is definition
    assert register_micro_type_definition(definition) is definition
    assert get_micro_type_definition(EXTENSION_NAME).coerce(" vp-0042 ") == "VP-0042"
    assert {"text", "integer", EXTENSION_NAME} <= set(list_public_micro_types())
    validate_micro_registry_integrity()


def test_collision_cannot_change_builtin_or_extension() -> None:
    with pytest.raises(ValueError, match="already registered differently"):
        register_micro_type_definition(_definition(name="text"))
    original = register_micro_type_definition(_definition())
    with pytest.raises(ValueError, match="already registered differently"):
        register_micro_type_definition(_definition(description="Conflicting vendor"))
    assert get_micro_type_definition(EXTENSION_NAME) is original


def test_invalid_extension_rolls_back_without_poisoning_registry() -> None:
    with pytest.raises(ValueError, match="unknown coercion targets"):
        register_micro_type_definition(
            _definition(coerce_to_micro_types=("does_not_exist",))
        )
    assert EXTENSION_NAME not in list_public_micro_types()
    validate_micro_registry_integrity()


def test_noncanonical_and_non_definition_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="canonical lowercase"):
        register_micro_type_definition(_definition(name="VENDOR_REFERENCE"))
    with pytest.raises(TypeError, match="MicroTypeDefinition"):
        register_micro_type_definition({"name": EXTENSION_NAME})  # type: ignore[arg-type]


def test_atomic_batch_allows_cross_referenced_micros() -> None:
    first = _definition(coerce_to_micro_types=("text", SECOND_EXTENSION))
    second = MicroTypeDefinition(
        name=SECOND_EXTENSION,
        description="Second vendor value, mutually coercible with first.",
        json_schema={"type": "string"},
        modality="text",
        coerce=_coerce_reference,
        coerce_to_micro_types=(EXTENSION_NAME,),
    )
    assert register_micro_type_definitions((first, second)) == (first, second)
    assert register_micro_type_definitions((first, second)) == (first, second)
    validate_micro_registry_integrity()
    assert get_micro_type_definition(SECOND_EXTENSION) is second


def test_invalid_batch_rolls_back_every_new_type() -> None:
    first = _definition(coerce_to_micro_types=("text", SECOND_EXTENSION))
    bad = MicroTypeDefinition(
        name=SECOND_EXTENSION,
        description="Second vendor value",
        coerce_to_micro_types=("missing_target",),
    )
    with pytest.raises(ValueError, match="unknown coercion targets"):
        register_micro_type_definitions((first, bad))
    assert EXTENSION_NAME not in MICRO_TYPES
    assert SECOND_EXTENSION not in MICRO_TYPES
    validate_micro_registry_integrity()
