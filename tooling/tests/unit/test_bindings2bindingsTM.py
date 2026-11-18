"""v1 regression, v2 algebra, failure boundaries, portability, and immutability."""
import json
import math
import pytest
from bindings2bindingsTM import *
from bindings2bindingsTM.compiler import fields, V1_OPS

@pytest.mark.parametrize('schema,good,bad', [
    (str, 'x', 0), (int, 2, True), (float, 2.0, 2), (bool, False, 0),
    (Nullable(str), None, 0), (List(int), [1, 2], [True]),
    (Dict({'x': str}), {'x': 'a'}, {'x': 'a', 'y': 0}),
    (Map(bool), {'x': False}, {'x': 1}),
])
def test_exact_types(schema, good, bad):
    plan = compile_binding({'s': schema}, schema, D.ref('s'))
    assert plan.evaluate({'s': good}) == good
    with pytest.raises(RuntimeValueError): plan.evaluate({'s': bad})

@pytest.mark.parametrize('value', [float('inf'), float('-inf'), float('nan')])
def test_nonfinite(value):
    with pytest.raises(CompilationError): compile_binding({}, float, D.value(value))
    with pytest.raises(RuntimeValueError): compile_binding({'s': float}, float, D.ref('s')).evaluate({'s': value})

def test_nested_composition_and_roundtrip():
    source = Dict({'title': str, 'count': int})
    e = D.dict({'heading': D.text(D.ref('draft', 'title'), ' / $literal ', True, 2, 2.5),
                'items': D.map(D.ref('entries'), D.dict({
                    'label': D.text('Entry: ', D.item('title')), 'count': D.item('count')}))})
    target = Dict({'heading': str, 'items': List(Dict({'label': str, 'count': int}))})
    p = compile_binding({'draft': source, 'entries': List(source)}, target, e)
    values = {'draft': {'title': 'A', 'count': 0}, 'entries': [{'title': 'B', 'count': 3}]}
    result = p.evaluate(values)
    assert result == {'heading': 'A / $literal true22.5', 'items': [{'label': 'Entry: B', 'count': 3}]}
    assert BindingPlan.from_json(p.to_json()).evaluate(values) == result
    result['items'][0]['count'] = 9
    assert values['entries'][0]['count'] == 3
    e['fields'].clear()
    assert p.evaluate(values)['items'][0]['count'] == 3
    assert p.dependencies == (('draft', ('title',)), ('entries', ()))

def test_projection_does_not_scan_unrelated_data():
    p = compile_binding({'s': Dict({'a.b': str, 'huge': List(int)})}, str, D.ref('s', 'a.b'))
    assert p.evaluate({'s': {'a.b': '$x', 'huge': object()}}) == '$x'
    with pytest.raises(RuntimeValueError): p.evaluate({'s': {'a.b': 2}})
    with pytest.raises(RuntimeValueError):
        compile_binding({'s': Dict({'a.b': str, 'huge': List(int)})},
                        Dict({'a.b': str, 'huge': List(int)}), D.ref('s')).evaluate(
                            {'s': {'a.b': 'x', 'huge': object()}})

def test_nullable_and_empty_inference():
    assert compile_binding({}, List(Nullable(str)), D.list(None, 'a')).evaluate({}) == [None, 'a']
    assert compile_binding({}, List(int), D.list()).evaluate({}) == []
    assert compile_binding({}, Nullable(int), D.value(2)).evaluate({}) == 2
    with pytest.raises(CompilationError): compile_binding({'s': Nullable(int)}, int, D.ref('s'))
    with pytest.raises(CompilationError): compile_binding({}, str, D.text(D.list()))
    with pytest.raises(CompilationError): compile_binding({}, int, D.item())
    with pytest.raises(CompilationError): compile_binding({}, List(int), D.list(1, True))

def test_nested_map_scope():
    e = D.map(D.ref('s'), D.map(D.item('rows'), D.text(D.item())))
    assert compile_binding({'s': List(Dict({'rows': List(int)}))}, List(List(str)), e).evaluate(
        {'s': [{'rows': [1, 2]}]}) == [['1', '2']]

@pytest.mark.parametrize('mutation', [
    lambda r: r.update(version=3),
    lambda r: r.update(certified=True),
    lambda r: r['expression'].update(op='execute'),
    lambda r: r['sources'].update(s={'kind': 'union'}),
    lambda r: r['expression'].update(path=['absent']),
])
def test_untrusted_recipe(mutation):
    r = json.loads(compile_binding({'s': Dict({'x': str})}, str, D.ref('s', 'x')).to_json())
    mutation(r)
    with pytest.raises(CompilationError): BindingPlan.from_json(json.dumps(r))

def test_recursive_schema_rejected():
    r = {'kind': 'list'}; r['item'] = r
    with pytest.raises(CompilationError): normalize(r)

def test_generated_supported_expressions():
    for n in range(40):
        e = D.map(D.ref('s'), D.dict({'text': D.text('$', D.item()), 'value': D.item()}))
        p = compile_binding({'s': List(int)}, List(Dict({'text': str, 'value': int})), e)
        assert BindingPlan.from_json(p.to_json()).evaluate({'s': list(range(n))}) == [
            {'text': '$' + str(i), 'value': i} for i in range(n)]

def test_map_literals_closed_to_open_compatibility_and_nullable_construction():
    assert compile_binding({}, Map(int), D.dict({'a': 1, 'b': 2})).evaluate({}) == {'a': 1, 'b': 2}
    assert compile_binding({}, Map(int), D.value({})).evaluate({}) == {}
    assert compile_binding({}, Nullable(List(int)), D.value([])).evaluate({}) == []
    assert compile_binding({}, Nullable(Dict({'items': List(int)})),
                           D.dict({'items': D.list()})).evaluate({}) == {'items': []}
    with pytest.raises(CompilationError):
        compile_binding({'s': Map(str)}, Dict({'a': str}), D.ref('s'))

@pytest.mark.parametrize('expression', [
    {'op': []}, {'op': 'ref', 'source': 's', 'path': [0]}, D.value({1: 'not a string key'}),
])
def test_malformed_expression_has_structured_errors(expression):
    with pytest.raises(CompilationError) as caught: compile_binding({'s': str}, str, expression)
    json.dumps(caught.value.details, allow_nan=False)

def _evaluated(expr, target, sources=None, values=None):
    p = compile_binding(sources or {}, target, expr)
    result = p.evaluate(values or {})
    assert BindingPlan.from_json(p.to_json()).evaluate(values or {}) == result
    return result

def _error(code, fn, error_class=CompilationError):
    with pytest.raises(error_class) as caught: fn()
    assert caught.value.details['code'] == code
    json.dumps(caught.value.details, allow_nan=False)

def test_all_39_operators_have_exact_canonical_grammar():
    assert len(fields) == 39
    assert V1_OPS == {'value', 'ref', 'item', 'text', 'list', 'dict', 'map'}
    assert {k for k in fields} == set('''value ref item outer text list dict map cond default
      eq neq lt lte gt gte and or not in add sub mul div mod neg size index slice filter merge
      to_str to_int to_float sum any all min max'''.split())
    _error('invalid_expression', lambda: compile_binding({}, int, {'op': 'add', 'left': D.value(1),
                                                                   'right': D.value(2), 'extra': 5}))

def test_conditional_short_circuiting():
    danger = D.div(1, 0)
    assert _evaluated(D.cond(True, 7.0, danger), float) == 7.0
    assert _evaluated(D.cond(False, danger, 8.0), float) == 8.0
    assert _evaluated(D.cond(True, 1, 2), int) == 1
    assert _evaluated(D.cond(False, None, 'ready'), Nullable(str)) == 'ready'
    _error('operand_type', lambda: compile_binding({}, int, D.cond(1, 2, 3)))
    _error('incompatible_branches', lambda: compile_binding({}, str, D.cond(True, 2, 'bad')))
    assert infer_expression_type({}, D.cond(True, 2, None), expected_type=Nullable(int)) == Nullable(int)

def test_default_nullable_unwrapping():
    assert _evaluated(D.default(D.index(D.list('a'), 3), 'fallback'), str) == 'fallback'
    assert _evaluated(D.default(D.index(D.list('a'), 0), 'fallback'), str) == 'a'
    assert _evaluated(D.default(D.index(D.list(5), 0), D.mod(1, 0)), int) == 5
    assert _evaluated(D.default(D.value(None), 9), int) == 9
    _error('default_requires_nullable', lambda: compile_binding({}, int, D.default(2, 3)))
    _error('default_requires_nonnull_fallback', lambda: compile_binding(
        {'s': Nullable(int)}, int, D.default(D.ref('s'), D.ref('s'))))

def test_predicate_and_comparison_logic():
    for expr, expected in [
        (D.eq(2, 2), True), (D.neq('a', 'b'), True),
        (D.lt(2, 3), True), (D.lte(2, 2), True), (D.gt('z', 'a'), True),
        (D.gte(3.0, 3.0), True), (D.not_(False), True),
        (D.and_(True, True), True), (D.or_(False, True), True),
        (D.and_(), True), (D.or_(), False),
        (D.in_('a', D.list('a', 'b')), True),
        (D.in_('x', D.dict({'x': 1})), True),
        (D.in_('x', D.ref('record')), True),
        (D.eq(D.dict({'a': D.list(1, 2)}), D.dict({'a': D.list(1, 2)})), True),
    ]:
        sources = {'record': Map(int)} if expr['op'] == 'in' and expr['collection']['op'] == 'ref' else {}
        values = {'record': {'x': 2}} if sources else {}
        assert _evaluated(expr, bool, sources, values) is expected
    assert _evaluated(D.and_(False, D.gt(D.div(1, 0), 0.0)), bool) is False
    assert _evaluated(D.or_(True, D.gt(D.div(1, 0), 0.0)), bool) is True
    _error('comparison_types', lambda: compile_binding({}, bool, D.lt(True, False)))
    _error('membership_types', lambda: compile_binding({}, bool, D.in_(1, D.dict({'x': 2}))))
    _error('incomparable_types', lambda: compile_binding({}, bool, D.eq('1', 1)))

def test_pure_arithmetic_precision_and_zero_division():
    for expr, t, expected in [
        (D.add(2, 3), int, 5), (D.sub(2, 5), int, -3), (D.mul(3, 4), int, 12),
        (D.div(7, 2), float, 3.5), (D.mod(-7, 3), int, 2),
        (D.neg(2), int, -2), (D.neg(2.5), float, -2.5),
        (D.add(2.5, 1.5), float, 4.0),
    ]:
        assert _evaluated(expr, t) == expected
    assert _evaluated(D.add(10**100, 10**100), int) == 2 * 10**100
    _error('division_by_zero', lambda: compile_binding({}, float, D.div(2, 0)).evaluate({}), RuntimeValueError)
    _error('division_by_zero', lambda: compile_binding({}, int, D.mod(2, 0)).evaluate({}), RuntimeValueError)
    _error('nonfinite_float', lambda: compile_binding({}, float, D.mul(1e308, 1e308)).evaluate({}), RuntimeValueError)
    _error('nonfinite_float', lambda: compile_binding({}, float, D.div(10**400, 2)).evaluate({}), RuntimeValueError)
    _error('arithmetic_types', lambda: compile_binding({}, int, D.mod(2.0, 1.0)))

def test_collection_size_index_slice_filter_merge():
    assert _evaluated(D.size('a🐙b'), int) == 3
    assert _evaluated(D.size(D.dict({'a': 1, 'b': 2})), int) == 2
    assert _evaluated(D.size(D.list('x', 'y')), int) == 2
    assert _evaluated(D.size(D.ref('m')), int, {'m': Map(int)}, {'m': {'x': 1}}) == 1
    for idx, expected in [(-3, 'a'), (-1, 'c'), (0, 'a'), (2, 'c'), (-4, None), (3, None)]:
        assert _evaluated(D.index(D.list('a', 'b', 'c'), idx), Nullable(str)) == expected
    assert _evaluated(D.index(D.list(), 0), Nullable(int)) is None
    assert _evaluated(D.slice('abcdef', -4, -1), str) == 'cde'
    assert _evaluated(D.slice(D.list(1, 2, 3, 4), 1, None), List(int)) == [2, 3, 4]
    assert _evaluated(D.slice('abcdef', 99, None), str) == ''
    assert _evaluated(D.filter(D.list(1, 2, 3, 4), D.gt(D.item(), 2)), List(int)) == [3, 4]
    assert _evaluated(D.merge(D.dict({'x': 1}), D.dict({'y': 2})),
                      Dict({'x': int, 'y': int})) == {'x': 1, 'y': 2}
    assert _evaluated(D.merge(), Dict({})) == {}
    _error('filter_requires_list', lambda: compile_binding({}, List(int), D.filter('abc', True)))
    _error('operand_type', lambda: compile_binding({}, List(int), D.filter(D.list(1), 1)))
    _error('index_requires_list', lambda: compile_binding({}, Nullable(str), D.index('abc', 0)))
    _error('slice_end_type', lambda: compile_binding({}, str, D.slice('abc', 0, 1.1)))

def test_scalar_type_casting():
    for expr, t, expected in [
        (D.to_str(2.5), str, '2.5'), (D.to_str(True), str, 'true'),
        (D.to_str('abc'), str, 'abc'), (D.to_str(5), str, '5'),
        (D.to_int('123'), int, 123), (D.to_int('-123'), int, -123),
        (D.to_int(3.0), int, 3), (D.to_int(False), int, 0),
        (D.to_float('2.25e2'), float, 225.0), (D.to_float(42), float, 42.0),
    ]:
        assert _evaluated(expr, t) == expected
    _error('nonintegral_float', lambda: compile_binding({}, int, D.to_int(3.7)).evaluate({}), RuntimeValueError)
    for v in ('nan', 'inf', ' 1', '1 ', '1_2', '0x12', '1e3'):
        _error('invalid_numeric_cast', lambda: compile_binding({}, int, D.to_int(v)).evaluate({}), RuntimeValueError)
    _error('invalid_numeric_cast', lambda: compile_binding({}, float, D.to_float('NaN')).evaluate({}), RuntimeValueError)
    _error('nonfinite_float', lambda: compile_binding({}, float, D.to_float('1e999')).evaluate({}), RuntimeValueError)
    _error('cast_type', lambda: compile_binding({}, int, D.to_int(3)))

def test_version_1_recipe_backward_compatibility():
    p = compile_binding({'s': Dict({'v': str})}, str, D.text('$', D.ref('s', 'v')))
    recipe = json.loads(p.to_json()); recipe['version'] = 1
    restored = BindingPlan.from_json(json.dumps(recipe))
    assert json.loads(restored.to_json())['version'] == 1
    assert restored.evaluate({'s': {'v': 'legacy'}}) == '$legacy'
    bad = json.loads(compile_binding({}, int, D.add(1, 2)).to_json()); bad['version'] = 1
    _error('invalid_expression', lambda: BindingPlan.from_json(json.dumps(bad)))
    assert json.loads(p.to_json())['version'] == 2

def test_sugar_dot_paths_and_boxing():
    expr = D.sugar({'$dict': {'title': '$draft.title', 'inner': '$draft.inner.value',
                              'literal': {'$value': '$draft.title'}}})
    target = Dict({'title': str, 'inner': int, 'literal': str})
    sources = {'draft': Dict({'title': str, 'inner': Dict({'value': int})})}
    assert _evaluated(expr, target, sources, {'draft': {'title': 'T', 'inner': {'value': 3}}}) == {
        'title': 'T', 'inner': 3, 'literal': '$draft.title'}
    assert _evaluated(D.value('$draft.title'), str) == '$draft.title'
    assert _evaluated(D.text('$draft.title'), str) == '$draft.title'
    assert _evaluated(D.value({'$gte': ['$x', '2']}), Dict({'$gte': List(str)})) == {'$gte': ['$x', '2']}

def test_sugar_compact_operators_and_escaping():
    expr = D.sugar({'$dict': {'ready': {'$gte': ['$draft.score', 0.9]},
                              'name': {'$default': ['$draft.title', 'Untitled']},
                              'escaped': {'$value': {'$gt': ['$item.value', '3']}},
                              'numbers': {'$list': [1, 2]},
                              'selected': {'$filter': ['$draft.flags', {'$not': False}]}}})
    target = Dict({'ready': bool, 'name': str, 'escaped': Dict({'$gt': List(str)}),
                   'numbers': List(int), 'selected': List(bool)})
    src = Dict({'score': float, 'title': Nullable(str), 'flags': List(bool)})
    assert _evaluated(expr, target, {'draft': src},
                      {'draft': {'score': 0.95, 'title': None, 'flags': [False, True]}}) == {
        'ready': True, 'name': 'Untitled', 'escaped': {'$gt': ['$item.value', '3']},
        'numbers': [1, 2], 'selected': [False, True]}
    _error('invalid_sugar', lambda: D.sugar({'$nonsense': 2}))
    _error('invalid_sugar', lambda: D.sugar({'$add': [1]}))

def test_filter_with_item_scope():
    src = List(Dict({'score': float, 'label': str}))
    e = D.filter(D.ref('s'), D.gte(D.item('score'), 0.9))
    assert _evaluated(e, src, {'s': src}, {'s': [{'score': 0.7, 'label': 'low'},
                                               {'score': 0.95, 'label': 'high'}]}) == [
        {'score': 0.95, 'label': 'high'}]
    _error('item_outside_map', lambda: compile_binding({}, int, D.item()))

def test_outer_parent_scope_access():
    sources = {'groups': List(Dict({'name': str, 'rows': List(Dict({'v': int, 'cells': List(int)}))}))}
    expr = D.map(D.ref('groups'), D.map(D.item('rows'), D.dict({
        'label': D.text(D.outer('name'), ':', D.item('v')),
        'cells': D.map(D.item('cells'), D.text(D.outer('v'), '/', D.outer('name', levels=2), '/', D.item()))
    })))
    target = List(List(Dict({'label': str, 'cells': List(str)})))
    values = {'groups': [{'name': 'A', 'rows': [{'v': 7, 'cells': [2, 3]}]}]}
    assert _evaluated(expr, target, sources, values) == [[{'label': 'A:7', 'cells': ['7/A/2', '7/A/3']}]]
    _error('outer_outside_map', lambda: compile_binding({}, str, D.outer('x')))
    _error('outer_outside_map', lambda: compile_binding({'s': List(int)}, List(int),
                                                          D.map(D.ref('s'), D.outer())))
    _error('invalid_outer_level', lambda: compile_binding({'s': List(List(int))}, List(List(int)),
        D.map(D.ref('s'), D.map(D.item(), D.outer(levels=2)))))
    _error('invalid_outer_level', lambda: compile_binding({'s': List(List(int))}, List(List(int)),
        D.map(D.ref('s'), D.map(D.item(), D.outer(levels=0)))))

def test_aggregations_sum_any_all_min_max():
    for name, t, filled, empty in [
        ('sum', List(int), 6, 0), ('sum', List(float), 6.0, 0.0),
        ('any', List(bool), True, False), ('all', List(bool), False, True),
        ('min', List(int), 1, None), ('max', List(int), 3, None),
        ('min', List(str), 'a', None), ('max', List(str), 'c', None),
    ]:
        values = ({'xs': [1, 2, 3]} if t == List(int) else
                  {'xs': [1.0, 2.0, 3.0]} if t == List(float) else
                  {'xs': [False, True]} if t == List(bool) else
                  {'xs': ['c', 'a', 'b']})
        expected = bool if name in ('any', 'all') else (Nullable(t.item) if name in ('min', 'max') else t.item)
        p = compile_binding({'xs': t}, expected, getattr(D, name)(D.ref('xs')))
        assert p.evaluate(values) == filled
        out = p.evaluate({'xs': []})
        assert out == empty
        if name == 'sum': assert type(out) is (float if t == List(float) else int)
        assert BindingPlan.from_json(p.to_json()).evaluate({'xs': []}) == empty
    _error('unsupported_aggregation', lambda: compile_binding({}, int, D.sum(D.list('bad'))))
    _error('unsupported_aggregation', lambda: compile_binding({}, Nullable(bool), D.min(D.list(True))))
    _error('nonfinite_float', lambda: compile_binding({}, float, D.sum(D.list(1e308, 1e308))).evaluate({}), RuntimeValueError)

def test_merge_with_compatible_key_collisions():
    expr = D.merge(D.dict({'x': 1, 'a': 'first'}), D.dict({'x': D.ref('maybe'), 'a': 'last'}))
    schema = Dict({'x': Nullable(int), 'a': str})
    assert _evaluated(expr, schema, {'maybe': Nullable(int)}, {'maybe': None}) == {'x': None, 'a': 'last'}
    _error('merge_requires_dict', lambda: compile_binding({'m': Map(int)}, Map(int), D.merge(D.ref('m'))))
    _error('incompatible_merge_key', lambda: compile_binding({}, Dict({'x': int}),
        D.merge(D.dict({'x': 1}), D.dict({'x': 'not compatible'}))))

def test_static_rejection_incompatible_branches():
    _error('incompatible_branches', lambda: compile_binding({}, int, D.cond(True, 2, 'two')))
    assert _evaluated(D.cond(True, D.dict({'x': 1}), D.dict({'x': D.ref('n')})),
                      Dict({'x': Nullable(int)}), {'n': Nullable(int)}, {'n': None}) == {'x': 1}

def test_static_rejection_mixed_numeric_types():
    for builder in (D.add, D.sub, D.mul, D.div, D.eq, D.lt, D.gt):
        _error('mixed_numeric_types', lambda: compile_binding({}, float, builder(1, 2.0)))
    assert _evaluated(D.add(D.to_float(1), 2.0), float) == 3.0

def test_infer_expression_type_public_contract():
    assert infer_expression_type({'items': List(Dict({'n': int}))},
        D.map(D.ref('items'), D.item('n'))) == List(int)
    assert infer_expression_type({}, D.list(), expected_type=List(int)) == List(int)
    _error('target_type', lambda: infer_expression_type({}, D.value(1), expected_type=str))
    _error('ambiguous_empty_list', lambda: infer_expression_type({}, D.list()))

def test_recipe_malformed_json_and_immutable_structures():
    p = compile_binding({}, List(int), D.list(1, 2))
    with pytest.raises(TypeError): p._expression['items'][0]['value'] = '9'
    with pytest.raises(AttributeError): p._map_schemas = {}
    for serialized in ('{"version":2,"version":2}', '{"expression":NaN}', '[]'):
        _error('invalid_recipe', lambda: BindingPlan.from_json(serialized))
    p2 = compile_binding({}, int, D.value(1))
    bad = json.loads(p2.to_json()); bad['expression']['other'] = D.value(3)
    _error('invalid_expression', lambda: BindingPlan.from_json(json.dumps(bad)))

def test_common_schema_and_closed_map_widening():
    assert reconcile_common_schema(int_schema := normalize(int), Nullable(int)) == Nullable(int)
    assert reconcile_common_schema(List(int), List(Nullable(int))) == List(Nullable(int))
    assert reconcile_common_schema(Dict({'a': int}), Dict({'b': int})) == Map(int)
    assert reconcile_common_schema(Dict({'a': int}), Map(int)) == Map(int)
    assert merge_dict_schemas(Dict({'x': int}), Dict({'x': Nullable(int)})) == Dict({'x': Nullable(int)})
    _error('incompatible_branches', lambda: reconcile_common_schema(int_schema, normalize(float)))
    _error('merge_requires_dict', lambda: merge_dict_schemas(Dict({}), Map(str)))
    _error('incompatible_merge_key', lambda: merge_dict_schemas(Dict({'x': int}), Dict({'x': str})))

def test_all_empty_aggregations_with_destination_type_hints():
    assert _evaluated(D.sum(D.list()), int) == 0
    assert type(_evaluated(D.sum(D.list()), float)) is float
    assert _evaluated(D.any(D.list()), bool) is False
    assert _evaluated(D.all(D.list()), bool) is True
    assert _evaluated(D.min(D.list()), Nullable(int)) is None
    assert _evaluated(D.max(D.list()), Nullable(str)) is None
    assert _evaluated(D.filter(D.list(), False), List(str)) == []
    assert _evaluated(D.slice(D.list(), 0), List(int)) == []
    assert _evaluated(D.default(D.index(D.list(), 0), 123), int) == 123

def test_sugar_nested_map_filter_and_outer2():
    src = List(Dict({'name': str, 'rows': List(Dict({'xs': List(int)}))}))
    expr = D.sugar({'$map': ['$groups', {'$map': ['$item.rows', {
        '$map': [{'$filter': ['$item.xs', {'$gte': ['$item', 2]}]},
                 {'$text': ['$outer2.name', ':', '$item']}]
    }]}]})
    assert _evaluated(expr, List(List(List(str))), {'groups': src}, {
        'groups': [{'name': 'G', 'rows': [{'xs': [0, 2, 4]}]}]
    }) == [[['G:2', 'G:4']]]

def test_deterministic_generated_arithmetic_differential():
    from random import Random
    rng = Random(1729)
    for i in range(250):
        a, b = rng.randrange(-10000, 10000), rng.randrange(-10000, 10000)
        builder, expected = [(D.add, a + b), (D.sub, a - b),
                             (D.mul, a * b), (D.mod, a % (b or 1))][i % 4]
        expr = builder(a, b if builder is not D.mod else b or 1)
        p = compile_binding({}, int, expr)
        assert p.evaluate({}) == expected
        assert BindingPlan.from_json(p.to_json()).evaluate({}) == expected

def test_detachment_of_filtered_and_merged_outputs():
    schema = List(Dict({'xs': List(int)}))
    source = [{'xs': [1, 2]}, {'xs': [3]}]
    p = compile_binding({'s': schema}, schema, D.filter(D.ref('s'), True))
    detached = p.evaluate({'s': source}); detached[0]['xs'][0] = 999
    assert source[0]['xs'][0] == 1
    m = compile_binding({'s': Dict({'xs': List(int)})}, Dict({'xs': List(int)}),
                        D.merge(D.ref('s'), D.dict({})))
    result = m.evaluate({'s': {'xs': [1, 2]}}); result['xs'].append(3)
    assert m.evaluate({'s': {'xs': [1, 2]}}) == {'xs': [1, 2]}

def test_reject_cyclic_json_and_float_int_precision_overflow():
    data = []; data.append(data)
    _error('nonportable_expression', lambda: compile_binding({}, List(int), D.value(data)))
    _error('nonfinite_float', lambda: compile_binding({}, float, D.to_float(10**400)).evaluate({}), RuntimeValueError)
    assert _evaluated(D.to_int(2.0**53), int) == 2**53
