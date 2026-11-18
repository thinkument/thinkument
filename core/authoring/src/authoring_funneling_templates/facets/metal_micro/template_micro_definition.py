"""Trusted backend semantics for an admitted example micro type."""
from _thinkprogram._iomicrosTM.core.micro_registry import MicroTypeDefinition
from _thinkprogram._iomicrosTM.tiny_coercers import coerce_integer


def bounded_score(value):
    result = coerce_integer(value)
    if result is not None and not 0 <= result <= 100:
        raise ValueError('Expected a score from 0 through 100.')
    return result


BOUNDED_SCORE = MicroTypeDefinition(
    name='example_bounded_score',
    description='An integer from zero through one hundred.',
    json_schema={'type': 'integer', 'minimum': 0, 'maximum': 100},
    modality='number', python_types=(int,), coerce=bounded_score,
    coerce_to_micro_types=('integer',), python_casts={int: bounded_score},
)
