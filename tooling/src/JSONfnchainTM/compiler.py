"""Strict flow lowering and static proof, delegating ALL expression work to b2b."""
from difflib import get_close_matches
import json
from types import MappingProxyType
from bindings2bindingsTM import (D, Dict, List, Schema, normalize, compatible,
                                 reconcile_common_schema, compile_binding, infer_expression_type,
                                 CompilationError as B2BCompilationError)
from .errors import FlowCompilationError
from .grammar import (Expression, Block, CallNode, BranchNode, MapNode, LoopNode,
                      ParallelNode, ident, RESERVED, MAX_CONSTRUCT_DEPTH, MAX_FLOW_NODES)
from .vocab import FunctionVocab

VERSION = 1
EMPTY = Dict({})
BOOL = normalize(bool)
INT = normalize(int)

def _exact(obj, required, optional=(), path=()):
    if type(obj) is not dict or not set(required) <= set(obj) or not set(obj) <= set(required) | set(optional):
        raise FlowCompilationError('invalid_grammar', path,
                                   f'Expected required keys {sorted(required)} and optional keys {sorted(optional)}',
                                   expected=sorted(set(required) | set(optional)),
                                   actual=sorted(obj) if type(obj) is dict and all(type(k) is str for k in obj) else type(obj).__name__)

def _lower(value):
    """Only flow JSON object/array construction is handled here. b2b parses every leaf.

    b2b intentionally treats plain dictionaries and arrays as literal under D.sugar;
    flow authoring instead uses plain nested objects as construction syntax. Explicit
    $value protects literal objects and arrays. No dollar token or operator is parsed.
    """
    if type(value) is dict:
        if 'op' in value or (len(value) == 1 and type(next(iter(value))) is str
                             and next(iter(value)).startswith('$')):
            return D.sugar(value)
        return D.dict({key: _lower(sub) for key, sub in value.items()})
    if type(value) is list: return D.list(*(_lower(x) for x in value))
    return D.sugar(value)

def _ref_diagnostic(expr, scope, data):
    code, actual = data['code'], data.get('actual')
    if code == 'unknown_source':
        hit = get_close_matches(str(actual), list(scope), n=1)
        return f"Unknown source {actual!r}." + (f" Did you mean '{hit[0]}'?" if hit else '')
    if code != 'unknown_field': return None
    candidates = []
    def walk(value):
        if type(value) is dict:
            if value.get('op') == 'ref' and value.get('source') in scope:
                schema = scope[value['source']]
                for key in value.get('path', []):
                    if schema.kind == 'dict':
                        if key not in schema._field_map:
                            hit = get_close_matches(str(key), list(schema._field_map), n=1)
                            candidates.append((key, value['source'], hit))
                            break
                        schema = schema._field_map[key]
                    elif schema.kind == 'map': schema = schema.item
                    else: break
            for item in value.values(): walk(item)
        elif type(value) is list:
            for item in value: walk(item)
    walk(expr)
    for key, source, matches in candidates:
        if key == actual:
            return f"Unknown field {key!r} on source {source!r}." + (f" Did you mean '{matches[0]}'?" if matches else '')
    return None

class _Compiler:
    def __init__(self, vocab):
        if not isinstance(vocab, FunctionVocab):
            raise FlowCompilationError('invalid_vocab', message='vocab must be FunctionVocab')
        self.vocab = vocab
        self.contracts = {}
        self.count = 0

    def expr(self, raw, scope, path, expected=None):
        try:
            canonical = _lower(raw)
            schema = infer_expression_type(scope, canonical, expected_type=expected)
            binding = compile_binding(scope, expected or schema, canonical)
            canonical = json.loads(binding.to_json())['expression']
            return Expression(binding, schema, json.dumps(canonical, sort_keys=True, separators=(',', ':'), allow_nan=False))
        except B2BCompilationError as exc:
            detail = exc.details
            message = _ref_diagnostic(canonical, scope, detail) if 'canonical' in locals() else None
            message = message or f'b2b {detail["code"]} at {list(path)}: {str(exc)}'
            raise FlowCompilationError(detail['code'], (*path, *detail['path']), message,
                                       expected=detail['expected'], actual=detail['actual'], cause=exc) from exc
        except (RecursionError, TypeError, ValueError) as exc:
            raise FlowCompilationError('invalid_expression', path, str(exc), cause=exc) from exc

    def steps(self, raw, scope, path, depth=0, worker=False):
        if depth >= MAX_CONSTRUCT_DEPTH:
            raise FlowCompilationError('construct_nesting_limit', path, f'Maximum construct nesting is {MAX_CONSTRUCT_DEPTH}')
        if type(raw) is not list:
            raise FlowCompilationError('invalid_grammar', path, 'steps must be an array')
        visible = dict(scope)
        nodes, canonical = [], []
        for i, raw_node in enumerate(raw):
            where = (*path, i)
            self.count += 1
            if self.count > MAX_FLOW_NODES:
                raise FlowCompilationError('node_count_limit', where, f'Maximum number of nodes is {MAX_FLOW_NODES}')
            if type(raw_node) is not dict:
                raise FlowCompilationError('invalid_grammar', where, 'Each step must be an object')
            name = ident(raw_node.get('id'), (*where, 'id'))
            if name in visible:
                raise FlowCompilationError('duplicate_identifier', where,
                                           f'Step {name!r} shadows a visible source or earlier step')
            if 'fn' in raw_node:
                node, serial, result = self.call(raw_node, visible, where)
            elif 'parallel' in raw_node:
                if worker: raise FlowCompilationError('nested_concurrency', where, 'Concurrent map body cannot contain parallel')
                node, serial, result = self.parallel(raw_node, visible, where)
            elif 'map' in raw_node:
                node, serial, result = self.map(raw_node, visible, where, depth, worker)
            elif 'loop' in raw_node:
                node, serial, result = self.loop(raw_node, visible, where, depth, worker)
            elif 'if' in raw_node or 'branch' in raw_node:
                node, serial, result = self.branch(raw_node, visible, where, depth, worker)
            else:
                raise FlowCompilationError('unknown_construct', where,
                                           f"Step {name!r} must have exactly one of fn, if/branch, map, loop, parallel")
            nodes.append(node); canonical.append(serial); visible[name] = result
        return tuple(nodes), canonical, visible

    def call(self, raw, scope, path):
        _exact(raw, ('id', 'fn'), ('args',), path)
        name = raw['fn']
        entry = self.vocab.resolve(name, path)
        self.contracts[name] = entry.contract()
        args = self.expr(raw.get('args', {}), scope, (*path, 'args'), entry.inputs)
        return (CallNode(raw['id'], name, args),
                {'id': raw['id'], 'fn': name, 'args': args.canonical}, entry.output)

    def block(self, raw, scope, path, depth, worker, common_return=None):
        if type(raw) is list:
            steps = raw; returns = common_return
        else:
            _exact(raw, ('steps',), ('returns',), path)
            if common_return is not None and 'returns' in raw:
                raise FlowCompilationError('invalid_grammar', path, 'Branch returns specified both at node and arm')
            steps = raw['steps']; returns = raw.get('returns', common_return)
        nodes, serial_steps, after = self.steps(steps, scope, (*path, 'steps'), depth + 1, worker)
        expr = self.expr(returns, after, (*path, 'returns')) if returns is not None else None
        serial = {'steps': serial_steps}
        if expr is not None: serial['returns'] = expr.canonical
        return Block(nodes, expr), serial

    def branch(self, raw, scope, path, depth, worker):
        if 'branch' in raw:
            _exact(raw, ('id', 'branch'), (), path)
            body = raw['branch']; _exact(body, ('if', 'then'), ('else', 'returns'), (*path, 'branch'))
        else:
            _exact(raw, ('id', 'if', 'then'), ('else', 'returns'), path)
            body = raw
        pred = self.expr(body['if'], scope, (*path, 'if'), BOOL)
        has_return = 'returns' in body
        explicit_else = 'else' in body
        then, then_serial = self.block(body['then'], scope, (*path, 'then'), depth, worker,
                                       body.get('returns'))
        otherwise, else_serial = self.block(body.get('else', []), scope, (*path, 'else'), depth,
                                             worker, body.get('returns'))
        valued = then.returns is not None or otherwise.returns is not None or has_return
        if valued and (not explicit_else or then.returns is None or otherwise.returns is None):
            raise FlowCompilationError('branch_returns', path,
                'Valued branch requires else and typed returns from both arms (arm blocks or common top-level returns)')
        try:
            result = (reconcile_common_schema(then.returns.schema, otherwise.returns.schema)
                      if valued else EMPTY)
        except B2BCompilationError as exc:
            raise FlowCompilationError('incompatible_branches', path, str(exc), cause=exc) from exc
        return (BranchNode(raw['id'], pred, then, otherwise, valued),
                {'id': raw['id'], 'branch': {'if': pred.canonical, 'then': then_serial, 'else': else_serial}}, result)

    def map(self, raw, scope, path, depth, worker):
        _exact(raw, ('id', 'map'), (), path)
        body = raw['map']
        _exact(body, ('over',), ('item_as', 'parallel', 'max_concurrency', 'steps', 'returns', 'call'), (*path, 'map'))
        use_parallel = body.get('parallel', False)
        if type(use_parallel) is not bool:
            raise FlowCompilationError('invalid_concurrency', path, 'map.parallel must be bool')
        if use_parallel and worker:
            raise FlowCompilationError('nested_concurrency', path, 'Concurrent map body cannot contain another concurrent map')
        limit = body.get('max_concurrency', 8)
        if type(limit) is not int or limit < 1:
            raise FlowCompilationError('invalid_concurrency', path, 'max_concurrency must be positive integer')
        alias = body.get('item_as', 'current')
        ident(alias, (*path, 'map', 'item_as'), reserved=False)
        if alias in RESERVED - {'current'} or (alias != 'current' and alias in scope):
            raise FlowCompilationError('invalid_identifier', path, f'Map alias {alias!r} shadows a visible source or reserved identifier')
        over = self.expr(body['over'], scope, (*path, 'map', 'over'))
        if over.schema.kind != 'list':
            raise FlowCompilationError('map_requires_list', path, 'map.over must infer List(T)')
        local = dict(scope); local['current'] = over.schema.item; local['index'] = INT
        local[alias] = over.schema.item
        single = 'call' in body
        if single:
            if 'steps' in body or 'returns' in body:
                raise FlowCompilationError('invalid_grammar', path, 'map.call cannot be combined with steps/returns')
            _exact(body['call'], ('fn',), ('args',), (*path, 'map', 'call'))
            raw_steps = [{'id': '_call', **body['call']}]
            return_raw = '$_call'
        else:
            if 'steps' not in body or 'returns' not in body:
                raise FlowCompilationError('map_returns', path, 'Multistep map requires steps and returns')
            raw_steps, return_raw = body['steps'], body['returns']
        nodes, serial_steps, end = self.steps(raw_steps, local, (*path, 'map', 'steps'),
                                               depth + 1, worker or use_parallel)
        result_expr = self.expr(return_raw, end, (*path, 'map', 'returns'))
        block = Block(nodes, result_expr)
        serial = {'id': raw['id'], 'map': {'over': over.canonical, 'item_as': alias,
                  'parallel': use_parallel, 'max_concurrency': limit,
                  'steps': serial_steps, 'returns': result_expr.canonical}}
        return MapNode(raw['id'], over, alias, use_parallel, limit, block), serial, List(result_expr.schema)

    def loop(self, raw, scope, path, depth, worker):
        _exact(raw, ('id', 'loop'), (), path)
        body = raw['loop']
        _exact(body, ('init', 'max', 'while', 'steps', 'update'),
               ('state_type', 'on_max', 'returns'), (*path, 'loop'))
        maximum = body['max']; on_max = body.get('on_max', 'raise')
        if type(maximum) is not int or maximum < 0:
            raise FlowCompilationError('invalid_loop_max', path, 'loop.max must be non-negative integer')
        if on_max not in ('raise', 'return_current'):
            raise FlowCompilationError('invalid_on_max', path, 'on_max must be raise or return_current')
        try:
            state_hint = normalize(body['state_type']) if 'state_type' in body else None
        except B2BCompilationError as exc:
            raise FlowCompilationError('invalid_state_type', path, str(exc), cause=exc) from exc
        init = self.expr(body['init'], scope, (*path, 'loop', 'init'), state_hint)
        state_type = state_hint or init.schema
        local = dict(scope); local['state'] = state_type; local['iteration'] = INT
        pred = self.expr(body['while'], local, (*path, 'loop', 'while'), BOOL)
        nodes, serial_steps, after = self.steps(body['steps'], local, (*path, 'loop', 'steps'), depth + 1, worker)
        try:
            update = self.expr(body['update'], after, (*path, 'loop', 'update'), state_type)
        except FlowCompilationError as exc:
            if exc.details['code'] == 'target_type':
                raise FlowCompilationError('loop_state_type', path, 'loop.update must match state schema exactly',
                                           expected=state_type.to_json(), actual=exc.details['actual'], cause=exc) from exc
            raise
        if update.schema != state_type:
            raise FlowCompilationError('loop_state_type', path, 'loop.update must match initial state schema exactly',
                                       expected=state_type.to_json(), actual=update.schema.to_json())
        result_expr = (self.expr(body['returns'], local, (*path, 'loop', 'returns'))
                       if 'returns' in body else None)
        serial = {'id': raw['id'], 'loop': {'init': init.canonical,
                  'state_type': state_type.to_json(), 'max': maximum, 'on_max': on_max,
                  'while': pred.canonical, 'steps': serial_steps, 'update': update.canonical}}
        if result_expr is not None: serial['loop']['returns'] = result_expr.canonical
        return (LoopNode(raw['id'], init, state_type, maximum, on_max, pred,
                         Block(nodes), update, result_expr), serial,
                result_expr.schema if result_expr else state_type)

    def parallel(self, raw, scope, path):
        _exact(raw, ('id', 'parallel'), (), path)
        children = raw['parallel']
        if type(children) is not list:
            raise FlowCompilationError('invalid_grammar', path, 'parallel must be an array of calls')
        calls, serial_calls, fields = [], [], {}
        for i, child in enumerate(children):
            where = (*path, 'parallel', i)
            self.count += 1
            if self.count > MAX_FLOW_NODES:
                raise FlowCompilationError('node_count_limit', where, f'Maximum number of nodes is {MAX_FLOW_NODES}')
            if type(child) is not dict:
                raise FlowCompilationError('invalid_grammar', where, 'parallel children must be calls')
            name = ident(child.get('id'), (*where, 'id'))
            if name in fields or name in scope:
                raise FlowCompilationError('duplicate_identifier', where, f'Child {name!r} shadows another visible name')
            call, serial, output = self.call(child, scope, where)
            calls.append(call); serial_calls.append(serial); fields[name] = output
        return ParallelNode(raw['id'], tuple(calls)), {'id': raw['id'], 'parallel': serial_calls}, Dict(fields)


def _preflight_count(flow):
    """Reject oversized/deep structures before quadratic accumulation of scopes."""
    count = 0
    def scan_steps(steps, depth):
        nonlocal count
        if depth >= MAX_CONSTRUCT_DEPTH:
            raise FlowCompilationError('construct_nesting_limit', message='Construct nesting exceeds 64')
        if type(steps) is not list: return
        for node in steps:
            count += 1
            if count > MAX_FLOW_NODES:
                raise FlowCompilationError('node_count_limit', message='Flow exceeds 10,000 nodes')
            if type(node) is not dict: continue
            if type(node.get('parallel')) is list:
                count += len(node['parallel'])
                if count > MAX_FLOW_NODES:
                    raise FlowCompilationError('node_count_limit', message='Flow exceeds 10,000 nodes')
            if type(node.get('map')) is dict:
                b = node['map']
                if 'call' in b: count += 1
                if count > MAX_FLOW_NODES:
                    raise FlowCompilationError('node_count_limit', message='Flow exceeds 10,000 nodes')
                scan_steps(b.get('steps', []), depth + 1)
            if type(node.get('loop')) is dict:
                scan_steps(node['loop'].get('steps', []), depth + 1)
            b = node.get('branch', node)
            if type(b) is dict and ('if' in b):
                for arm in ('then', 'else'):
                    inner = b.get(arm, [])
                    scan_steps(inner.get('steps', []) if type(inner) is dict else inner, depth + 1)
    scan_steps(flow.get('steps'), 0)

class FlowPlan:
    """Verified immutable flow; JSON recipe contains no callables or live state."""
    __slots__ = ('_json', '_nodes', '_returns', '_sources', '_target', '_contracts')
    def __init__(self, json_string, nodes, returns, sources, target, contracts):
        object.__setattr__(self, '_json', json_string)
        object.__setattr__(self, '_nodes', nodes)
        object.__setattr__(self, '_returns', returns)
        object.__setattr__(self, '_sources', MappingProxyType(dict(sources)))
        object.__setattr__(self, '_target', target)
        object.__setattr__(self, '_contracts', MappingProxyType({
            k: json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False)
            for k, v in contracts.items()}))
    def __setattr__(self, name, value): raise AttributeError('FlowPlan is immutable')
    @property
    def target_type(self): return self._target
    @property
    def function_contracts(self): return json.loads(self._json)['functions']
    def to_json(self): return self._json
    @classmethod
    def from_json(cls, serialized, *, vocab):
        if type(serialized) is not str:
            raise FlowCompilationError('invalid_recipe', message='Recipe must be JSON text')
        def pairs_unique(pairs):
            out = {}
            for key, value in pairs:
                if key in out: raise ValueError(f'Duplicate JSON key: {key}')
                out[key] = value
            return out
        try:
            raw = json.loads(serialized, object_pairs_hook=pairs_unique,
                             parse_constant=lambda s: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        except (ValueError, TypeError, RecursionError) as exc:
            raise FlowCompilationError('invalid_recipe', message='Malformed, duplicate-key, or nonfinite recipe', cause=exc) from exc
        _exact(raw, ('version', 'sources', 'target', 'functions', 'flow'), (), ('recipe',))
        if type(raw['version']) is not int or raw['version'] != VERSION or type(raw['functions']) is not dict:
            raise FlowCompilationError('invalid_recipe', message='Unsupported recipe version or contracts')
        try: plan = compile_flow(raw['flow'], raw['sources'], raw['target'], vocab)
        except FlowCompilationError: raise
        if json.loads(plan.to_json()) != raw:
            raise FlowCompilationError('invalid_recipe', message='Recipe is noncanonical or recorded contracts do not match supplied vocabulary')
        return plan

def compile_flow(flow, source_types, target_type, vocab):
    """Compile strict JSON flow with explicit typed input sources and return target.

    Signature: compile_flow(flow, source_types, target_type, vocab).
    Pass target_type=None to infer and freeze the exact return schema.
    """
    if type(source_types) is not dict or not all(type(k) is str for k in source_types):
        raise FlowCompilationError('invalid_sources', message='source_types must be a named schema dictionary')
    sources = {}
    for name, raw in source_types.items():
        ident(name, ('sources', name))
        try: sources[name] = normalize(raw)
        except B2BCompilationError as exc:
            raise FlowCompilationError('invalid_sources', ('sources', name), str(exc), cause=exc) from exc
    try: target = normalize(target_type) if target_type is not None else None
    except B2BCompilationError as exc:
        raise FlowCompilationError('invalid_target', message=str(exc), cause=exc) from exc
    _exact(flow, ('steps', 'returns'), (), ('flow',))
    try:
        json.dumps(flow, allow_nan=False)
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise FlowCompilationError('invalid_flow_json', ('flow',),
                                   'Flow must be a finite acyclic JSON-shaped declaration', cause=exc) from exc
    _preflight_count(flow)
    compiler = _Compiler(vocab)
    nodes, serial, scope = compiler.steps(flow['steps'], sources, ('flow', 'steps'))
    returns = compiler.expr(flow['returns'], scope, ('flow', 'returns'), target)
    target = target or returns.schema
    recipe = {'version': VERSION, 'sources': {k: v.to_json() for k, v in sorted(sources.items())},
              'target': target.to_json(),
              'functions': {k: compiler.contracts[k] for k in sorted(compiler.contracts)},
              'flow': {'steps': serial, 'returns': returns.canonical}}
    try: encoded = json.dumps(recipe, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise FlowCompilationError('invalid_recipe', message='Flow cannot be encoded as finite JSON', cause=exc) from exc
    return FlowPlan(encoded, nodes, returns, sources, target, compiler.contracts)
