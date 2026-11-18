"""Inert authoring AST. Only D.sugar enables interpretation of dollar syntax."""
from copy import deepcopy
from .types import CompilationError

def node(e): return deepcopy(e) if type(e) is dict and 'op' in e else D.value(e)

class D:
    @staticmethod
    def value(value): return {'op': 'value', 'value': deepcopy(value)}
    @staticmethod
    def ref(source, *path): return {'op': 'ref', 'source': source, 'path': list(path)}
    @staticmethod
    def item(*path): return {'op': 'item', 'path': list(path)}
    @staticmethod
    def outer(*path, levels=1): return {'op': 'outer', 'path': list(path), 'levels': levels}
    @staticmethod
    def text(*parts): return {'op': 'text', 'parts': [node(x) for x in parts]}
    @staticmethod
    def list(*items): return {'op': 'list', 'items': [node(x) for x in items]}
    @staticmethod
    def dict(fields): return {'op': 'dict', 'fields': {k: node(v) for k, v in fields.items()}}
    @staticmethod
    def map(sequence, body): return {'op': 'map', 'sequence': node(sequence), 'body': node(body)}
    @staticmethod
    def filter(sequence, predicate): return {'op': 'filter', 'sequence': node(sequence), 'predicate': node(predicate)}
    @staticmethod
    def cond(test, then, else_): return {'op': 'cond', 'test': node(test), 'then': node(then), 'else': node(else_)}
    @staticmethod
    def default(value, fallback): return {'op': 'default', 'value': node(value), 'fallback': node(fallback)}
    @staticmethod
    def eq(left, right): return _binary('eq', left, right)
    @staticmethod
    def neq(left, right): return _binary('neq', left, right)
    @staticmethod
    def lt(left, right): return _binary('lt', left, right)
    @staticmethod
    def lte(left, right): return _binary('lte', left, right)
    @staticmethod
    def gt(left, right): return _binary('gt', left, right)
    @staticmethod
    def gte(left, right): return _binary('gte', left, right)
    @staticmethod
    def and_(*args): return {'op': 'and', 'args': [node(x) for x in args]}
    @staticmethod
    def or_(*args): return {'op': 'or', 'args': [node(x) for x in args]}
    @staticmethod
    def not_(arg): return _unary('not', arg)
    @staticmethod
    def in_(item, collection): return {'op': 'in', 'item': node(item), 'collection': node(collection)}
    @staticmethod
    def add(left, right): return _binary('add', left, right)
    @staticmethod
    def sub(left, right): return _binary('sub', left, right)
    @staticmethod
    def mul(left, right): return _binary('mul', left, right)
    @staticmethod
    def div(left, right): return _binary('div', left, right)
    @staticmethod
    def mod(left, right): return _binary('mod', left, right)
    @staticmethod
    def neg(arg): return _unary('neg', arg)
    @staticmethod
    def size(value): return {'op': 'size', 'value': node(value)}
    @staticmethod
    def index(sequence, index): return {'op': 'index', 'sequence': node(sequence), 'index': node(index)}
    @staticmethod
    def slice(sequence, start, end=None): return {'op': 'slice', 'sequence': node(sequence), 'start': node(start), 'end': node(end)}
    @staticmethod
    def merge(*dicts): return {'op': 'merge', 'dicts': [node(x) for x in dicts]}
    @staticmethod
    def to_str(value): return {'op': 'to_str', 'value': node(value)}
    @staticmethod
    def to_int(value): return {'op': 'to_int', 'value': node(value)}
    @staticmethod
    def to_float(value): return {'op': 'to_float', 'value': node(value)}
    @staticmethod
    def sum(sequence): return {'op': 'sum', 'sequence': node(sequence)}
    @staticmethod
    def any(sequence): return {'op': 'any', 'sequence': node(sequence)}
    @staticmethod
    def all(sequence): return {'op': 'all', 'sequence': node(sequence)}
    @staticmethod
    def min(sequence): return {'op': 'min', 'sequence': node(sequence)}
    @staticmethod
    def max(sequence): return {'op': 'max', 'sequence': node(sequence)}
    @staticmethod
    def sugar(expression): return desugar_node(expression)

def _binary(op, left, right): return {'op': op, 'left': node(left), 'right': node(right)}
def _unary(op, arg): return {'op': op, 'arg': node(arg)}
_SUGAR_BINARY = frozenset('eq neq lt lte gt gte in add sub mul div mod default'.split())
_SUGAR_UNARY = frozenset('not neg size to_str to_int to_float sum any all min max'.split())
_SUGAR_VARIADIC = frozenset('text list and or merge'.split())

def desugar_node(expression, path=()):
    """Translate one explicitly opted-in sugar tree; $value suppresses recursion."""
    if type(expression) is str and expression.startswith('$'):
        bits = expression[1:].split('.')
        if not all(bits): raise CompilationError('invalid_sugar', path, 'dotted path', expression)
        if bits[0] == 'item': return D.item(*bits[1:])
        if bits[0] == 'outer': return D.outer(*bits[1:])
        if bits[0].startswith('outer') and bits[0][5:].isdigit():
            return D.outer(*bits[1:], levels=int(bits[0][5:]))
        return D.ref(bits[0], *bits[1:])
    if type(expression) is dict:
        if 'op' in expression: return node(expression)
        if len(expression) != 1: return D.value(expression)
        operator, value = next(iter(expression.items()))
        if type(operator) is not str or not operator.startswith('$'): return D.value(expression)
        op = operator[1:]
        if op == 'value': return D.value(value)
        if op == 'dict':
            if type(value) is not dict or not all(type(k) is str for k in value):
                raise CompilationError('invalid_sugar', path, '$dict object', type(value).__name__)
            return D.dict({k: desugar_node(v, (*path, k)) for k, v in value.items()})
        if op in _SUGAR_VARIADIC:
            if type(value) is not list: raise CompilationError('invalid_sugar', path, 'array', type(value).__name__)
            parts = [desugar_node(v, (*path, i)) for i, v in enumerate(value)]
            return {'op': op, ('parts' if op == 'text' else 'items' if op == 'list' else 'args' if op in ('and', 'or') else 'dicts'): parts}
        if op in _SUGAR_BINARY:
            if type(value) is not list or len(value) != 2:
                raise CompilationError('invalid_sugar', path, 'two-element array', type(value).__name__)
            a, b = (desugar_node(v, (*path, i)) for i, v in enumerate(value))
            if op == 'in': return D.in_(a, b)
            if op == 'default': return D.default(a, b)
            return _binary(op, a, b)
        if op in _SUGAR_UNARY:
            a = desugar_node(value, (*path, op))
            return ({'op': op, 'sequence': a} if op in ('sum', 'any', 'all', 'min', 'max')
                    else {'op': op, 'value': a} if op in ('size', 'to_str', 'to_int', 'to_float')
                    else _unary(op, a))
        if op in ('map', 'filter', 'cond', 'slice'):
            length = 3 if op in ('cond', 'slice') else 2
            if type(value) is not list or len(value) != length:
                raise CompilationError('invalid_sugar', path, f'{length}-element array', type(value).__name__)
            parts = [desugar_node(v, (*path, i)) for i, v in enumerate(value)]
            if op == 'map': return D.map(*parts)
            if op == 'filter': return D.filter(*parts)
            if op == 'cond': return D.cond(*parts)
            return D.slice(*parts)
        if op in ('ref', 'item', 'outer'):
            if type(value) is not list: raise CompilationError('invalid_sugar', path, 'path array', type(value).__name__)
            if op == 'ref':
                if not value: raise CompilationError('invalid_sugar', path)
                return D.ref(value[0], *value[1:])
            if op == 'item': return D.item(*value)
            return D.outer(*value)
        raise CompilationError('invalid_sugar', path, 'recognized $operator', operator)
    return D.value(expression)
