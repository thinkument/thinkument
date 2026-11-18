"""A typed seed-to-consumer flow in Crystal, completely independent of Metal."""
from copy import deepcopy
from authoring_funneling.a_typed_PSMCW_authoring import D
from ..widgets import SEED, CONSUMER
from ..publication import authoring_profile_v1

CRYSTAL_FLOW_P = {
    'kind': 'think_program_v1',
    'surface_version': 'v1',
    'symbols': {},
    'puppeteering': {},
    'run': {
        'program': {
            'info': {'id': 'crystal_flow', 'title': 'Crystal Typed Flow'},
            'widgets': {
                'seed_1': {'widget': SEED, 'args': {'title': 'Crystal Data', 'count': 1}, 'bindings': {}},
                'consumer_1': {
                    'widget': CONSUMER,
                    'args': {},
                    'bindings': {
                        'sources': {
                            'draft': {'widget': 'seed_1', 'port': 'result'},
                            'entries': {'widget': 'seed_1', 'port': 'entries'},
                        },
                        'inputs': {
                            'context': D.dict({
                                'heading': D.ref('draft', 'title'),
                                'items': D.map(
                                    D.ref('entries', 'rows'),
                                    D.dict({'label': D.item('title'), 'count': D.item('count')}),
                                ),
                                'note': D.ref('draft', 'note'),
                            })
                        },
                    },
                },
            },
            'flow': [{'id': 'write', 'widgets': ['seed_1']}, {'id': 'read', 'widgets': ['consumer_1']}],
        },
        'config': {},
    },
}


def export():
    profile = authoring_profile_v1()
    return profile.compile({
        'profile_id': profile.profile_id,
        'W': sorted([SEED, CONSUMER]),
        'P': deepcopy(CRYSTAL_FLOW_P),
        'SM': {},
        'C': None,
    })
