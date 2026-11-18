"""Central family aesthetics declarations and official backend SM gateway."""
from copy import deepcopy
from collections.abc import Mapping

from _thinksessions.sesh_metadata.__sesh_meta_dynamic_augmentation_by_apps import (
    SessionMetadataSurfaceRegistry, validate_session_metadata_pocket_value,
)

AESTHETICS_KEY = 'paquete_aesthetics'
MICRO_PLACEMENT_KEY = 'paquete_micro_placement'
PLACEMENT_AXES = {
    'widgets': {'vertical':'vertical', 'horizontal':'horizontal'},
    'micros': {'vertical':'vertical', 'horizontal':'horizontal'},
}
PLACEMENT_DEFAULTS = {'widgets':'vertical','micros':'vertical','visibility':'current_span'}
WIDGET_VISIBILITIES = ('current_span','all_appearances')


def placement_schema_v1():
    choices = {
        'placement': {'type':'string','enum':list(PLACEMENT_AXES['widgets'])},
        'visibility': {'type':'string','enum':list(WIDGET_VISIBILITIES)},
    }
    return {'kind':'session_metadata_pocket_schema_v1',
            'label':'Paquete widget placements',
            'description':'Family-local widget placement and visibility, with per-step overrides.',
            'allow_none':False,'additional_keys':False,
            'fields':{
                'defaults':{'type':'object','fields':deepcopy(choices),'additional_keys':False},
                'steps':{'type':'array','items':{'type':'object','fields':{
                    'step':{'type':'string','required':True},**deepcopy(choices)},'additional_keys':False}},
            },
            'laws':['Step IDs are the fully qualified public program step IDs.',
                    'Each step has at most one override; omitted fields inherit family defaults.',
                    'Placement affects presentation only; history and role restrictions remain authoritative.']}


SEMANTIC_TARGETS = {
    'section': 'data-paquete-section', 'step': 'data-paquete-step',
    'widget': 'data-paquete-widget', 'widget_type': 'data-paquete-widget-type',
    'micro': 'data-paquete-micro', 'micro_type': 'data-paquete-micro-type',
    'micro_table': 'data-paquete-micro-table', 'part': 'data-paquete-part',
}
RENDERABLE_PARTS = ('page', 'section', 'step', 'widget', 'micros', 'micro', 'label', 'control')


class AestheticsValidationError(ValueError):
    def __init__(self, path, message):
        self.path = path
        super().__init__(message)


def validate_widget_placements(pocket, *, step_ids=None, path=None):
    path = path or f'{AESTHETICS_KEY}.widget_placements'
    validate_session_metadata_pocket_value(pocket, placement_schema_v1(), path=path)
    seen = set()
    for index, row in enumerate(pocket.get('steps', [])):
        step = row['step']
        location = f'{path}.steps[{index}].step'
        if not step or step in seen:
            raise AestheticsValidationError(['widget_placements', 'steps', index, 'step'],
                f'{location}: require unique nonempty step IDs.')
        if step_ids is not None and step not in step_ids:
            raise AestheticsValidationError(['widget_placements', 'steps', index, 'step'],
                f'{location}: Unknown placement step {step!r}; use a fully qualified program step ID.')
        seen.add(step)
    return pocket


def css_schema_v1():
    return {'type': 'array', 'items': {'type': 'object', 'additional_keys': False,
        'fields': {
            'target': {'type': 'object', 'required': True, 'additional_keys': False,
                       'fields': {key: {'type': 'string', **({'enum': list(RENDERABLE_PARTS)} if key == 'part' else {})}
                                  for key in SEMANTIC_TARGETS}},
            'declarations': {'type': 'object', 'required': True, 'fields': {},
                             'additional_values': {'type': 'string'}},
            'pseudo_classes': {'type': 'array', 'items': {'type': 'string'}},
            'media': {'type': 'string'},
        }}}


def validate_css_injection(rules, *, step_ids=None, path=None):
    path = path or f'{AESTHETICS_KEY}.css_injection'
    # The registered schema handles shapes, including arbitrary string-valued declarations.
    for index, rule in enumerate(rules):
        step = rule['target'].get('step')
        if step_ids is not None and step is not None and step not in step_ids:
            raise AestheticsValidationError(['css_injection', index, 'target', 'step'],
                f'{path}[{index}].target.step: Unknown CSS step {step!r}.')


AESTHETICS_SECTIONS = {
    'widget_placements': {'schema': lambda: {'type': 'object', **{
        key: value for key, value in placement_schema_v1().items()
        if key in ('fields', 'additional_keys')}}, 'validator': validate_widget_placements,
        'browser': 'widgetsContainer'},
    'css_injection': {'schema': css_schema_v1, 'validator': validate_css_injection,
        'browser': 'applyAesthetics'},
}


def aesthetics_schema_v1():
    return {'kind': 'session_metadata_pocket_schema_v1', 'label': 'Paquete aesthetics',
            'allow_none': False, 'additional_keys': False,
            'fields': {name: row['schema']() for name, row in AESTHETICS_SECTIONS.items()}}


def register_aesthetics_metadata_v1():
    from .browser_exports import browser_exports
    exports = browser_exports('aesthetics.js')
    for name, row in AESTHETICS_SECTIONS.items():
        if row['browser'] not in exports:
            raise ValueError(f'Aesthetic section {name!r} has no browser behavior {row["browser"]!r}.')
    for axis, members in PLACEMENT_AXES.items():
        if not members or PLACEMENT_DEFAULTS[axis] not in members:
            raise ValueError(f'Placement axis {axis!r} requires a valid default.')
        for name, renderer in members.items():
            if not name or renderer not in exports:
                raise ValueError(f'Placement {axis}.{name} has no browser layout function {renderer!r}.')
    return SessionMetadataSurfaceRegistry.register_pocket(
        key=AESTHETICS_KEY, schema=aesthetics_schema_v1(), replace=True)


def validate_aesthetics(pocket, *, step_ids=None):
    # Canonicalize required child fields using the same official registry contract.
    from _thinksessions.sesh_metadata.__sesh_meta_dynamic_augmentation_by_apps import coerce_session_metadata_pocket_schema
    schema = coerce_session_metadata_pocket_schema(AESTHETICS_KEY, aesthetics_schema_v1())
    validate_session_metadata_pocket_value(pocket, schema, path=AESTHETICS_KEY)
    for name, value in pocket.items():
        AESTHETICS_SECTIONS[name]['validator'](value, step_ids=step_ids, path=f'{AESTHETICS_KEY}.{name}')
    return pocket


def with_aesthetics(SM=None, **sections):
    """Copy SM and publish sections in the official aesthetics pocket.

    Values remain inert; ordinary SM symbols and C resolve before effective validation.
    Existing sections are preserved when adding or replacing another section.
    """
    if SM is not None and not isinstance(SM, Mapping):
        raise TypeError('SM must be a mapping.')
    unknown = set(sections) - set(AESTHETICS_SECTIONS)
    if unknown:
        raise KeyError(f'{AESTHETICS_KEY} has unknown sections: {sorted(unknown)}')
    result = deepcopy(dict(SM or {}))
    pocket = result.setdefault(AESTHETICS_KEY, {})
    if not isinstance(pocket, dict):
        raise TypeError(f'{AESTHETICS_KEY} must be a mapping.')
    pocket.update(deepcopy(sections))
    return result
