"""Deterministic work counts, plus reported timings without machine thresholds."""
from time import perf_counter
import pytest
from bindings2bindingsTM import *
from bindings2bindingsTM import runtime
from bindings2bindingsTM.compiler import _restore


def test_unrelated_input_size_and_repeated_reads(monkeypatch):
    original = runtime.validate
    calls = []
    def counted(value, schema, path=()):
        calls.append((schema.kind, path))
        return original(value, schema, path)
    monkeypatch.setattr(runtime, 'validate', counted)
    for n in (0, 100, 100000):
        sources = {'s': Dict({'title': str, 'unrelated': List(int)})}
        p = compile_binding(sources, str, D.text(*[D.ref('s', 'title') for i in range(100)]))
        calls.clear()
        values = {'s': {'title': 'a', 'unrelated': list(range(n))}}
        assert p.evaluate(values) == 'a'*100
        assert len(calls) == 1


def test_map_local_repeated_reads_are_reused(monkeypatch):
    original = runtime.validate
    calls = []
    def counted(value, schema, path=()):
        calls.append((schema.kind, path))
        return original(value, schema, path)
    monkeypatch.setattr(runtime, 'validate', counted)
    p = compile_binding({'s': List(Dict({'title': str}))}, List(str),
                        D.map(D.ref('s'), D.text(*[D.item('title') for i in range(10)])))
    for n in (0, 10, 100):
        calls.clear()
        assert p.evaluate({'s': [{'title': 'a'} for i in range(n)]}) == ['a'*10]*n
        assert len(calls) == n+1


def test_bounded_recipe_cache_and_immutable_instructions():
    _restore.cache_clear()
    for n in range(300):
        BindingPlan.from_json(compile_binding({}, str, D.value(str(n))).to_json())
    assert _restore.cache_info().currsize == 128
    plan = compile_binding({}, str, D.value('safe'))
    with pytest.raises(AttributeError): plan._json = 'tampered'
    with pytest.raises(TypeError): plan._expression['op'] = 'ref'


def test_reported_construction_timings(capsys):
    for n in (10, 100, 1000):
        p = compile_binding({'s': List(int)}, List(Dict({'label': str, 'value': int})),
                            D.map(D.ref('s'), D.dict({'label': D.text('value ', D.item()), 'value': D.item()})))
        values = {'s': list(range(n))}
        start = perf_counter()
        for i in range(10): result = p.evaluate(values)
        assert len(result) == n
        print({'items': n, 'evaluations': 10, 'seconds': perf_counter()-start})


def test_projection_uses_preindexed_schema_at_all_widths(monkeypatch):
    for width in (1, 100, 10000):
        fields = {f'field{i}': int for i in range(width)}
        fields['selected'] = str
        p = compile_binding({'s': Dict(fields)}, str, D.ref('s', 'selected'))
        index = p._sources['s']._field_map
        assert index['selected'].kind == 'str'
        for i in range(10):
            assert p.evaluate({'s': {'selected': 'value'}}) == 'value'
        assert p._sources['s']._field_map is index


def test_v2_conditional_does_not_read_unused_huge_source(monkeypatch):
    original = runtime.validate
    calls = []
    def counted(value, schema, path=()):
        calls.append(path)
        return original(value, schema, path)
    monkeypatch.setattr(runtime, 'validate', counted)
    src = {'s': Dict({'chosen': str, 'unused': List(int)})}
    e = D.cond(True, D.ref('s', 'chosen'), D.to_str(D.size(D.ref('s', 'unused'))))
    plan = compile_binding(src, str, e)
    assert plan.evaluate({'s': {'chosen': 'ok', 'unused': object()}}) == 'ok'
    assert calls == [('s', 'chosen')]


def test_v2_outer_scope_reads_once_per_parent_item(monkeypatch):
    original = runtime.validate
    calls = []
    def counted(value, schema, path=()):
        calls.append(path)
        return original(value, schema, path)
    monkeypatch.setattr(runtime, 'validate', counted)
    schema = List(Dict({'prefix': str, 'children': List(int)}))
    expr = D.map(D.ref('s'), D.map(D.item('children'), D.text(
        D.outer('prefix'), D.outer('prefix'), D.item())))
    plan = compile_binding({'s': schema}, List(List(str)), expr)
    assert plan.evaluate({'s': [{'prefix': 'p', 'children': [1, 2, 3]}]}) == [['pp1', 'pp2', 'pp3']]
    assert calls.count(('outer1', 'prefix')) == 1


def test_v2_filter_index_and_aggregation_do_not_scan_unreferenced_sources(monkeypatch):
    original = runtime.validate
    calls = []
    def counted(value, schema, path=()):
        calls.append(path)
        return original(value, schema, path)
    monkeypatch.setattr(runtime, 'validate', counted)
    p = compile_binding({'s': Dict({'relevant': List(int), 'unrelated': List(int)})},
                        Nullable(int), D.max(D.filter(D.ref('s', 'relevant'), D.gt(D.item(), 4))))
    assert p.evaluate({'s': {'relevant': [1, 5, 3], 'unrelated': object()}}) == 5
    assert calls.count(('s', 'relevant')) == 1
    assert not any('unrelated' in x for x in calls)


def test_versioned_restore_cache_keeps_distinct_versions():
    import json
    _restore.cache_clear()
    p = compile_binding({}, int, D.value(2))
    raw = json.loads(p.to_json())
    raw['version'] = 1
    old = BindingPlan.from_json(json.dumps(raw))
    new = BindingPlan.from_json(p.to_json())
    assert old is not new
    assert old.evaluate({}) == new.evaluate({}) == 2
    assert json.loads(old.to_json())['version'] == 1
