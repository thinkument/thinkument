"""Explicit subtable ownership above the platform's flat micro registry."""
from dataclasses import dataclass
from functools import lru_cache
from _thinkprogram._iomicrosTM.core.value_semantics import assert_dead_json
from types import MappingProxyType

from _thinkprogram._iomicrosTM.core.micro_registry import (
    MicroTypeDefinition, get_micro_type_definition, register_micro_type_definitions,
)
from _thinkprogram._iomicrosTM.tiny_coercers import coerce_integer
from _thinkprogram._iomicrosTM.core.api_validation import validate_micro_validator_legality


@dataclass(frozen=True)
class MicroRow:
    definition: MicroTypeDefinition
    renderer: str


@dataclass(frozen=True)
class MicroTable:
    id: str
    rows: tuple[MicroRow, ...]


def bounded_integer(value):
    value = coerce_integer(value)
    if value is not None and not 0 <= value <= 100:
        raise ValueError('Expected an integer between 0 and 100.')
    return value


BOUNDED_INTEGER = MicroTypeDefinition(
    name='creativity_bounded_integer', description='An integer from 0 through 100.',
    json_schema={'type':'integer','minimum':0,'maximum':100}, modality='number',
    python_types=(int,), coerce=bounded_integer, coerce_to_micro_types=('integer',),
    python_casts={int:bounded_integer},
)
MICRO_TABLES = (
    MicroTable('basic', tuple(MicroRow(get_micro_type_definition(name), renderer)
        for name, renderer in (('text','text'),('integer','integer'),('select','select')))),
    MicroTable('bounded', (MicroRow(BOUNDED_INTEGER, 'integer'),)),
)


def micro_catalogue(tables=None):
    """Validate all ownership and browser references before any registration."""
    tables = MICRO_TABLES if tables is None else tables
    from ..shared_rendering.browser_exports import browser_exports
    exports = browser_exports('micros.js')
    table_ids, rows = set(), {}
    for table in tables:
        if not isinstance(table, MicroTable) or not table.id or table.id in table_ids:
            raise ValueError('Micro subtables require unique nonempty IDs.')
        table_ids.add(table.id)
        for row in table.rows:
            if not isinstance(row, MicroRow) or not isinstance(row.definition, MicroTypeDefinition):
                raise TypeError('Expected a micro definition and renderer row.')
            name = row.definition.name
            if name in rows:
                raise ValueError(f'Micro {name!r} belongs to more than one subtable.')
            if row.renderer not in exports:
                raise ValueError(f'Micro {name!r} has no browser renderer {row.renderer!r}.')
            rows[name] = row
    return MappingProxyType(rows)


@lru_cache(maxsize=1)
def admitted_micros():
    return micro_catalogue()


def register_microtables_v1():
    rows = admitted_micros()
    return register_micro_type_definitions(row.definition for row in rows.values())


def validate_shell(shell):
    """Inspect without rewriting: the emitted descriptor is the render argument."""
    if not isinstance(shell, dict) or type(shell.get('micros')) is not list:
        raise ValueError('A library shell requires a micros list.')
    assert_dead_json(shell['micros'], path='shell.micros')
    from ..shared_rendering.aesthetics import MICRO_PLACEMENT_KEY, PLACEMENT_AXES, PLACEMENT_DEFAULTS
    placement = shell.get(MICRO_PLACEMENT_KEY, PLACEMENT_DEFAULTS['micros'])
    if placement not in PLACEMENT_AXES['micros']:
        raise ValueError(f'Unknown micro placement {placement!r}.')
    rows = admitted_micros()
    names = set()
    for micro in shell['micros']:
        if type(micro) is not dict:
            raise ValueError('Micro descriptors must be JSON objects.')
        name = micro.get('name')
        if type(name) is not str or not name or name in names:
            raise ValueError('Micro names must be nonempty and unique within a shell.')
        names.add(name)
        if micro.get('type') not in rows:
            raise ValueError(f"Micro type {micro.get('type')!r} is not admitted by the library.")
        validate_micro_validator_legality(micro)
    return shell
