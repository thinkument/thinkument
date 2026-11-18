from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class MicroTypeSpec:
    name: str
    description: str


@dataclass(frozen=True)
class ValidatorPolicy:
    """Platform-known validator capability for one micro type.

    This is the projection/marriage capability sheet, not a closed-world ban on
    application-owned validators. A concrete dataspec may attach opaque custom
    validators; the platform can execute them, but only policies declared here
    are known to be projectable/introspectable as first-class micro capabilities.

    ``mandatory_enforced`` means "hard/projectable when activated", not
    "automatically attach this validator to every usage".
    """

    path: str
    mandatory_enforced: bool = False
    arg_map: Mapping[str, str] = field(default_factory=dict)
    guidance_channel: str = "local_guidance"


@dataclass(frozen=True)
class MicroTypeDefinition:
    """Engine-owned, renderer-independent definition of one canonical data atom."""

    name: str
    description: str
    json_schema: Optional[
        Mapping[str, Any] | Callable[[Mapping[str, Any]], Mapping[str, Any]]
    ] = None
    requiredness_policy: str = "normal"
    visibility_policy: str = "visible"
    modality: Optional[str] = None
    validators: Tuple[ValidatorPolicy, ...] = ()
    validator_modalities: Tuple[str, ...] = ()
    python_types: Tuple[type, ...] = (str,)
    coerce: Optional[Callable[[Any], Any]] = None
    coerce_to_micro_types: Tuple[str, ...] = ()
    python_casts: Mapping[type, Callable[[Any], Any]] = field(default_factory=dict)


MICRO_TYPES: Dict[str, MicroTypeDefinition] = {}
_REGISTRATION_LOCK = RLock()


def _ensure_defaults_loaded() -> None:
    """Import the canonical built-ins, even if extensions populated the dict.

    ``if MICRO_TYPES: return`` is incorrect: an independently loaded pack can
    populate the shared dict before the built-in table is imported. Importing
    the module is idempotent, including when the table calls back into registry
    integrity validation while its import is finishing.
    """
    import_module("_thinkprogram._iomicrosTM.table_micros")


def normalize_micro_type_name(micro_type: str) -> str:
    name = str(micro_type or "").strip().lower()
    if not name:
        raise ValueError("micro_type must be non-empty")
    return name


def list_public_micro_types() -> List[str]:
    _ensure_defaults_loaded()
    return sorted(MICRO_TYPES)


def get_micro_type_definition(micro_type: str) -> MicroTypeDefinition:
    _ensure_defaults_loaded()
    name = normalize_micro_type_name(micro_type)
    return MICRO_TYPES[name]


def get_micro_type_spec(micro_type: str) -> MicroTypeSpec:
    definition = get_micro_type_definition(micro_type)
    return MicroTypeSpec(name=definition.name, description=definition.description)


def import_registrar() -> Dict[str, MicroTypeDefinition]:
    _ensure_defaults_loaded()
    return MICRO_TYPES


def validator_policy_map(micro_type: str) -> Dict[str, ValidatorPolicy]:
    definition = get_micro_type_definition(micro_type)
    return {policy.path: policy for policy in definition.validators}


def is_validator_allowed_for_micro(*, micro_type: str, validator_path: str) -> bool:
    return str(validator_path) in validator_policy_map(micro_type)


def validate_micro_registry_integrity() -> None:
    """Validate table-internal invariants without importing validator modules."""
    _ensure_defaults_loaded()
    names = set(MICRO_TYPES)
    for key, definition in MICRO_TYPES.items():
        if definition.name != key:
            raise ValueError(
                f"micro key/name mismatch: key={key!r}, definition.name={definition.name!r}"
            )
        if not definition.description.strip():
            raise ValueError(f"micro {key!r} must have a description")
        if not definition.python_types:
            raise ValueError(f"micro {key!r} must declare python_types")
        unknown = sorted(set(definition.coerce_to_micro_types) - names)
        if unknown:
            raise ValueError(f"micro {key!r} has unknown coercion targets: {unknown}")
        paths = [policy.path for policy in definition.validators]
        if len(paths) != len(set(paths)):
            raise ValueError(f"micro {key!r} contains duplicate validator policies")
        for policy in definition.validators:
            if not policy.path or ":" not in policy.path:
                raise ValueError(
                    f"micro {key!r} has noncanonical validator path {policy.path!r}"
                )


def register_micro_type_definitions(
    definitions: Iterable[MicroTypeDefinition],
) -> Tuple[MicroTypeDefinition, ...]:
    """Atomically augment the built-ins with one or more extension micros.

    A pack may define multiple types that name each other as coercion targets;
    validate them as one transaction. Repeat registration of *identical*
    definitions is idempotent. Built-in collisions and mismatched definitions
    are rejected, and no partial additions survive validation failure.
    """
    proposed = tuple(definitions)
    for definition in proposed:
        if not isinstance(definition, MicroTypeDefinition):
            raise TypeError("definition must be a MicroTypeDefinition")
        name = normalize_micro_type_name(definition.name)
        if name != definition.name:
            raise ValueError("micro definition.name must be canonical lowercase")

    with _REGISTRATION_LOCK:
        _ensure_defaults_loaded()
        pending: dict[str, MicroTypeDefinition] = {}
        for definition in proposed:
            previous = pending.get(definition.name, MICRO_TYPES.get(definition.name))
            if previous is not None and previous != definition:
                raise ValueError(
                    f"micro type {definition.name!r} is already registered differently"
                )
            pending[definition.name] = definition
        additions = {
            name: definition
            for name, definition in pending.items()
            if name not in MICRO_TYPES
        }
        MICRO_TYPES.update(additions)
        try:
            validate_micro_registry_integrity()
        except Exception:
            for name in additions:
                del MICRO_TYPES[name]
            raise
        return tuple(MICRO_TYPES[definition.name] for definition in proposed)


def register_micro_type_definition(
    definition: MicroTypeDefinition,
) -> MicroTypeDefinition:
    """Idempotent single-micro convenience form of atomic registration."""
    return register_micro_type_definitions((definition,))[0]


__all__ = [
    "MICRO_TYPES",
    "MicroTypeSpec",
    "MicroTypeDefinition",
    "ValidatorPolicy",
    "get_micro_type_definition",
    "get_micro_type_spec",
    "import_registrar",
    "is_validator_allowed_for_micro",
    "list_public_micro_types",
    "normalize_micro_type_name",
    "register_micro_type_definition",
    "register_micro_type_definitions",
    "validate_micro_registry_integrity",
    "validator_policy_map",
]
