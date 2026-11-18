"""Statically verified portable expressions; caches never contain source values."""
from functools import lru_cache
import json
from types import MappingProxyType
from .types import (Schema, normalize, compatible, reconcile_common_schema,
                    merge_dict_schemas, CompilationError, RuntimeValueError, validate)
from .expressions import node

VERSION = 2
V1_OPS = frozenset(('value', 'ref', 'item', 'text', 'list', 'dict', 'map'))
fields = {
    'value': {'value'}, 'ref': {'source', 'path'}, 'item': {'path'},
    'outer': {'path', 'levels'},
    'text': {'parts'}, 'list': {'items'}, 'dict': {'fields'},
    'map': {'sequence', 'body'},
    'cond': {'test', 'then', 'else'}, 'default': {'value', 'fallback'},
    'eq': {'left', 'right'}, 'neq': {'left', 'right'},
    'lt': {'left', 'right'}, 'lte': {'left', 'right'},
    'gt': {'left', 'right'}, 'gte': {'left', 'right'},
    'and': {'args'}, 'or': {'args'}, 'not': {'arg'},
    'in': {'item', 'collection'},
    'add': {'left', 'right'}, 'sub': {'left', 'right'},
    'mul': {'left', 'right'}, 'div': {'left', 'right'},
    'mod': {'left', 'right'}, 'neg': {'arg'},
    'size': {'value'}, 'index': {'sequence', 'index'},
    'slice': {'sequence', 'start', 'end'},
    'filter': {'sequence', 'predicate'}, 'merge': {'dicts'},
    'to_str': {'value'}, 'to_int': {'value'}, 'to_float': {'value'},
    'sum': {'sequence'}, 'any': {'sequence'}, 'all': {'sequence'},
    'min': {'sequence'}, 'max': {'sequence'},
}
assert len(fields) == 39

def _dead_json(v, path=(), active=None):
    active = set() if active is None else active
    if len(active) >= 128: raise CompilationError('expression_nesting_limit', path, 128, len(active))
    if type(v) in (str, int, bool) or v is None: return
    if type(v) is float:
        from math import isfinite
        if isfinite(v): return
    if type(v) not in (list, dict) or id(v) in active:
        raise CompilationError('nonportable_expression', path, actual=type(v).__name__)
    active.add(id(v))
    try:
        if type(v) is dict:
            if not all(type(k) is str for k in v): raise CompilationError('invalid_field_name', path)
            for k, x in v.items(): _dead_json(x, (*path, k), active)
        else:
            for i, x in enumerate(v): _dead_json(x, (*path, i), active)
    finally: active.remove(id(v))

def _literal_type(v, hint, path):
    if hint and hint.kind == 'nullable' and v is not None: hint = hint.item
    if v is None:
        if hint and hint.kind == 'nullable': return hint
        raise CompilationError('ambiguous_null', path)
    for cls, kind in ((str, 'str'), (bool, 'bool'), (int, 'int'), (float, 'float')):
        if type(v) is cls:
            s = Schema(kind)
            try: validate(v, s, path)
            except RuntimeValueError as exc:
                raise CompilationError(exc.details['code'], path, actual=exc.details['actual']) from exc
            return s
    if type(v) is list:
        h = hint.item if hint and hint.kind == 'list' else None
        return _list_type([_literal_type(x, h, (*path, i)) for i, x in enumerate(v)], h, path)
    if type(v) is dict and all(type(k) is str for k in v):
        hints = dict(hint.fields) if hint and hint.kind == 'dict' else {}
        field_hint = hint.item if hint and hint.kind == 'map' else None
        return Schema('dict', fields=tuple((k, _literal_type(x, field_hint or hints.get(k), (*path, k)))
                                            for k, x in sorted(v.items())))
    raise CompilationError('invalid_literal', path, actual=type(v).__name__)

def _list_type(items, hint, path):
    if not items:
        if hint is None: raise CompilationError('ambiguous_empty_list', path)
        return Schema('list', hint)
    t = hint or items[0]
    for s in items:
        if compatible(s, t): continue
        if hint is None and compatible(t, s): t = s
        else: raise CompilationError('heterogeneous_list', path, t.to_json(), s.to_json())
    return Schema('list', t)

def _project(schema, field_path, where):
    if type(field_path) is not list or not all(type(k) is str for k in field_path):
        raise CompilationError('invalid_path', where)
    for k in field_path:
        if schema.kind == 'dict' and k in schema._field_map: schema = schema._field_map[k]
        elif schema.kind == 'map': schema = schema.item
        else: raise CompilationError('unknown_field', where, actual=k)
    return schema

def _require_type(schema, kinds, path, code='operand_type'):
    if schema.kind not in kinds: raise CompilationError(code, path, list(kinds), schema.to_json())

def _check(e, sources, hint=None, scopes=(), path=(), deps=None, sequence_schemas=None, version=VERSION):
    if type(e) is not dict: raise CompilationError('invalid_expression', path)
    op = e.get('op')
    if type(op) is not str or op not in fields or (version == 1 and op not in V1_OPS) or set(e) != fields[op] | {'op'}:
        raise CompilationError('invalid_expression', path, actual=op if type(op) is str else type(op).__name__)
    def check(key, subhint=None):
        return _check(e[key], sources, subhint, scopes, (*path, key), deps, sequence_schemas, version)
    def check_array(key, subhint=None):
        if type(e[key]) is not list:
            raise CompilationError('invalid_expression', (*path, key), 'array', type(e[key]).__name__)
        return [_check(v, sources, subhint, scopes, (*path, key, i), deps, sequence_schemas, version)
                for i, v in enumerate(e[key])]
    inner_hint = hint.item if hint and hint.kind == 'nullable' else hint
    def empty_sequence_literal():
        seq = e.get('sequence')
        return type(seq) is dict and ((seq.get('op') == 'list' and seq.get('items') == []) or
                                       (seq.get('op') == 'value' and seq.get('value') == []))
    if op == 'value': return _literal_type(e['value'], hint, (*path, 'value'))
    if op in ('ref', 'item', 'outer'):
        if op == 'ref':
            source = e['source']
            if type(source) is not str or source not in sources:
                raise CompilationError('unknown_source', path, actual=source if type(source) is str else type(source).__name__)
            base = sources[source]
        elif op == 'item':
            if not scopes: raise CompilationError('item_outside_map', path)
            base = scopes[-1]
        else:
            levels = e['levels']
            if type(levels) is not int or levels < 1:
                raise CompilationError('invalid_outer_level', path, 'positive integer', levels)
            if len(scopes) < 2: raise CompilationError('outer_outside_map', path)
            if levels >= len(scopes): raise CompilationError('invalid_outer_level', path, len(scopes) - 1, levels)
            base = scopes[-levels - 1]
        projected = _project(base, e['path'], path)
        if op == 'ref' and deps is not None: deps.add((e['source'], tuple(e['path'])))
        return projected
    if op in ('text', 'list'):
        key = 'parts' if op == 'text' else 'items'
        h = inner_hint.item if inner_hint and inner_hint.kind == 'list' and op == 'list' else None
        ts = check_array(key, h)
        if op == 'list': return _list_type(ts, h, path)
        if any(t.kind not in ('str', 'int', 'float', 'bool') for t in ts):
            raise CompilationError('text_requires_scalar', path)
        return Schema('str')
    if op == 'dict':
        if type(e['fields']) is not dict or not all(type(k) is str for k in e['fields']):
            raise CompilationError('invalid_expression', path)
        hints = dict(inner_hint.fields) if inner_hint and inner_hint.kind == 'dict' else {}
        map_hint = inner_hint.item if inner_hint and inner_hint.kind == 'map' else None
        return Schema('dict', fields=tuple((k, _check(v, sources, map_hint or hints.get(k), scopes,
                                                      (*path, 'fields', k), deps, sequence_schemas, version))
                                            for k, v in sorted(e['fields'].items())))
    if op in ('map', 'filter'):
        seq = check('sequence', inner_hint if op == 'filter' and empty_sequence_literal() and inner_hint and inner_hint.kind == 'list' else None)
        _require_type(seq, ('list',), path, 'map_requires_list' if op == 'map' else 'filter_requires_list')
        if sequence_schemas is not None: sequence_schemas[id(e)] = seq.item
        body_key = 'body' if op == 'map' else 'predicate'
        h = inner_hint.item if inner_hint and inner_hint.kind == 'list' and op == 'map' else None
        body_type = _check(e[body_key], sources, h, (*scopes, seq.item), (*path, body_key), deps, sequence_schemas, version)
        if op == 'filter':
            _require_type(body_type, ('bool',), (*path, 'predicate'))
            return seq
        return Schema('list', body_type)
    if op == 'cond':
        _require_type(check('test'), ('bool',), (*path, 'test'))
        a, b = check('then', hint), check('else', hint)
        return reconcile_common_schema(a, b, path)
    if op == 'default':
        fallback = check('fallback', inner_hint)
        if fallback.kind == 'nullable': raise CompilationError('default_requires_nonnull_fallback', (*path, 'fallback'))
        primary = check('value', Schema('nullable', fallback))
        if primary.kind != 'nullable':
            raise CompilationError('default_requires_nullable', (*path, 'value'), 'Nullable(T)', primary.to_json())
        if not compatible(fallback, primary.item):
            raise CompilationError('incompatible_branches', path, primary.item.to_json(), fallback.to_json())
        return primary.item
    if op in ('eq', 'neq', 'lt', 'lte', 'gt', 'gte', 'add', 'sub', 'mul', 'div', 'mod'):
        a, b = check('left'), check('right')
        if a.kind in ('int', 'float') and b.kind in ('int', 'float') and a.kind != b.kind:
            raise CompilationError('mixed_numeric_types', path, a.to_json(), b.to_json())
        if op in ('eq', 'neq'):
            try: reconcile_common_schema(a, b, path)
            except CompilationError as exc:
                raise CompilationError('incomparable_types', path, a.to_json(), b.to_json()) from exc
            return Schema('bool')
        if op in ('lt', 'lte', 'gt', 'gte'):
            if a.kind != b.kind or a.kind not in ('int', 'float', 'str'):
                raise CompilationError('comparison_types', path, a.to_json(), b.to_json())
            return Schema('bool')
        if a.kind != b.kind or a.kind not in ('int', 'float'):
            raise CompilationError('arithmetic_types', path, a.to_json(), b.to_json())
        if op == 'mod' and a.kind != 'int': raise CompilationError('arithmetic_types', path, 'Int, Int', a.to_json())
        return Schema('float' if op == 'div' else a.kind)
    if op in ('and', 'or'):
        for i, t in enumerate(check_array('args')): _require_type(t, ('bool',), (*path, 'args', i))
        return Schema('bool')
    if op == 'not':
        _require_type(check('arg'), ('bool',), (*path, 'arg'))
        return Schema('bool')
    if op == 'in':
        element, collection = check('item'), check('collection')
        if collection.kind == 'list':
            if not compatible(element, collection.item):
                raise CompilationError('membership_types', path, collection.item.to_json(), element.to_json())
        elif collection.kind in ('map', 'dict'):
            _require_type(element, ('str',), (*path, 'item'), 'membership_types')
        else: raise CompilationError('membership_types', path, 'List, Map, Dict', collection.to_json())
        return Schema('bool')
    if op == 'neg':
        t = check('arg'); _require_type(t, ('int', 'float'), path, 'arithmetic_types'); return t
    if op == 'size':
        _require_type(check('value'), ('str', 'list', 'map', 'dict'), path); return Schema('int')
    if op == 'index':
        item_hint = hint.item if hint and hint.kind == 'nullable' else None
        seq = check('sequence', Schema('list', item_hint) if item_hint and empty_sequence_literal() else None)
        idx = check('index')
        _require_type(seq, ('list',), path, 'index_requires_list')
        _require_type(idx, ('int',), (*path, 'index'))
        return Schema('nullable', seq.item)
    if op == 'slice':
        seq = check('sequence', inner_hint if empty_sequence_literal() and inner_hint and inner_hint.kind == 'list' else None)
        start = check('start'); end = check('end', Schema('nullable', Schema('int')))
        _require_type(seq, ('list', 'str'), path, 'slice_requires_sequence')
        _require_type(start, ('int',), (*path, 'start'))
        if not compatible(end, Schema('nullable', Schema('int'))):
            raise CompilationError('slice_end_type', (*path, 'end'), 'Nullable(Int)', end.to_json())
        return seq
    if op == 'merge': return merge_dict_schemas(*check_array('dicts'), path=path)
    if op in ('to_str', 'to_int', 'to_float'):
        t = check('value')
        kinds = {'to_str': ('str', 'int', 'float', 'bool'), 'to_int': ('str', 'float', 'bool'),
                 'to_float': ('str', 'int')}[op]
        _require_type(t, kinds, path, 'cast_type')
        return Schema({'to_str': 'str', 'to_int': 'int', 'to_float': 'float'}[op])
    if op in ('sum', 'any', 'all', 'min', 'max'):
        item_hint = (Schema('bool') if op in ('any', 'all') else
                     hint.item if op in ('min', 'max') and hint and hint.kind == 'nullable' else
                     inner_hint if op == 'sum' and inner_hint and inner_hint.kind in ('int', 'float') else None)
        seq = check('sequence', Schema('list', item_hint) if item_hint and empty_sequence_literal() else None)
        if seq.kind != 'list': raise CompilationError('unsupported_aggregation', path, 'List(T)', seq.to_json())
        allowed = ('int', 'float') if op == 'sum' else ('bool',) if op in ('any', 'all') else ('int', 'float', 'str')
        if seq.item.kind not in allowed: raise CompilationError('unsupported_aggregation', path, list(allowed), seq.item.to_json())
        if sequence_schemas is not None: sequence_schemas[id(e)] = seq.item
        if op in ('any', 'all'): return Schema('bool')
        return Schema('nullable', seq.item) if op in ('min', 'max') else seq.item
    raise CompilationError('invalid_expression', path, actual=op)

def _portable(expression):
    try:
        authored = node(expression)
        _dead_json(authored)
        return json.loads(json.dumps(authored, allow_nan=False))
    except CompilationError: raise
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise CompilationError('nonportable_expression') from exc

def infer_expression_type(source_types: dict[str, Schema], expression, *, expected_type: Schema | None = None) -> Schema:
    if type(source_types) is not dict or not all(type(k) is str for k in source_types):
        raise CompilationError('invalid_source_types')
    sources = {k: normalize(v) for k, v in source_types.items()}
    expected = normalize(expected_type) if expected_type is not None else None
    actual = _check(_portable(expression), sources, expected)
    if expected is not None and not compatible(actual, expected):
        raise CompilationError('target_type', (), expected.to_json(), actual.to_json())
    return actual

def _freeze(expr, sequence_schemas, frozen_sequences):
    op = expr['op']; result = {'op': op}
    for key, value in expr.items():
        if key == 'op': continue
        if op == 'value' and key == 'value': result[key] = json.dumps(value, separators=(',', ':'), allow_nan=False)
        elif key in ('path',): result[key] = tuple(value)
        elif key in ('parts', 'items', 'args', 'dicts'):
            result[key] = tuple(_freeze(v, sequence_schemas, frozen_sequences) for v in value)
        elif op == 'dict' and key == 'fields':
            result[key] = MappingProxyType({k: _freeze(v, sequence_schemas, frozen_sequences) for k, v in value.items()})
        elif key in ('body', 'predicate', 'sequence', 'test', 'then', 'else', 'fallback',
                     'left', 'right', 'arg', 'item', 'collection', 'start', 'end', 'index', 'value'):
            result[key] = _freeze(value, sequence_schemas, frozen_sequences)
        else: result[key] = value
    frozen = MappingProxyType(result)
    if op in ('map', 'filter', 'sum', 'any', 'all', 'min', 'max'):
        frozen_sequences[id(frozen)] = sequence_schemas[id(expr)]
    return frozen

class BindingPlan:
    __slots__ = ('_json', '_sources', '_target', '_expression', '_dependencies', '_map_schemas')
    def __init__(self, sources, target, expression, *, _version=VERSION):
        if _version not in (1, 2): raise CompilationError('invalid_recipe_version')
        if type(sources) is not dict: raise CompilationError('invalid_source_types')
        if not all(type(k) is str for k in sources): raise CompilationError('invalid_source_name')
        src = {k: normalize(v) for k, v in sources.items()}
        target = normalize(target); e = _portable(expression); deps, seq_schemas = set(), {}
        actual = _check(e, src, target, deps=deps, sequence_schemas=seq_schemas, version=_version)
        if not compatible(actual, target): raise CompilationError('target_type', (), target.to_json(), actual.to_json())
        frozen_sequences = {}; expression_frozen = _freeze(e, seq_schemas, frozen_sequences)
        self._sources = MappingProxyType(src)
        self._target = target
        self._dependencies = tuple(sorted(deps))
        self._expression = expression_frozen
        self._map_schemas = MappingProxyType(frozen_sequences)
        self._json = json.dumps(dict(version=_version, sources={k: v.to_json() for k, v in sorted(src.items())},
                                     target=target.to_json(), expression=e),
                                sort_keys=True, separators=(',', ':'), allow_nan=False)
    def __setattr__(self, name, value):
        if hasattr(self, name): raise AttributeError('BindingPlan is immutable')
        object.__setattr__(self, name, value)
    @property
    def target_type(self): return self._target
    @property
    def dependencies(self): return self._dependencies
    def to_json(self): return self._json
    @classmethod
    def from_json(cls, serialized):
        if type(serialized) is not str: raise CompilationError('invalid_recipe')
        return _restore(serialized)
    def evaluate(self, source_values):
        from .runtime import evaluate
        return evaluate(self, source_values)

def _object_pairs_unique(pairs):
    result = {}
    for k, v in pairs:
        if k in result: raise ValueError('duplicate JSON object key')
        result[k] = v
    return result

@lru_cache(maxsize=128)
def _restore(serialized):
    try:
        raw = json.loads(serialized, object_pairs_hook=_object_pairs_unique,
                         parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (ValueError, TypeError, RecursionError) as exc: raise CompilationError('invalid_recipe') from exc
    if (type(raw) is not dict or set(raw) != {'version', 'sources', 'target', 'expression'} or
            type(raw['version']) is not int or raw['version'] not in (1, 2) or type(raw['sources']) is not dict):
        raise CompilationError('invalid_recipe')
    return BindingPlan(raw['sources'], raw['target'], raw['expression'], _version=raw['version'])

def compile_binding(source_types, target_type, expression):
    """Compile to v2, requiring an explicit destination schema."""
    return BindingPlan(source_types, target_type, expression)
