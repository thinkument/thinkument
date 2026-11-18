"""Deterministic, pure, scoped evaluation over selected and validated projections."""
from copy import deepcopy
import json
import math
import re
from .types import validate, RuntimeValueError
_INT_DECIMAL = re.compile(r'[+-]?(?:0|[1-9][0-9]*)\Z', re.ASCII)
_FLOAT_DECIMAL = re.compile(r'[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?\Z', re.ASCII)

def evaluate(plan, values):
    reads = {}
    def read(value, schema, field_path, where):
        if not field_path and type(value) is dict and 'ref' in value and 'status' in value:
            from .types import Promise
            target_schema = schema if schema.kind == 'promise' else Promise(schema)
            validate(value, target_schema, where)
            return value
        for k in field_path:
            if type(value) is not dict or k not in value:
                raise RuntimeValueError('missing_projection', where, schema.to_json(), type(value).__name__)
            value = value[k]
            schema = schema._field_map[k] if schema.kind == 'dict' else schema.item
        validate(value, schema, where)
        return value

    def finite(result, where):
        if type(result) is not float or not math.isfinite(result):
            raise RuntimeValueError('nonfinite_float', where, 'finite Float', repr(result))
        return result
    def run(e, scopes=(), where=()):
        op = e['op']
        def child(key): return run(e[key], scopes, (*where, key))
        if op == 'value': return json.loads(e['value'])
        if op == 'ref':
            key = (e['source'], e['path'])
            if key not in reads:
                if type(values) is not dict or e['source'] not in values:
                    raise RuntimeValueError('missing_source', (e['source'],))
                reads[key] = read(values[e['source']], plan._sources[e['source']], e['path'], (e['source'], *e['path']))
            return deepcopy(reads[key])
        if op in ('item', 'outer'):
            scope = scopes[-1] if op == 'item' else scopes[-1 - e['levels']]
            item_value, schema, cache = scope
            key = e['path']
            if key not in cache:
                label = 'item' if op == 'item' else f'outer{e["levels"]}'
                cache[key] = read(item_value, schema, key, (label, *key))
            return deepcopy(cache[key])
        if op == 'text':
            return ''.join(v if type(v) is str else json.dumps(v, allow_nan=False, separators=(',', ':'))
                           for i, x in enumerate(e['parts'])
                           for v in (run(x, scopes, (*where, 'parts', i)),))
        if op in ('list', 'and', 'or'):
            key = 'items' if op == 'list' else 'args'
            if op == 'list': return [run(x, scopes, (*where, key, i)) for i, x in enumerate(e[key])]
            if op == 'and':
                for i, x in enumerate(e[key]):
                    if not run(x, scopes, (*where, key, i)): return False
                return True
            for i, x in enumerate(e[key]):
                if run(x, scopes, (*where, key, i)): return True
            return False
        if op == 'dict': return {k: run(x, scopes, (*where, 'fields', k)) for k, x in e['fields'].items()}
        if op in ('map', 'filter'):
            sequence = child('sequence'); schema = plan._map_schemas[id(e)]; result = []
            for value in sequence:
                nested = (*scopes, (value, schema, {})); key = 'body' if op == 'map' else 'predicate'
                evaluated = run(e[key], nested, (*where, key))
                if op == 'map': result.append(evaluated)
                elif evaluated: result.append(value)
            return result
        if op == 'cond': return child('then') if child('test') else child('else')
        if op == 'default':
            primary = child('value')
            return primary if primary is not None else child('fallback')
        if op in ('eq', 'neq', 'lt', 'lte', 'gt', 'gte', 'add', 'sub', 'mul', 'div', 'mod'):
            a, b = child('left'), child('right')
            if op == 'eq': return a == b
            if op == 'neq': return a != b
            if op == 'lt': return a < b
            if op == 'lte': return a <= b
            if op == 'gt': return a > b
            if op == 'gte': return a >= b
            if op in ('div', 'mod') and b == 0:
                raise RuntimeValueError('division_by_zero', where, 'nonzero divisor', b)
            try:
                if op == 'add': result = a + b
                elif op == 'sub': result = a - b
                elif op == 'mul': result = a * b
                elif op == 'div': result = a / b
                else: result = a % b
            except (OverflowError, ZeroDivisionError) as exc:
                raise RuntimeValueError('nonfinite_float' if op == 'div' or type(a) is float else 'division_by_zero', where) from exc
            return finite(result, where) if type(result) is float or op == 'div' else result
        if op == 'not': return not child('arg')
        if op == 'in': return child('item') in child('collection')
        if op == 'neg':
            result = -child('arg'); return finite(result, where) if type(result) is float else result
        if op == 'size': return len(child('value'))
        if op == 'index':
            sequence, index = child('sequence'), child('index')
            return sequence[index] if -len(sequence) <= index < len(sequence) else None
        if op == 'slice':
            sequence, start, end = child('sequence'), child('start'), child('end')
            return sequence[start:end]
        if op == 'merge':
            merged = {}
            for i, expr in enumerate(e['dicts']): merged.update(run(expr, scopes, (*where, 'dicts', i)))
            return merged
        if op == 'to_str':
            value = child('value')
            return value if type(value) is str else json.dumps(value, allow_nan=False, separators=(',', ':'))
        if op == 'to_int':
            value = child('value')
            if type(value) is bool: return int(value)
            if type(value) is float:
                if not value.is_integer(): raise RuntimeValueError('nonintegral_float', where, 'exact integral Float', value)
                return int(value)
            if not _INT_DECIMAL.fullmatch(value):
                raise RuntimeValueError('invalid_numeric_cast', where, 'decimal integer string', value)
            try: return int(value, 10)
            except ValueError as exc:
                raise RuntimeValueError('invalid_numeric_cast', where, 'decimal integer string', 'too long') from exc
        if op == 'to_float':
            value = child('value')
            if type(value) is str:
                if not _FLOAT_DECIMAL.fullmatch(value):
                    raise RuntimeValueError('invalid_numeric_cast', where, 'decimal float string', value)
                try: converted = float(value)
                except ValueError as exc:
                    raise RuntimeValueError('invalid_numeric_cast', where, 'decimal float string', value) from exc
                return finite(converted, where)
            try: return finite(float(value), where)
            except OverflowError as exc:
                raise RuntimeValueError('nonfinite_float', where, 'finite Float', 'integer too large') from exc
        if op in ('sum', 'any', 'all', 'min', 'max'):
            sequence = child('sequence')
            if op == 'sum':
                is_float = plan._map_schemas[id(e)].kind == 'float'
                result = sum(sequence, 0.0 if is_float else 0)
                return finite(result, where) if is_float else result
            if op == 'any': return any(sequence)
            if op == 'all': return all(sequence)
            if op == 'min': return min(sequence) if sequence else None
            return max(sequence) if sequence else None
        raise RuntimeValueError('invalid_instruction', where, actual=op)
    return run(plan._expression)
