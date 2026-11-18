"""Explicit deterministic projection and validation of Metal browser metadata."""
from functools import lru_cache
from .static_assets import STATIC_ROOT

from .browser_exports import browser_exports

def browser_catalogue_source():
    """Single generated projection: adding a sheet row needs no hand-maintained JS map."""
    import json
    from ..shared_widgets.micros import micro_catalogue, MICRO_TABLES
    from ..shared_widgets.registry import widget_rows
    micros = {name:row.renderer for name,row in micro_catalogue().items()}
    widgets = {name:row.renderer for name,row in widget_rows().items()}
    for name, renderer in widgets.items():
        if renderer not in browser_exports('widgets.js'):
            raise ValueError(f'Widget {name!r} has no browser renderer {renderer!r}.')
    from .aesthetics import PLACEMENT_AXES, PLACEMENT_DEFAULTS, SEMANTIC_TARGETS, RENDERABLE_PARTS, AESTHETICS_SECTIONS
    return ('// Generated from the Python library sheets; do not edit.\n'
            + 'export const MICRO_RENDERERS = Object.freeze(' + json.dumps(micros,sort_keys=True) + ');\n'
            + 'export const WIDGET_RENDERERS = Object.freeze(' + json.dumps(widgets,sort_keys=True) + ');\n'
            + 'export const PLACEMENT_AXES = Object.freeze(' + json.dumps(PLACEMENT_AXES,sort_keys=True) + ');\n'
            + 'export const MICRO_TABLES = Object.freeze(' + json.dumps({r.definition.name: t.id for t in MICRO_TABLES for r in t.rows},sort_keys=True) + ');\n'
            + 'export const SEMANTIC_TARGETS = Object.freeze(' + json.dumps(SEMANTIC_TARGETS,sort_keys=True) + ');\n'
            + 'export const RENDERABLE_PARTS = Object.freeze(' + json.dumps(RENDERABLE_PARTS) + ');\n'
            + 'export const AESTHETICS_SECTIONS = Object.freeze(' + json.dumps({name: row['browser'] for name,row in AESTHETICS_SECTIONS.items()},sort_keys=True) + ');\n'
            + 'export const PLACEMENT_DEFAULTS = Object.freeze(' + json.dumps(PLACEMENT_DEFAULTS,sort_keys=True) + ');\n')


@lru_cache(maxsize=1)
def validate_browser_catalogue_v1():
    if (STATIC_ROOT/'catalogue.js').read_text() != browser_catalogue_source():
        raise ValueError('Browser catalogue is stale; run python -m authoring_funneling.examples.metal.shared_rendering.catalogue --export-browser.')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--export-browser', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.export_browser:
        (STATIC_ROOT / 'catalogue.js').write_text(browser_catalogue_source())
    else:
        validate_browser_catalogue_v1()
