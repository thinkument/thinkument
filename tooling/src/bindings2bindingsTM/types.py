"""Finite immutable structural schemas; no coercion or application dependencies."""
from dataclasses import dataclass, field
from functools import lru_cache
import math
from types import MappingProxyType

Str, Int, Float, Bool = str, int, float, bool

class BindingError(ValueError):
    """Stable, JSON-compatible error details for public boundaries."""
    def __init__(self, code, path=(), expected=None, actual=None):
        self.details = dict(code=code, path=list(path), expected=expected, actual=actual)
        super().__init__(f'{code} at {list(path)}: expected {expected}, got {actual}')

class CompilationError(BindingError): pass
class RuntimeValueError(BindingError): pass

@dataclass(frozen=True)
class Schema:
    kind: str
    item: 'Schema | None' = None
    fields: tuple = ()
    _field_map: object = field(init=False, repr=False, compare=False, hash=False)
    def __post_init__(self): object.__setattr__(self, '_field_map', MappingProxyType(dict(self.fields)))
    def field_type(self, key): return self._field_map[key]
    def __copy__(self): return self
    def __deepcopy__(self, memo): return self
    def to_json(self):
        result = {'kind': self.kind}
        if self.item is not None: result['item'] = self.item.to_json()
        if self.kind == 'dict': result['fields'] = {k: v.to_json() for k, v in self.fields}
        return result

Any = Schema('any')
def Nullable(t): return Schema('nullable', normalize(t))
def List(t): return Schema('list', normalize(t))
def Map(t): return Schema('map', normalize(t))
def Promise(t): return Schema('promise', normalize(t))
def Dict(fields): return normalize({'kind': 'dict', 'fields': fields})

def normalize(raw, _active=None):
    active = set() if _active is None else _active
    if len(active) >= 64: raise CompilationError('schema_nesting_limit', expected=64, actual=len(active))
    if isinstance(raw, Schema):
        try: raw = raw.to_json()
        except (AttributeError, TypeError, RecursionError, ValueError) as exc: raise CompilationError('invalid_schema') from exc
    for cls, kind in ((str, 'str'), (int, 'int'), (float, 'float'), (bool, 'bool')):
        if raw is cls: return Schema(kind)
    if type(raw) is not dict or id(raw) in active:
        raise CompilationError('invalid_schema', expected='finite schema', actual=type(raw).__name__)
    active.add(id(raw))
    try:
        kind = raw.get('kind')
        if kind in ('str', 'int', 'float', 'bool', 'any') and set(raw) == {'kind'}: return Schema(kind)
        if kind in ('nullable', 'list', 'map', 'promise') and set(raw) == {'kind', 'item'}:
            item = normalize(raw['item'], active)
            if kind == 'nullable' and item.kind == 'nullable': return item
            return Schema(kind, item)
        if kind == 'dict' and set(raw) == {'kind', 'fields'} and type(raw['fields']) is dict:
            if not all(type(k) is str for k in raw['fields']): raise CompilationError('invalid_field_name')
            return Schema(kind, fields=tuple((k, normalize(v, active)) for k, v in sorted(raw['fields'].items())))
        raise CompilationError('invalid_schema', actual=str(type(raw).__name__))
    finally: active.remove(id(raw))

@lru_cache(maxsize=4096)
def compatible(source, target):
    """Directed subtype check. Int never implicitly fits Float."""
    if source == target: return True
    if target.kind == 'any': return True
    if target.kind == 'nullable': return compatible(source.item if source.kind == 'nullable' else source, target.item)
    if source.kind == 'dict' and target.kind == 'map': return all(compatible(t, target.item) for _, t in source.fields)
    if source.kind == 'promise' and target.kind == 'map' and target.item.kind == 'str': return True
    if source.kind == 'dict' and target.kind == 'promise' and 'ref' in source._field_map: return True
    if source.kind != target.kind: return False
    if source.kind in ('list', 'map', 'promise'): return compatible(source.item, target.item)
    if source.kind == 'dict':
        return (tuple(k for k, _ in source.fields) == tuple(k for k, _ in target.fields)
                and all(compatible(a, b) for (_, a), (_, b) in zip(source.fields, target.fields)))
    return False

def reconcile_common_schema(s1: Schema, s2: Schema, path: tuple = ()) -> Schema:
    s1, s2 = normalize(s1), normalize(s2)
    if compatible(s1, s2): return s2
    if compatible(s2, s1): return s1
    if s1.kind == 'nullable' or s2.kind == 'nullable':
        a = s1.item if s1.kind == 'nullable' else s1
        b = s2.item if s2.kind == 'nullable' else s2
        return Nullable(reconcile_common_schema(a, b, path))
    if s1.kind == s2.kind and s1.kind in ('list', 'map', 'promise'):
        return Schema(s1.kind, reconcile_common_schema(s1.item, s2.item, path))

    if s1.kind == s2.kind == 'dict' and set(s1._field_map) == set(s2._field_map):
        return Dict({k: reconcile_common_schema(v, s2._field_map[k], (*path, k)) for k, v in s1.fields})
    if s1.kind in ('dict', 'map') and s2.kind in ('dict', 'map'):
        types = ([v for _, v in s1.fields] if s1.kind == 'dict' else [s1.item]) + ([v for _, v in s2.fields] if s2.kind == 'dict' else [s2.item])
        if types:
            common = types[0]
            for t in types[1:]: common = reconcile_common_schema(common, t, path)
            return Map(common)
    raise CompilationError('incompatible_branches', path, s1.to_json(), s2.to_json())

def merge_dict_schemas(*schemas: Schema, path: tuple = ()) -> Schema:
    if not schemas: return Dict({})
    merged = {}
    for i, raw in enumerate(schemas):
        schema = normalize(raw)
        if schema.kind != 'dict': raise CompilationError('merge_requires_dict', (*path, i), 'Dict', schema.to_json())
        for key, value in schema.fields:
            if key in merged:
                try: merged[key] = reconcile_common_schema(merged[key], value, (*path, i, key))
                except CompilationError as exc:
                    raise CompilationError('incompatible_merge_key', (*path, i, key), merged[key].to_json(), value.to_json()) from exc
            else: merged[key] = value
    return Dict(merged)

def validate(value, schema, path=()):
    s = normalize(schema) if not isinstance(schema, Schema) else schema
    kind = s.kind
    if kind == 'any': return
    if kind == 'nullable':
        if value is None: return
        return validate(value, s.item, path)
    valid = (kind == 'str' and type(value) is str or
             kind == 'int' and type(value) is int or
             kind == 'bool' and type(value) is bool or
             kind == 'float' and type(value) is float and math.isfinite(value))
    if valid: return
    if kind == 'list' and type(value) is list:
        for i, v in enumerate(value): validate(v, s.item, (*path, i))
        return
    if kind in ('dict', 'map') and type(value) is dict and all(type(k) is str for k in value):
        if kind == 'dict':
            if value.keys() != s._field_map.keys(): raise RuntimeValueError('closed_fields', path, s.to_json(), list(value))
            for k, t in s.fields: validate(value[k], t, (*path, k))
        else:
            for k, v in value.items(): validate(v, s.item, (*path, k))
        return
    if kind == 'promise':
        if hasattr(value, 'ref') and isinstance(getattr(value, 'ref'), str):
            return
        if type(value) is dict and isinstance(value.get('ref'), str):
            if value.get('result') is not None and value.get('status') == 'success':
                validate(value['result'], s.item, (*path, 'result'))
            return
        try:
            validate(value, s.item, path)
            return
        except RuntimeValueError:
            pass
        raise RuntimeValueError('invalid_promise', path, s.to_json(), type(value).__name__)
    if kind == 'float' and type(value) is float: raise RuntimeValueError('nonfinite_float', path, s.to_json(), repr(value))
    raise RuntimeValueError('value_type', path, s.to_json(), type(value).__name__)
