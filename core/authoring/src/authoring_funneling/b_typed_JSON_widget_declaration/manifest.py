"""Finite JSON declarations; all expression typing remains owned by b2b."""
from copy import deepcopy
import json
import re
from bindings2bindingsTM import Str, Int, Float, Bool, Dict, List, Map, Nullable, normalize
from JSONfnchainTM import FlowCompilationError

PRIMITIVES = {'str': Str, 'int': Int, 'float': Float, 'bool': Bool}

def fail(message, path=()):
    raise FlowCompilationError('invalid_widget_manifest', path, message)

def normalize_port_schema_v1(raw):
    if isinstance(raw, str):
        if raw.endswith('?'):
            return Nullable(normalize_port_schema_v1(raw[:-1]))
        if raw not in PRIMITIVES:
            fail('Unknown primitive type: ' + raw)
        return normalize(PRIMITIVES[raw])
    if type(raw) is list and len(raw) == 1:
        return List(normalize_port_schema_v1(raw[0]))
    if type(raw) is dict:
        if raw.get('kind') == 'promise' or raw.get('type') == 'promise':
            from bindings2bindingsTM import Promise
            return Promise(normalize_port_schema_v1(raw['item']))
        if 'kind' in raw:
            return normalize(raw)
        if raw.get('type') in ('nullable', 'list') and set(raw) == {'type', 'item'}:
            return (Nullable if raw['type'] == 'nullable' else List)(normalize_port_schema_v1(raw['item']))
        if raw.get('type') == 'map' and set(raw) == {'type', 'key', 'value'}:
            if raw['key'] != 'str':
                fail('Map keys must be strings')
            return Map(normalize_port_schema_v1(raw['value']))
        return Dict({k: normalize_port_schema_v1(v) for k, v in raw.items()})
    fail('Expected a JSON schema')

def normalize_manifest_v1(manifest):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: fail('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    try:
        encoded = manifest if isinstance(manifest, str) else json.dumps(manifest, allow_nan=False)
        if len(encoded.encode()) > 1_000_000: fail('Manifest exceeds 1 MB')
        result = json.loads(encoded, object_pairs_hook=unique,
                            parse_constant=lambda _: fail('Nonfinite JSON'))
    except (ValueError, TypeError, RecursionError) as exc:
        fail('Manifest must be finite JSON: ' + str(exc))
    if type(result) is not dict: fail('Manifest must be an object')
    if result.get('kind') != 'json_widget_v1': fail('Expected kind json_widget_v1')
    if not isinstance(result.get('name'), str) or not re.fullmatch(r'[A-Za-z_][\w.]*', result['name']):
        fail('Widget name must be an identifier')
    if set(result) - {'kind', 'name', 'title', 'declaration', 'signals'}:
        fail('Unknown manifest field')
    signals = result.get('signals')
    if type(signals) is not dict or not {'mount', 'fill'} <= signals.keys():
        fail('signals requires mount and fill')
    for name, flow in signals.items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name) or type(flow) is not dict:
            fail('Invalid signal name or definition', ('signals', name))
        if set(flow) - {'steps', 'returns', 'done', 'reexplode', 'outputs', 'keep', 'execution'}:
            fail('Unknown signal field', ('signals', name))
        execution_mode = flow.get('execution', 'auto')
        if execution_mode not in ('auto', 'sync', 'async'):
            fail('execution must be one of: auto, sync, async', ('signals', name))
        if 'returns' in flow and set(flow) - {'steps', 'returns', 'execution'}:
            fail('Outcome must be inside returns or inline, not both', ('signals', name))
        outcome = flow.get('returns', {k: v for k, v in flow.items() if k not in ('steps', 'execution')})
        signals[name] = {'steps': flow.get('steps', []), 'returns': outcome, 'execution': execution_mode}
    declaration = result.setdefault('declaration', {})
    if type(declaration) is not dict or set(declaration) - {'args', 'inputs', 'outputs', 'fills', 'signal'}:
        fail('Invalid declaration fields')
    for group in ('args', 'inputs', 'outputs'):
        declaration.setdefault(group, {})
        if type(declaration[group]) is not dict: fail(group + ' must be an object')
    for port, raw in declaration['outputs'].items():
        norm = normalize_port_schema_v1(raw)
        if norm.kind not in ('dict', 'promise'):
            fail('Output ports require closed records or Promise[T]', ('outputs', port))
        if norm.kind == 'promise' and norm.item.kind != 'dict':
            fail('Promise output ports require closed record payload', ('outputs', port))
    return result

validate_manifest_grammar_v1 = normalize_manifest_v1
