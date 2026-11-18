"""JSON lifecycle compilation, state isolation, static rejection and rollback."""
from copy import deepcopy
import json
import pytest
from bindings2bindingsTM import Dict, Str, Int, Nullable, List, Map, normalize
from JSONfnchainTM import FlowCompilationError, FlowRuntimeError
from authoring_funneling import compile_strict_program
from authoring_funneling.b_typed_JSON_widget_declaration import (
    normalize_port_schema_v1, prepare_json_widget_v1, register_prepared_json_widget_v1,
)
from authoring_funneling.a_typed_PSMCW_authoring.widget import OUTPUT_STATE


def manifest(name='json_test.counter'):
    return {'kind':'json_widget_v1','name':name,'declaration':{'outputs':{'result':{'count':'int'}}},
            'signals':{
                'mount':{'outputs':{'result':{'count':0}},'reexplode':{'title':'Counter','micros':[{'name':'answer','type':'text'}]}},
                'fill':{'done':True,'keep':'*'},
                'increment':{'outputs':{'result':{'count':{'$add':['$prior_outputs.result.count',1]}}},
                             'reexplode':{'title':'Counter','micros':[{'name':'answer','type':'text'}]}}
            }}


def program(name):
    return {'kind':'think_program_v1','surface_version':'v1','symbols':{},'puppeteering':{},
            'run':{'program':{'info':{'id':'json_test','title':'JSON'},
                             'widgets':{'w':{'widget':name,'bindings':{}}},
                             'flow':[{'id':'first','widgets':['w']}]},'config':{}}}


def mounted(raw=None, **kwargs):
    raw = raw or manifest()
    # Every prepared JSON ID is immutable; tests use a fresh stable identifier
    # for each independently compiled variant.
    raw = deepcopy(raw)
    raw['name'] = raw['name'] + '.case_' + str(next(_PREPARED_CASES))
    cls = register_prepared_json_widget_v1(prepare_json_widget_v1(raw, **kwargs))
    compiled = compile_strict_program(program(raw['name']))
    args = {**compiled['run']['program']['widgets']['w']['args'],
            **compiled['run']['program']['flow'][0]['overrides']['args']['w']}
    events = []
    def emit(payload, *, name, **_kwargs): events.append((name, deepcopy(payload))); return {}
    widget = cls(q={'form_id':'f','frame_id':'fr','span_id':'s','datum_id':'w'}, emit=emit)
    fill = {'fill_shell':{'id':'w','args':args,'micros':[]}, 'current_fills':{}}
    result = widget._on_mount({},fill,{},{} )
    fill['fill_shell'] = result.next_fill_shell
    return widget, fill, events


from itertools import count
_PREPARED_CASES = count()

@pytest.mark.parametrize('raw,expected', [('str',Str), ('str?',Nullable(Str)), (['int'],List(Int)),
                                         ({'a':'str'},Dict({'a':Str})),
                                         ({'type':'map','key':'str','value':'int'},Map(Int))])
def test_schema_normalization(raw,expected):
    assert normalize_port_schema_v1(raw) == normalize(expected)


def test_mount_fill_signal_and_scope_isolation():
    widget, fill, events = mounted()
    scope = widget._build_root_scope(fill,{})
    scope['prior_outputs']['result']['count']=999
    assert widget.outputs.read('result','count')==0
    widget.json_signal_increment({'kind':'increment'},{},fill,{},{} )
    assert widget.outputs.read('result','count')==1
    assert widget._on_fill({}, {},fill,{},{} ) is True
    assert [name for name,_ in events]==['audit-ins','audit-outs']*3

@pytest.mark.parametrize('change', ['kind','mount','output','function','unknown','ambiguous'])
def test_static_rejection(change):
    raw=manifest()
    if change=='kind':raw.pop('kind')
    if change=='mount':raw['signals'].pop('mount')
    if change=='output':raw['declaration']['outputs']['result']='str'
    if change=='function':raw['signals']['fill']['steps']=[{'id':'x','fn':'unsafe.eval'}]
    if change=='unknown':raw['signals']['fill']['unexpected']=True
    if change=='ambiguous':raw['signals']['fill']['reexplode']={'title':'Bad','micros':[{'name':'a','type':'text'}]}
    with pytest.raises(FlowCompilationError):prepare_json_widget_v1(raw)


def test_invalid_result_rolls_back_and_audits_error():
    raw=manifest();raw['signals']['increment']={'done':False,'outputs':{'result':{'count':9}}}
    widget,fill,events=mounted(raw)
    with pytest.raises(ValueError):widget.json_signal_increment({}, {},fill,{},{} )
    assert widget._state[OUTPUT_STATE]=={'result':{'count':0}}
    assert events[-1][0]=='audit-error'


def test_duplicate_json_keys_rejected():
    with pytest.raises(FlowCompilationError):prepare_json_widget_v1('{"kind":"json_widget_v1","kind":"bad"}')


def test_prepare_is_pure_and_explicit_registration_is_immutable():
    from authoring_funneling.b_typed_JSON_widget_declaration import (
        prepare_json_widget_v1, register_prepared_json_widget_v1,
    )
    from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
        kernel_widget_class_repr_v1,
    )
    raw = manifest('json_test.prepared_immutable')
    with pytest.raises((ValueError, KeyError, TypeError)):
        kernel_widget_class_repr_v1(raw['name'])
    prepared = prepare_json_widget_v1(raw)
    assert prepared.widget_id == raw['name']
    with pytest.raises((ValueError, KeyError, TypeError)):
        kernel_widget_class_repr_v1(raw['name'])
    cls = register_prepared_json_widget_v1(prepared)
    assert register_prepared_json_widget_v1(prepared) is cls
    changed = manifest(raw['name'])
    changed['title'] = 'Changed source'
    with pytest.raises(ValueError, match='different content'):
        register_prepared_json_widget_v1(prepare_json_widget_v1(changed))


@pytest.mark.parametrize('fails', [False, True])
def test_parallel_vendor_attempts_settle_and_release_before_return(fails):
    from threading import Barrier, Lock
    from types import SimpleNamespace
    from wallet_economics.usage import VendorResult
    from authoring_funneling.b_typed_JSON_widget_declaration import VendorBinding
    from epsilinesTM_serveragnostic.subapps.economics import bind_provider_v1
    from epsilinesTM_serveragnostic.subapps.economics.contracts import ReservationReceipt, ChargeReceipt
    from ..service_ready_computation.test_economics_widget_mould import receipt
    from ..service_ready_computation.test_economics_pricing import DESCRIPTOR
    barrier=Barrier(2); lock=Lock(); calls=[]
    class Provider:
        def reserve(self, request):
            with lock:calls.append(('reserve',request.call_key))
            return ReservationReceipt(request.call_key,'held',100,'policy','hash',{},True)
        def charge(self,rid,usage):
            with lock:calls.append(('charge',rid))
            return ChargeReceipt(
                charge_id='charge:'+rid,
                reservation_id=rid,
                settlement_status='settled',
                estimated_microcredits=10,
                calculated_microcredits=10,
                charged_microcredits=10,
                refunded_microcredits=0,
                excess_microcredits=0,
                estimated_vendor_cost_usd='0.01',
                calculated_vendor_cost_usd='0.01',
                customer_price_usd='0.012',
                policy_version='policy',
                policy_hash='hash',
                correlation={},
            )
        def release(self,rid):
            with lock:calls.append(('release',rid))
    class Prepared:
        descriptor=DESCRIPTOR
        def __init__(self,prompt):self.prompt=prompt
        def execute(self, *, client):
            barrier.wait(timeout=10)
            if fails and self.prompt=='a':raise ValueError('provider failed')
            return VendorResult({'text':self.prompt},receipt())
    binding=VendorBinding(lambda args:{'prepared':Prepared(args['prompt']),'client':None,'maximum_units':{'item':10}},
                          lambda result:{'text':result.value['text'],'usage':{'prompt_tokens':1,'completion_tokens':1}})
    raw=manifest('json_test.parallel')
    raw['signals']['increment']={'execution':'sync', 'steps':[{'id':'both','parallel':[
        {'id':name,'fn':'vendor.llm.chat_completion','args':{'prompt':name,'model':None,'temperature':None}}
        for name in ('a','b')]}], 'done':True, 'outputs':{'result':{'count':2}}}
    widget,fill,events=mounted(raw,vendor_bindings={'vendor.llm.chat_completion':binding})
    with bind_provider_v1(Provider()):
        if fails:
            with pytest.raises(FlowRuntimeError):widget.json_signal_increment({}, {},fill,{},{} )
        else:widget.json_signal_increment({}, {},fill,{},{} )
    reserved=[key for kind,key in calls if kind=='reserve']
    assert len(reserved)==len(set(reserved))==2
    released = sorted(key for kind,key in calls if kind=='release')
    charged = sorted(key for kind,key in calls if kind=='charge')
    assert sorted(released + charged) == sorted(reserved)
    assert set(released).isdisjoint(charged)
    assert len([1 for kind,key in calls if kind=='charge'])==(1 if fails else 2)
    assert widget.outputs.read('result','count')==(0 if fails else 2)
    operation=events[-1][1]['operation_id']
    indexes=[payload['event_index'] for _,payload in events if payload['operation_id']==operation]
    assert indexes==list(range(len(indexes)))


@pytest.mark.parametrize('name,args,expected', [
    ('text.template', {'template':'Hello {{name}}','vars':{'name':'world'}}, {'text':'Hello world'}),
    ('text.concat', {'parts':['a','b'],'sep':'/'}, {'text':'a/b'}),
    ('math.add', {'a':2.0,'b':3.0}, {'result':5.0}),
    ('math.multiply', {'a':2.0,'b':3.0}, {'result':6.0}),
    ('data.extract', {'source':{'a':'found'},'key':'a'}, {'value':'found'}),
    ('data.extract', {'source':{'a':'found'},'key':'missing'}, {'value':None}),
])
def test_approved_transform_contracts(name,args,expected):
    from JSONfnchainTM import compile_flow, execute_flow, FlowPlan
    from authoring_funneling.b_typed_JSON_widget_declaration import create_default_vocab
    vocab=create_default_vocab()
    plan=compile_flow({'steps':[{'id':'result','fn':name,'args':args}], 'returns':'$result'}, {}, None, vocab)
    restored=FlowPlan.from_json(plan.to_json(),vocab=vocab)
    assert execute_flow(restored,{},vocab=vocab)==expected


def test_legacy_transitions_manifest_is_rejected():
    from authoring_funneling import StrictServiceWidget, ServiceReadyWidget
    raw=manifest('json_test.legacy');signals=raw.pop('signals')
    raw['transitions']={key:signals[key] for key in ('mount','fill')}
    raw['transitions']['signals']={'increment':signals['increment']}
    with pytest.raises(FlowCompilationError):
        prepare_json_widget_v1(raw)


def test_unbound_vendor_signal_fails_closed_and_preserves_state():
    raw=manifest('json_test.unbound')
    raw['signals']['increment']={'execution':'sync', 'steps':[{'id':'call','fn':'vendor.embeddings.generate',
        'args':{'text':'sample','model':None}}], 'done':True, 'keep':'*'}
    widget,fill,events=mounted(raw)
    with pytest.raises(FlowRuntimeError,match='No trusted vendor binding'):
        widget.json_signal_increment({}, {},fill,{},{} )
    assert widget.outputs.read('result','count')==0
    assert events[-1][0]=='audit-error'


@pytest.mark.parametrize('micros,fills', [
    ([{'name':'same','type':'text'},{'name':'same','type':'text'}],{}),
    ([{'name':'answer','type':'text'}],{'unknown':'bad'}),
])
def test_invalid_replacement_shell_is_not_committed(micros,fills):
    raw=manifest('json_test.bad_shell')
    raw['signals']['increment']={'reexplode':{'title':'Bad','micros':micros,'pre_computed_fills':fills},
                                 'outputs':{'result':{'count':999}}}
    widget,fill,events=mounted(raw)
    with pytest.raises(ValueError):widget.json_signal_increment({}, {},fill,{},{} )
    assert widget.outputs.read('result','count')==0


def test_prepared_registration_rejects_wrong_artifact_types_and_proofs():
    from dataclasses import replace
    from authoring_funneling.b_typed_JSON_widget_declaration import (
        PreparedJsonWidgetV1, register_prepared_json_widget_v1,
    )
    artifact = prepare_json_widget_v1(manifest('json_test.registration_boundary'))
    with pytest.raises(TypeError):
        register_prepared_json_widget_v1(object())
    forged = replace(artifact, _proof=object())
    with pytest.raises(ValueError, match='must come from'):
        register_prepared_json_widget_v1(forged)
    forged_class = replace(artifact, widget_class=type('Forged', (), {}))
    with pytest.raises(TypeError, match='inherit JsonDefinedLibraryWidget'):
        register_prepared_json_widget_v1(forged_class)


def test_strict_registration_rejects_unprepared_and_different_existing_class():
    from authoring_funneling.a_typed_PSMCW_authoring.contracts import (
        prepare_strict_widget, register_prepared_strict_widget_v1,
    )
    from authoring_funneling.a_typed_PSMCW_authoring.widget import StrictServiceWidget
    from authoring_funneling.examples.metal.shared_widgets.base import LibraryWidget
    with pytest.raises(TypeError, match='not prepared'):
        register_prepared_strict_widget_v1(type('Unprepared', (StrictServiceWidget,), {}))
    name = 'json_test.strict_boundary'
    def concrete(name):
        def mount(self, position, fill_data, limits, stats): return True
        def fill(self, signal, position, fill_data, limits, stats): return True
        return type(name, (LibraryWidget,), {'_on_mount': mount, '_on_fill': fill})
    first = prepare_strict_widget(name, outputs={'result': Dict({'value': Int})})(
        concrete('StrictBoundaryA')
    )
    register_prepared_strict_widget_v1(first)
    other = prepare_strict_widget(name, outputs={'result': Dict({'value': Int})})(
        concrete('StrictBoundaryB')
    )
    with pytest.raises(ValueError, match='already registered to a different class'):
        register_prepared_strict_widget_v1(other)


def test_gateway_binding_rejects_unavailable_routes_and_mismatched_prepared_calls(monkeypatch):
    from types import SimpleNamespace
    from authoring_funneling.b_typed_JSON_widget_declaration import (
        create_gateway_vendor_binding,
    )
    class Ops:
        api_provider_id = 'vercel'
        def __init__(self, row): self.row = row
        def get_operation(self, operation_id):
            if operation_id == 'missing': raise KeyError(operation_id)
            return self.row
    with pytest.raises(ValueError, match='unavailable'):
        create_gateway_vendor_binding(Ops({'eligibility': 'configured'}), 'missing',
                                     request=lambda args: {}, project=lambda result: result)
    with pytest.raises(ValueError, match='unavailable'):
        create_gateway_vendor_binding(Ops({'eligibility': 'excluded'}), 'I1',
                                     request=lambda args: {}, project=lambda result: result)
    binding = create_gateway_vendor_binding(Ops({'eligibility': 'configured'}), 'I1',
        request=lambda args: {}, project=lambda result: result)
    call = SimpleNamespace(descriptor=SimpleNamespace(vendor='vercel', operation='T1'),
                           prepared=SimpleNamespace(operation_id='T1'), maximum_units={})
    import gateway_lab.thinkwidget_economics as gateway_economics
    monkeypatch.setattr(gateway_economics, 'prepare_gateway_vendor_call',
                        lambda *args, **kwargs: call)
    context = SimpleNamespace(host_context={'operation_id': 'widget-op', 'vendor_bindings': {},
        'owner_thread': __import__('threading').get_ident(),
        'widget': SimpleNamespace(execute_vendor_operation_v1=lambda **kwargs: None)}, attempt_id='attempt')
    with pytest.raises(ValueError, match='trusted route binding'):
        binding.execute(context, {'prepared_call': call})
