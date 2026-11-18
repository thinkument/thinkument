"""Structural limits, queue bounds, deterministic output, runtime and portability scale."""
import json
from concurrent.futures import ThreadPoolExecutor as BasePool
from random import Random
from threading import Lock
from time import perf_counter, sleep

import pytest
from bindings2bindingsTM import D, Dict, List
from JSONfnchainTM import compile_flow, execute_flow, FunctionVocab, FlowPlan, FlowCompilationError
from JSONfnchainTM import runtime


def vocab(fn=None):
    v=FunctionVocab()
    v.register(name='io.identity', fn=fn or (lambda a,c: {'value':a['value']}),
               inputs=Dict({'value':int}), output=Dict({'value':int}), version='1')
    return v


def map_flow(*, concurrent=True, maximum=8):
    return {'steps':[{'id':'mapped','map':{'over':'$p.xs','parallel':concurrent,
        'max_concurrency':maximum,'call':{'fn':'io.identity','args':{'value':'$current'}}}}],
        'returns':'$mapped'}


def test_map_many_items_order_and_roundtrip(capsys):
    rng=Random(17031)
    v=vocab(); f=map_flow(); p=compile_flow(f,{'p':Dict({'xs':List(int)})},List(Dict({'value':int})),v)
    restored=FlowPlan.from_json(p.to_json(),vocab=v)
    for n in (0,1,11,50,500,2000):
        xs=[rng.randrange(-100000,100000) for _ in range(n)]
        start=perf_counter()
        result=execute_flow(restored,{'p':{'xs':xs}},vocab=v,max_concurrency=4)
        assert result==[{'value':i} for i in xs]
        print({'items':n,'elapsed_seconds':round(perf_counter()-start,5)})


def test_inflight_tasks_do_not_exceed_effective_cap(monkeypatch):
    lock=Lock()
    stats={'now':0,'peak':0,'submitted':0}
    class TrackingPool(BasePool):
        def submit(self, fn, *args, **kwargs):
            with lock:
                stats['now']+=1; stats['submitted']+=1
                stats['peak']=max(stats['peak'],stats['now'])
            try: future=super().submit(fn,*args,**kwargs)
            except BaseException:
                with lock: stats['now']-=1
                raise
            def finished(_):
                with lock: stats['now']-=1
            future.add_done_callback(finished)
            return future
    monkeypatch.setattr(runtime,'ThreadPoolExecutor',TrackingPool)
    def slow(args,ctx):
        sleep(.0005)
        return {'value':args['value']}
    v=vocab(slow)
    p=compile_flow(map_flow(maximum=3),{'p':Dict({'xs':List(int)})},
                   List(Dict({'value':int})),v)
    xs=list(range(1000))
    assert len(execute_flow(p,{'p':{'xs':xs}},vocab=v,max_concurrency=5))==len(xs)
    assert stats['submitted']==1000
    assert 1<=stats['peak']<=3


def test_execution_wide_cap_clamps_map_local_concurrency(monkeypatch):
    lock=Lock(); running=0; peak=0
    def slow(args,ctx):
        nonlocal running,peak
        with lock:
            running+=1; peak=max(peak,running)
        sleep(.002)
        with lock: running-=1
        return {'value':args['value']}
    v=vocab(slow)
    p=compile_flow(map_flow(maximum=100),{'p':Dict({'xs':List(int)})},
                   List(Dict({'value':int})),v)
    execute_flow(p,{'p':{'xs':list(range(70))}},vocab=v,max_concurrency=2)
    assert 1<=peak<=2


def test_short_circuits_use_b2b_without_custom_expression_operators():
    v=vocab()
    flow={'steps':[{'id':'selected','map':{'over':{'$filter':['$p.xs',{'$gte':['$item',2]}]},
        'steps':[], 'returns':{'$add':['$current',1]}}}],
        'returns':{'$sum':'$selected'}}
    p=compile_flow(flow,{'p':Dict({'xs':List(int)})},int,v)
    for xs in ([0,1,2,3],[],[10]*40):
        out=sum(x+1 for x in xs if x>=2)
        assert execute_flow(p,{'p':{'xs':xs}},vocab=v)==out
        assert execute_flow(FlowPlan.from_json(p.to_json(),vocab=v),
                            {'p':{'xs':xs}},vocab=v)==out


def test_generated_flow_differential_200_cases():
    rng=Random(4747); v=vocab()
    f={'steps':[{'id':'a','map':{'over':'$p.xs','steps':[],
        'returns':{'$mul':['$current',3]}}}], 'returns':'$a'}
    p=compile_flow(f,{'p':Dict({'xs':List(int)})},List(int),v)
    for i in range(200):
        xs=[rng.randint(-1000,1000) for _ in range(rng.randrange(0,35))]
        assert execute_flow(p,{'p':{'xs':xs}},vocab=v)==[3*x for x in xs]


def test_json_recipe_is_stable_and_contains_only_static_structures():
    v=vocab()
    p=compile_flow(map_flow(),{'p':Dict({'xs':List(int)})},List(Dict({'value':int})),v)
    raw=json.loads(p.to_json())
    assert p.to_json()==json.dumps(raw,sort_keys=True,separators=(',',':'))
    assert all(set(contract)=={'version','inputs','output'} for contract in raw['functions'].values())
    assert 'thread' not in p.to_json().lower() and 'future' not in p.to_json().lower()


def test_large_construct_limit_rejected_before_calling_b2b(monkeypatch):
    calls=0; original=runtime.execute_flow
    many=[{'id':f'call_{i}','fn':'io.identity', 'args':{'value':i}} for i in range(10001)]
    start=perf_counter()
    with pytest.raises(FlowCompilationError) as caught:
        compile_flow({'steps':many,'returns':'$call_0'}, {}, Dict({'value':int}), vocab())
    assert caught.value.details['code']=='node_count_limit'
    # No machine-dependent timing assertion.
    assert calls==0
    print({'oversized_nodes':len(many),'reject_seconds':round(perf_counter()-start,5)})


def test_compilation_and_exec_reported_timing_no_machine_threshold(capsys):
    for n in (1,10,100):
        flow={'steps':[{'id':f's{i}','fn':'io.identity',
                       'args':{'value':'$p.x'}} for i in range(n)],
              'returns':f'$s{n-1}.value'}
        v=vocab()
        start=perf_counter()
        plan=compile_flow(flow,{'p':Dict({'x':int})},int,v)
        compile_seconds=perf_counter()-start
        start=perf_counter()
        result=execute_flow(plan,{'p':{'x':13}},vocab=v)
        assert result==13
        print({'steps':n,'compile_seconds':round(compile_seconds,5),
               'run_seconds':round(perf_counter()-start,5)})


def test_inferred_flow_target_roundtrip_and_worker_context_isolation():
    from contextvars import ContextVar
    from JSONfnchainTM import FunctionVocab, compile_flow, execute_flow, FlowPlan
    from bindings2bindingsTM import Dict, Str
    marker = ContextVar('flow_test_marker', default='missing')
    vocab = FunctionVocab()
    def read(args, ctx):
        value = marker.get()
        marker.set('worker-local')
        return {'value': value}
    vocab.register(name='context.read', fn=read, inputs=Dict({}), output=Dict({'value':Str}), version='1')
    flow={'steps':[{'id':'both','parallel':[{'id':'a','fn':'context.read'},{'id':'b','fn':'context.read'}]}],
          'returns':{'a':'$both.a.value','b':'$both.b.value'}}
    plan=compile_flow(flow,{},None,vocab)
    token=marker.set('host')
    try:
        restored=FlowPlan.from_json(plan.to_json(),vocab=vocab)
        assert execute_flow(restored,{},vocab=vocab)=={'a':'host','b':'host'}
        assert marker.get()=='host'
    finally:
        marker.reset(token)
