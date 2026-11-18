"""Contract, grammar, five constructs, isolation, portability, and fault tests."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Barrier, Event, Lock
from time import sleep
import pytest
from bindings2bindingsTM import D, Dict, List, Map, Nullable
from JSONfnchainTM import (compile_flow, execute_flow, FunctionVocab, FlowPlan,
    FlowInterceptor, FlowCompilationError, FlowRuntimeError,
    MaxIterationsExceededError)


def vocabulary():
    vocab = FunctionVocab()
    vocab.register(name='text.upper', fn=lambda args, ctx: {'text': args['text'].upper()},
                   inputs=Dict({'text': str}), output=Dict({'text': str}), version='1.0')
    vocab.register(name='math.inc', fn=lambda args, ctx: {'value': args['n'] + 1},
                   inputs=Dict({'n': int}), output=Dict({'value': int}), version='1.0')
    vocab.register(name='list.words', fn=lambda args, ctx: {'words': args['words']},
                   inputs=Dict({'words': List(str)}), output=Dict({'words': List(str)}), version='1.0')
    vocab.register(name='io.echo', fn=lambda args, ctx: {'text': args['text']},
                   inputs=Dict({'text': str}), output=Dict({'text': str}), version='1.0')
    return vocab


def compile_run(flow, sources=None, target=None, values=None, vocab=None, **kw):
    vocab = vocab or vocabulary()
    p = compile_flow(flow, sources or {}, target or Dict({'result': str}), vocab)
    return execute_flow(p, values or {}, vocab=vocab, **kw)


def reject(code, callable_):
    with pytest.raises(FlowCompilationError) as info: callable_()
    assert info.value.details['code'] == code
    json.dumps(info.value.details, allow_nan=False)


def test_vocab_registration_and_schema_validation():
    v = vocabulary()
    reject('duplicate_function', lambda: v.register(name='text.upper', fn=lambda a, c: a,
        inputs=Dict({}), output=Dict({}), version='2'))
    reject('invalid_function_contract', lambda: v.register(name='invalid', fn=lambda a, c: a,
        inputs=List(str), output=Dict({}), version='1'))
    reject('invalid_function_name', lambda: v.register(name='bad-name', fn=lambda a, c: a,
        inputs=Dict({}), output=Dict({}), version='1'))
    reject('invalid_function', lambda: v.register(name='nothing', fn=4,
        inputs=Dict({}), output=Dict({}), version='1'))


def test_linear_call_chain_with_canonical_args():
    v = vocabulary()
    flow = {'steps': [
        {'id':'a', 'fn':'text.upper', 'args':{'text':'$mouth.brief'}},
        {'id':'b', 'fn':'text.upper', 'args':{'text':'$a.text'}},
    ], 'returns': {'result':'$b.text'}}
    p = compile_flow(flow, {'mouth':Dict({'brief':str})}, Dict({'result':str}), v)
    assert execute_flow(p, {'mouth':{'brief':'hello'}}, vocab=v) == {'result':'HELLO'}
    assert execute_flow(FlowPlan.from_json(p.to_json(), vocab=v),
                        {'mouth':{'brief':'world'}}, vocab=v) == {'result':'WORLD'}


def test_branching_conditional_flat_if_then_else():
    v = vocabulary()
    f = {'steps':[{'id':'route', 'if':{'$gt':['$parameters.score', 3]},
        'then':{'steps':[{'id':'select','fn':'text.upper','args':{'text':'yes'}}],
                'returns':'$select.text'},
        'else':{'steps':[{'id':'select','fn':'text.upper','args':{'text':'no'}}],
                'returns':'$select.text'}}],
        'returns':{'result':'$route'}}
    p = compile_flow(f, {'parameters':Dict({'score':int})}, Dict({'result':str}), v)
    for score, expected in [(4,'YES'), (3,'NO')]:
        assert execute_flow(p, {'parameters':{'score':score}}, vocab=v) == {'result':expected}
    assert FlowPlan.from_json(p.to_json(), vocab=v).to_json() == p.to_json()


def test_branch_block_and_unvalued_branch():
    v = vocabulary()
    f = {'steps':[{'id':'side', 'branch':{'if':False, 'then':[
        {'id':'do_it', 'fn':'io.echo','args':{'text':'x'}}]}}], 'returns':'$side'}
    p = compile_flow(f, {}, Dict({}), v)
    assert execute_flow(p, {}, vocab=v) == {}
    reject('branch_returns', lambda: compile_flow({'steps':[{'id':'x','if':True,
        'then':{'steps':[], 'returns':'yes'}}], 'returns':'$x'}, {}, str, v))


def test_map_iteration_with_default_current():
    f = {'steps':[{'id':'mapped','map':{'over':'$parameters.words',
        'steps':[{'id':'upper','fn':'text.upper','args':{'text':'$current'}}],
        'returns':'$upper.text'}}], 'returns':{'result':{'$text':[{'$size':'$mapped'},' items']}}}
    assert compile_run(f, {'parameters':Dict({'words':List(str)})},
                       values={'parameters':{'words':['a','b','c']}}) == {'result':'3 items'}


def test_map_iteration_single_call_sugar():
    f = {'steps':[{'id':'mapped','map':{'over':'$parameters.words', 'item_as':'word',
        'call':{'fn':'text.upper','args':{'text':'$word'}}}}], 'returns':'$mapped'}
    assert compile_run(f, {'parameters':Dict({'words':List(str)})},
        List(Dict({'text':str})), {'parameters':{'words':['ab','cd']}}) == [
            {'text':'AB'},{'text':'CD'}]


def test_map_index_and_order():
    f = {'steps':[{'id':'mapped','map':{'over':'$p.words', 'steps':[],
        'returns':{'$text':['$current', ':', '$index']}}}], 'returns':'$mapped'}
    assert compile_run(f, {'p':Dict({'words':List(str)})}, List(str),
                       {'p':{'words':['a','b']}}) == ['a:0','b:1']


def test_stateful_loop_init_update_and_default_return():
    f = {'steps':[{'id':'count','loop':{'init':{'n':0},'max':6,
        'while':{'$lt':['$state.n',3]},'steps':[
            {'id':'next','fn':'math.inc','args':{'n':'$state.n'}}],
        'update':{'n':'$next.value'}}}], 'returns':'$count'}
    assert compile_run(f, {}, Dict({'n':int})) == {'n':3}


def test_stateful_loop_max_iterations_return_current():
    f = {'steps':[{'id':'count','loop':{'init':0,'max':2,'on_max':'return_current',
        'while':True,'steps':[], 'update':{'$add':['$state',1]}}}], 'returns':'$count'}
    assert compile_run(f, {}, int) == 2
    f['steps'][0]['loop']['on_max'] = 'raise'
    with pytest.raises(MaxIterationsExceededError) as caught:
        compile_run(f, {}, int)
    assert caught.value.details['code'] == 'max_iterations'
    f['steps'][0]['loop']['max'] = 0
    with pytest.raises(MaxIterationsExceededError): compile_run(f, {}, int)


def test_loop_exactly_at_max_is_not_failure_if_guard_turns_false():
    f = {'steps':[{'id':'loop0','loop':{'init':0,'max':2,'while':{'$lt':['$state',2]},
        'steps':[], 'update':{'$add':['$state',1]}}}], 'returns':'$loop0'}
    assert compile_run(f, {}, int) == 2


def test_loop_init_ambiguous_list_state_type_and_final_returns():
    f = {'steps':[{'id':'loop0','loop':{'init':[], 'state_type':List(int).to_json(),
        'max':0,'while':False,'steps':[], 'update':'$state',
        'returns':{'$size':'$state'}}}], 'returns':'$loop0'}
    assert compile_run(f, {}, int) == 0


def test_parallel_fork_join_concurrency_and_namespacing():
    barrier = Barrier(2, timeout=3)
    v = FunctionVocab()
    v.register(name='io.sync',fn=lambda a,c: (barrier.wait(), {'text':a['text']})[1],
               inputs=Dict({'text':str}),output=Dict({'text':str}),version='1')
    f = {'steps':[{'id':'fan','parallel':[
        {'id':'a','fn':'io.sync','args':{'text':'A'}},
        {'id':'b','fn':'io.sync','args':{'text':'B'}}]}],
        'returns':{'$text':['$fan.a.text','$fan.b.text']}}
    assert compile_run(f, {}, str, vocab=v, max_concurrency=2) == 'AB'
    reject('unknown_source', lambda: compile_flow({**f, 'returns':'$a.text'}, {}, str, v))


class Audit(FlowInterceptor):
    def __init__(self): self.lock = Lock(); self.events=[]
    def _add(self, kind, ctx):
        with self.lock: self.events.append((kind, ctx))
    def before_step(self, ctx, args): self._add('before',ctx)
    def after_step(self, ctx, args, result): self._add('after',ctx)
    def on_step_error(self, ctx, args, error): self._add('error',ctx)


def test_flow_interceptor_lifecycle_and_attempt_identity():
    audit = Audit()
    f = {'steps':[{'id':'letters','map':{'over':'$p.words','parallel':True,
        'max_concurrency':3,'call':{'fn':'text.upper','args':{'text':'$current'}}}}],
        'returns':'$letters'}
    v=vocabulary(); p=compile_flow(f, {'p':Dict({'words':List(str)})}, List(Dict({'text':str})),v)
    result=execute_flow(p,{'p':{'words':['a','b','c']}},vocab=v,interceptor=audit,max_concurrency=3)
    assert [x['text'] for x in result]==['A','B','C']
    assert Counter(k for k,ctx in audit.events)=={'before':3,'after':3}
    begins=[c for k,c in audit.events if k=='before']
    ends=[c for k,c in audit.events if k=='after']
    assert {c.attempt_id for c in begins}=={c.attempt_id for c in ends}
    assert len({c.attempt_id for c in begins})==3
    assert len({c.execution_id for c in begins})==1
    assert {c.map_indices for c in begins}=={(0,),(1,),(2,)}
    assert all(c.node_path[0]=='letters' for c in begins)
    assert all(c.host_context=={'request':'R'} for c in begins) is False
    audit2=Audit()
    execute_flow(p,{'p':{'words':['a']}},vocab=v,interceptor=audit2,host_context={'request':'R'})
    assert audit2.events[0][1].host_context=={'request':'R'}
    assert audit2.events[0][1].execution_id!=begins[0].execution_id


def test_static_rejection_with_did_you_mean_suggestion():
    v=vocabulary()
    with pytest.raises(FlowCompilationError,match="Did you mean 'text.upper'"):
        compile_flow({'steps':[{'id':'bad','fn':'text.uppper','args':{}}], 'returns':'$bad'}, {}, Dict({}),v)
    with pytest.raises(FlowCompilationError,match="Did you mean 'context'"):
        compile_flow({'steps':[{'id':'bad','fn':'io.echo','args':{'text':'$mouth.contex'}}],
            'returns':'$bad'}, {'mouth':Dict({'context':str})}, Dict({'text':str}),v)
    with pytest.raises(FlowCompilationError,match="Did you mean 'mouth'"):
        compile_flow({'steps':[{'id':'bad','fn':'io.echo','args':{'text':'$mout'}}],
            'returns':'$bad'}, {'mouth':str}, Dict({'text':str}),v)


def test_runtime_error_fail_closed_and_settlement():
    sync=Barrier(2,timeout=3); done=[]; lock=Lock()
    def work(args, ctx):
        sync.wait()
        if args['text']=='bad': raise ValueError('vendor failed')
        sleep(.015)
        with lock: done.append(ctx.attempt_id)
        return {'text':'ok'}
    v=FunctionVocab(); v.register(name='io.fails', fn=work, inputs=Dict({'text':str}),
                                  output=Dict({'text':str}),version='1')
    audit=Audit()
    f={'steps':[{'id':'fan','parallel':[
        {'id':'bad','fn':'io.fails','args':{'text':'bad'}},
        {'id':'good','fn':'io.fails','args':{'text':'good'}}]}], 'returns':'$fan.good.text'}
    p=compile_flow(f,{},str,v)
    with pytest.raises(FlowRuntimeError) as caught:
        execute_flow(p,{},vocab=v,interceptor=audit,max_concurrency=2)
    assert caught.value.details['code']=='call_failed'
    assert len(done)==1
    assert Counter(x for x,_ in audit.events)=={'before':2,'error':1,'after':1}


def test_plan_serialization_roundtrip_v1():
    v=vocabulary()
    f={'steps':[{'id':'a','fn':'text.upper','args':{'text':'$p.text'}}],
       'returns':{'result':'$a.text'}}
    p=compile_flow(f,{'p':Dict({'text':str})},Dict({'result':str}),v)
    wire=p.to_json()
    assert json.loads(wire)['version']==1
    assert 'callable' not in wire
    assert wire==FlowPlan.from_json(wire,vocab=v).to_json()
    assert execute_flow(FlowPlan.from_json(wire,vocab=v),{'p':{'text':'hi'}},vocab=v)=={'result':'HI'}
    with pytest.raises(AttributeError): p._json='bad'


@pytest.mark.parametrize('change', [
    lambda r:r.update(version=2),
    lambda r:r.update(extra='bad'),
    lambda r:r['functions']['text.upper'].update(version='bad'),
    lambda r:r['flow']['steps'][0].update(bad='injection'),
    lambda r:r['flow']['steps'][0]['args'].update(op='execute'),
    lambda r:r['flow'].update(returns={'op':'ref','source':'unknown','path':[]}),
])
def test_restore_rejects_tamper(change):
    v=vocabulary(); p=compile_flow({'steps':[{'id':'s','fn':'text.upper',
        'args':{'text':'hi'}}], 'returns':'$s.text'}, {}, str,v)
    raw=json.loads(p.to_json()); change(raw)
    with pytest.raises(FlowCompilationError): FlowPlan.from_json(json.dumps(raw),vocab=v)


@pytest.mark.parametrize('raw', ['[]','{}','{"version":1,"version":1}', '{"version":NaN}', 'not JSON'])
def test_reject_untrusted_wire(raw):
    with pytest.raises(FlowCompilationError): FlowPlan.from_json(raw,vocab=vocabulary())


def test_contract_drift_is_checked_pre_dispatch():
    v=vocabulary(); count=[]
    f={'steps':[{'id':'s','fn':'text.upper','args':{'text':'abc'}}], 'returns':'$s.text'}
    p=compile_flow(f,{},str,v)
    v.register(name='text.upper',fn=lambda a,c:(count.append(1), {'text':'X'})[1],
               inputs=Dict({'text':str}),output=Dict({'text':str}),version='2',replace=True)
    with pytest.raises(FlowRuntimeError) as caught: execute_flow(p,{},vocab=v)
    assert caught.value.details['code']=='contract_drift'
    assert not count


def test_callback_errors_and_invalid_outputs_signal_error_hook():
    audit=Audit(); v=FunctionVocab()
    v.register(name='io.invalid',fn=lambda a,c:{'text':3},
               inputs=Dict({}), output=Dict({'text':str}),version='1')
    p=compile_flow({'steps':[{'id':'x','fn':'io.invalid'}], 'returns':'$x.text'}, {}, str,v)
    with pytest.raises(FlowRuntimeError) as e: execute_flow(p,{},vocab=v,interceptor=audit)
    assert e.value.details['code']=='value_type'
    assert [k for k,_ in audit.events]==['before','error']
    class BeforeFails(Audit):
        def before_step(self,ctx,args): super().before_step(ctx,args); raise ValueError('hook')
    audit2=BeforeFails()
    with pytest.raises(FlowRuntimeError): execute_flow(p,{},vocab=v,interceptor=audit2)
    assert [k for k,_ in audit2.events]==['before','error']


def test_no_dispatch_when_parallel_arg_binding_fails():
    v=vocabulary(); called=[]
    v.register(name='io.track',fn=lambda a,c:(called.append(1),{'text':a['text']})[1],
               inputs=Dict({'text':str}),output=Dict({'text':str}),version='1')
    f={'steps':[{'id':'p','parallel':[
        {'id':'ok','fn':'io.track','args':{'text':'hello'}},
        {'id':'bad','fn':'io.track','args':{'text':'$args.s'}}]}], 'returns':'$p.ok.text'}
    p=compile_flow(f,{'args':Dict({'s':str})},str,v)
    with pytest.raises(FlowRuntimeError): execute_flow(p,{'args':{'s':3}},vocab=v)
    assert not called


def test_rejection_of_forward_ref_alias_collisions_and_unknown_construct():
    v=vocabulary()
    reject('unknown_source',lambda:compile_flow({'steps':[{'id':'a','fn':'io.echo',
        'args':{'text':'$future.text'}},{'id':'future','fn':'io.echo',
        'args':{'text':'foo'}}], 'returns':'$a.text'}, {},str,v))
    reject('duplicate_identifier',lambda:compile_flow({'steps':[{'id':'a','fn':'io.echo',
        'args':{'text':'hi'}},{'id':'a','fn':'io.echo','args':{'text':'hi'}}],
        'returns':'$a.text'}, {},str,v))
    reject('invalid_identifier',lambda:compile_flow({'steps':[{'id':'state','fn':'io.echo'}],
        'returns':'$state'}, {},str,v))
    reject('unknown_construct',lambda:compile_flow({'steps':[{'id':'x','noop':True}],
        'returns':'$x'}, {},str,v))
    reject('invalid_grammar',lambda:compile_flow({'steps':[{'id':'x','fn':'io.echo','inputs':{}}],
        'returns':'$x'}, {},str,v))


def test_branch_private_names_are_unavailable_after_join():
    v=vocabulary()
    f={'steps':[{'id':'b','if':True,'then':[{'id':'private','fn':'io.echo',
        'args':{'text':'hi'}}]}], 'returns':'$private.text'}
    reject('unknown_source',lambda:compile_flow(f,{},str,v))


def test_concurrent_map_blocks_nested_parallel_or_map():
    v=vocabulary()
    nested={'steps':[{'id':'mapped_parent','map':{'over':'$p.items','parallel':True,
        'steps':[{'id':'inner','map':{'over':'$p.items','parallel':True,
            'steps':[], 'returns':'$current'}}], 'returns':'$inner'}}], 'returns':'$outer'}
    reject('nested_concurrency',lambda:compile_flow(nested,{'p':Dict({'items':List(int)})},List(List(int)),v))
    nested['steps'][0]['map']['steps']=[{'id':'fan','parallel':[]}]
    reject('nested_concurrency',lambda:compile_flow(nested,{'p':Dict({'items':List(int)})},List(Dict({})),v))


def test_static_type_errors_use_b2b_not_custom_inference():
    v=vocabulary()
    reject('mixed_numeric_types',lambda:compile_flow({'steps':[],
        'returns':{'$add':[1,2.0]}},{},float,v))
    reject('map_requires_list',lambda:compile_flow({'steps':[{'id':'m','map':{
        'over':42,'call':{'fn':'io.echo','args':{'text':'hi'}}}}],
        'returns':'$m'}, {},List(Dict({'text':str})),v))
    reject('target_type',lambda:compile_flow({'steps':[], 'returns':42},{},str,v))
    reject('loop_state_type',lambda:compile_flow({'steps':[{'id':'s','loop':{
        'init':{'a':1},'while':False,'max':0,'steps':[],
        'update':{'a':1,'b':2}}}], 'returns':'$s'},{},Dict({'a':int}),v))


def test_nested_json_object_sugar_and_escaped_literal():
    v=FunctionVocab()
    v.register(name='obj.render',fn=lambda a,c:{'text':a['x']['name']+' / '+a['y']},
        inputs=Dict({'x':Dict({'name':str}), 'y':str}),output=Dict({'text':str}),version='1')
    f={'steps':[{'id':'a','fn':'obj.render','args':{'x':{'name':'$p.name'},
        'y':{'$value':'$p.name'}}}], 'returns':'$a.text'}
    assert compile_run(f,{'p':Dict({'name':str})},str,{'p':{'name':'Alice'}},v)=='Alice / $p.name'


def test_no_input_mutation_across_calls():
    v=FunctionVocab()
    def mutation(a,c): a['value'].append(999); return {'length':len(a['value'])}
    v.register(name='mutate',fn=mutation,inputs=Dict({'value':List(int)}),
               output=Dict({'length':int}),version='1')
    f={'steps':[{'id':'a','fn':'mutate','args':{'value':'$p.value'}},
        {'id':'b','fn':'mutate','args':{'value':'$p.value'}}],
        'returns':{'$list':['$a.length','$b.length']}}
    values={'p':{'value':[1,2]}}
    assert compile_run(f,{'p':Dict({'value':List(int)})},List(int),values,v)==[3,3]
    assert values=={'p':{'value':[1,2]}}


def test_empty_parallel_and_empty_map():
    v=vocabulary()
    f={'steps':[{'id':'p','parallel':[]},{'id':'m','map':{
        'over':'$args.words','steps':[], 'returns':'$current'}}],
        'returns':{'p':'$p','m':'$m'}}
    assert compile_run(f,{'args':Dict({'words':List(str)})},
        Dict({'p':Dict({}), 'm':List(str)}),{'args':{'words':[]}},v)=={'p':{},'m':[]}


def test_invalid_nesting_max_depth_and_node_count():
    v=vocabulary()
    child={'id':'node','fn':'io.echo','args':{'text':'hi'}}
    for i in range(65): child={'id':f'branch{i}','if':True,'then':[child]}
    reject('construct_nesting_limit',lambda:compile_flow({'steps':[child], 'returns':{}},
                                                         {},Dict({}),v))
    steps=[{'id':f'x{i}','fn':'io.echo','args':{'text':'x'}} for i in range(10001)]
    reject('node_count_limit',lambda:compile_flow({'steps':steps,'returns':{}}, {},Dict({}),v))


def test_exact_output_contract_and_unexpected_result_field():
    v=FunctionVocab()
    v.register(name='bad',fn=lambda a,c:{'value':1,'extra':1},
               inputs=Dict({}),output=Dict({'value':int}),version='1')
    p=compile_flow({'steps':[{'id':'x','fn':'bad'}],'returns':'$x.value'}, {},int,v)
    with pytest.raises(FlowRuntimeError) as c: execute_flow(p,{},vocab=v)
    assert c.value.details['code']=='closed_fields'


def test_failed_map_no_partial_results():
    events=[]
    v=FunctionVocab()
    def worker(a,c):
        events.append(a['value'])
        if a['value']==2: raise ValueError('boom')
        return {'value':a['value']}
    v.register(name='work',fn=worker,inputs=Dict({'value':int}),
               output=Dict({'value':int}),version='1')
    f={'steps':[{'id':'mapped','map':{'over':'$p.values','parallel':True,'max_concurrency':2,
        'call':{'fn':'work','args':{'value':'$current'}}}}], 'returns':'$mapped'}
    p=compile_flow(f,{'p':Dict({'values':List(int)})},List(Dict({'value':int})),v)
    with pytest.raises(FlowRuntimeError):
        execute_flow(p,{'p':{'values':[1,2,3,4,5]}},vocab=v,max_concurrency=2)
    assert 2 in events


def test_nonportable_and_cyclic_flow_rejected_before_grammar_walk():
    v=vocabulary()
    f={'steps':[], 'returns':{}}
    f['steps'].append(f)
    reject('invalid_flow_json',lambda:compile_flow(f,{},Dict({}),v))
    reject('invalid_flow_json',lambda:compile_flow({'steps':[], 'returns':float('nan')}, {},float,v))
    reject('invalid_flow_json',lambda:compile_flow({'steps':[], 'returns':object()}, {},str,v))

def test_immutable_compiled_expression_and_contract_snapshot():
    v=vocabulary()
    p=compile_flow({'steps':[{'id':'x','fn':'text.upper','args':{'text':'abc'}}],
                    'returns':'$x.text'}, {},str,v)
    canonical=p._nodes[0].args.canonical
    canonical['op']='forged'
    assert p._nodes[0].args.canonical['op']=='dict'
    with pytest.raises(TypeError): p._contracts['text.upper']='forged'
    with pytest.raises(AttributeError): p._nodes[0].args.canonical_json='forged'
    assert execute_flow(p,{},vocab=v)=='ABC'

def test_error_after_hook_invokes_on_step_error_once():
    class AfterFails(Audit):
        def after_step(self,ctx,args,result):
            super().after_step(ctx,args,result)
            raise ValueError('audit write failed')
    audit=AfterFails(); v=vocabulary()
    p=compile_flow({'steps':[{'id':'x','fn':'text.upper','args':{'text':'abc'}}],
                    'returns':'$x.text'}, {},str,v)
    with pytest.raises(FlowRuntimeError) as caught:
        execute_flow(p,{},vocab=v,interceptor=audit)
    assert caught.value.details['code']=='call_failed'
    assert [k for k,_ in audit.events]==['before','after','error']
    assert len({ctx.attempt_id for _,ctx in audit.events})==1


def test_canonical_compile_flow_signature():
    v = vocabulary()
    flow = {'steps': [{'id': 'up', 'fn': 'text.upper', 'args': {'text': '$p.msg'}}],
            'returns': '$up.text'}
    sources = {'p': Dict({'msg': str})}
    target = str

    # Canonical positional order: compile_flow(flow, source_types, target_type, vocab)
    plan = compile_flow(flow, sources, target, v)
    assert execute_flow(plan, {'p': {'msg': 'hello'}}, vocab=v) == 'HELLO'

    # Keyword argument order
    plan_kw = compile_flow(flow=flow, source_types=sources, target_type=target, vocab=v)
    assert plan_kw.to_json() == plan.to_json()

    # Mismatched positional arguments fail strictly without hairy heuristics
    reject('invalid_sources', lambda: compile_flow(sources, target, flow, v))


def test_concurrent_multi_threaded_plan_execution():
    v = vocabulary()
    f = {'steps': [
        {'id': 'a', 'fn': 'text.upper', 'args': {'text': '$p.text'}},
        {'id': 'b', 'fn': 'text.upper', 'args': {'text': '$a.text'}}
    ], 'returns': {'res': '$b.text'}}
    plan = compile_flow(f, {'p': Dict({'text': str})}, Dict({'res': str}), v)

    def worker(i):
        word = f'word_{i}'
        res = execute_flow(plan, {'p': {'text': word}}, vocab=v)
        assert res == {'res': word.upper()}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker, i) for i in range(25)]
        for fut in futures:
            fut.result()


def test_zero_step_transition_flow():
    v = vocabulary()
    f = {'steps': [], 'returns': {'doubled': {'$mul': ['$inputs.n', 2]}}}
    plan = compile_flow(f, {'inputs': Dict({'n': int})}, Dict({'doubled': int}), v)
    assert execute_flow(plan, {'inputs': {'n': 21}}, vocab=v) == {'doubled': 42}


def test_loop_returns_with_state_and_iteration():
    v = vocabulary()
    f = {
        'steps': [{
            'id': 'counter',
            'loop': {
                'init': {'total': 0},
                'max': 10,
                'while': {'$lt': ['$state.total', 15]},
                'steps': [
                    {'id': 'add_five', 'fn': 'math.inc', 'args': {'n': '$state.total'}}
                ],
                'update': {'total': {'$add': ['$state.total', 5]}},
                'returns': {
                    'final_total': '$state.total',
                    'count': '$iteration',
                }
            }
        }],
        'returns': '$counter'
    }
    plan = compile_flow(f, {}, Dict({'final_total': int, 'count': int}), v)
    result = execute_flow(plan, {}, vocab=v)
    assert result == {'final_total': 15, 'count': 3}

    # Verify that iteration-local step 'add_five' cannot be accessed from loop returns
    bad_flow = deepcopy(f)
    bad_flow['steps'][0]['loop']['returns'] = {'leak': '$add_five.value'}
    reject('unknown_source', lambda: compile_flow(bad_flow, {}, Dict({'leak': int}), v))


def test_branch_common_top_level_returns():
    v = vocabulary()
    f = {
        'steps': [{
            'id': 'decision',
            'if': {'$gt': ['$p.score', 50]},
            'then': [{'id': 'tag', 'fn': 'text.upper', 'args': {'text': 'pass'}}],
            'else': [{'id': 'tag', 'fn': 'text.upper', 'args': {'text': 'fail'}}],
            'returns': {'status': '$tag.text', 'threshold': 50}
        }],
        'returns': '$decision'
    }
    plan = compile_flow(f, {'p': Dict({'score': int})},
                        Dict({'status': str, 'threshold': int}), v)
    assert execute_flow(plan, {'p': {'score': 75}}, vocab=v) == {'status': 'PASS', 'threshold': 50}
    assert execute_flow(plan, {'p': {'score': 25}}, vocab=v) == {'status': 'FAIL', 'threshold': 50}

    # Reject if both branch-level returns and arm returns are defined
    f_conflicting = deepcopy(f)
    f_conflicting['steps'][0]['then'] = {'steps': [], 'returns': 'illegal'}
    reject('invalid_grammar', lambda: compile_flow(f_conflicting, {'p': Dict({'score': int})}, Dict({}), v))

