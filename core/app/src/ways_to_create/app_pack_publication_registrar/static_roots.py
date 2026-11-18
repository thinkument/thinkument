"""Aggregate explicit family static roots; identical reused mounts occur once."""
from dataclasses import replace

try:
    from authoring_funneling.examples.metal.publication import shared_static_roots_v1 as metal_roots
    from authoring_funneling.examples.crystal.publication import shared_static_roots_v1 as crystal_roots
    STATIC_ROOT_PROVIDERS = (metal_roots, crystal_roots)
except ImportError:
    STATIC_ROOT_PROVIDERS = ()

def shared_static_roots_v1():
    roots = {}
    for provider in STATIC_ROOT_PROVIDERS:
        for spec in provider():
            spec = replace(spec, path=spec.path.resolve(), logical_prefix=spec.logical_prefix.strip().strip('/'))
            existing = roots.get(spec.logical_prefix)
            if existing is not None and (existing.path, existing.opinionation_module) != (spec.path, spec.opinionation_module):
                raise ValueError(f'Conflicting static mount {spec.logical_prefix!r}.')
            roots.setdefault(spec.logical_prefix, spec)
    return tuple(roots.values())
