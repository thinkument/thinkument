from copy import deepcopy
import json
import pytest
from bindings2bindingsTM import RuntimeValueError,D,Dict,Nullable,List
from authoring_funneling.a_typed_PSMCW_authoring import StrictServiceWidget,strict_widget,analytica_signal_catcher,compile_strict_program
from authoring_funneling.a_typed_PSMCW_authoring.widget import OUTPUT_STATE,MOUTH_STATE,CONFIG_STATE
from authoring_funneling.examples.metal.shared_widgets.widgets import Counter,COUNTER
from .test_templates import higher


def mounted(cls=Counter, *, fail=False):
    h=higher();w=h['run']['program']['widgets']['counter'];w['bindings']={'inputs':{'start':D.value(2)}};w['args']['fail']=fail
    p=compile_strict_program(h)
    args={**p['run']['program']['widgets']['counter']['args'],**p['run']['program']['flow'][1]['overrides']['args']['counter']}
    events=[]
    def emit(payload,*,name,**_kwargs): events.append({'name':name,'payload':deepcopy(payload)});return {}
    widget=cls(q={},emit=emit)
    fill={'fill_shell':{'id':'counter','args':args,'micros':[]},'current_fills':{}}
    result=widget._on_mount({},fill,{},{} )
    return widget,fill,events,result


def assert_operation(events,terminal):
    assert [e['name'] for e in events]==['audit-ins',terminal]
    assert events[0]['payload']['operation_id']==events[1]['payload']['operation_id']


def test_complete_mount_signal_inheritance_and_captured_mouth():
    class Child(Counter): pass
    widget,fill,events,result=mounted(Child)
    assert_operation(events,'audit-outs')
    assert widget.outputs.read('result','count')==2
    assert '__kernel' not in widget.configuration
    assert 'strict_binding_recipe_v1' not in widget.configuration
    fill['fill_shell']=result.next_fill_shell
    assert 'strict_binding_recipe_v1' not in fill['fill_shell']['args']
    events.clear();widget.increment({'kind':'increment'},{},fill,{},{} )
    assert_operation(events,'audit-outs')
    assert widget.outputs.read('result','count')==3
    assert widget.mouth.read('start')==2
    events.clear();fill['current_fills']={'finish':'done'}
    assert widget._on_fill({}, {},fill,{},{} ) is True
    assert_operation(events,'audit-outs')
    assert widget.outputs.read('result','note')=='done'


def test_error_atomic_and_audited():
    widget,fill,events,result=mounted(fail=True)
    before=widget.outputs.read('result','count');events.clear();fill['current_fills']={'finish':'discard me'}
    with pytest.raises(ValueError,match='deliberate'): widget._on_fill({}, {},fill,{},{} )
    assert_operation(events,'audit-error')
    assert widget.outputs.read('result','count')==before
    assert widget.outputs.read('result','note') is None


def test_incomplete_false_and_undeclared_state():
    class Missing(Counter):
        def _on_fill(self,*args): self.outputs.keep('result','count');return True
    widget,fill,events,result=mounted(Missing);events.clear()
    with pytest.raises(RuntimeValueError,match='incomplete_outputs'): widget._on_fill({}, {},fill,{},{} )
    assert_operation(events,'audit-error')
    assert widget.outputs.read('result','note') is None
    with pytest.raises(RuntimeValueError): widget.public=1
    with pytest.raises(RuntimeValueError): del widget.public
    class FalseResult(Counter):
        def _on_fill(self,*args): self.outputs.keep_port('result');return False
    widget,fill,events,result=mounted(FalseResult);events.clear()
    with pytest.raises(RuntimeValueError,match='strict_transition_outcome'): widget._on_fill({}, {},fill,{},{} )
    assert_operation(events,'audit-error')


def test_atomic_batches_distinct_keys_and_null_helpers():
    widget,fill,events,result=mounted()
    widget._strict_staged={}
    with pytest.raises(RuntimeValueError): widget.outputs.write_many({'result':{'count':8,'note':9}})
    assert widget._strict_staged=={}
    widget.outputs.write('result','count',1);widget.outputs.write('result','count',2)
    assert widget._strict_staged=={'result':{'count':2}}
    widget.outputs.write_null('result','note')
    assert widget.outputs.read_or('result','note','fallback')=='fallback'
    assert widget.outputs.read_or('result','count',7)==2
    with pytest.raises(RuntimeValueError): widget.outputs.require_value('result','note')
    assert widget.mouth.require_value('start')==2


def test_direct_and_inherited_overrides_have_one_operation():
    class Changed(Counter):
        def _on_fill(self,*args): self.outputs.keep_port('result');return True
    widget,fill,events,result=mounted(Changed);events.clear()
    widget._on_fill({}, {},fill,{},{} )
    assert_operation(events,'audit-outs')


def test_no_accepted_reads_at_mount_and_detached_mutables():
    @strict_widget('typed_test.mutable.v1',overwrite=True,outputs={'result':Dict({'items':List(int)})})
    class Mutable(StrictServiceWidget):
        def _on_mount(self,*args): self.outputs.write('result','items',[1]);return True
        def _on_fill(self,*args): self.outputs.keep_port('result');return True
    widget=Mutable(q={},emit=lambda *a,**k:{})
    with pytest.raises(RuntimeValueError): widget.outputs.read('result','items')
    widget._state[OUTPUT_STATE]={'result':{'items':[1]}}
    read=widget.outputs.read('result','items');read.append(2)
    assert widget.outputs.read('result','items')==[1]


def test_binding_projection_counts_and_inherited_analytics_payload_costs(monkeypatch):
    from time import perf_counter
    from bindings2bindingsTM import runtime
    from .test_templates import higher
    @strict_widget('typed_test.cost_source.v1',overwrite=True,outputs={'result':Dict({'title':str,'unrelated':List(int)})})
    class Source(StrictServiceWidget):
        def _on_mount(self,*a): self.outputs.write_port('result',{'title':'selected','unrelated':[]});return True
        def _on_fill(self,*a):self.outputs.keep_port('result');return True
    @strict_widget('typed_test.cost_consumer.v1',overwrite=True,args={'size':{'type':'int','default':0}},inputs={'title':str},outputs={'result':Dict({'items':List(int)})})
    class CostConsumer(StrictServiceWidget):
        def _on_mount(self,*a): self.outputs.write('result','items',list(range(self.configuration['size'])));return True
        def _on_fill(self,*a):self.outputs.keep_port('result');return True
    h=higher();body=h['run']['program']
    body['widgets']={'source':{'widget':'typed_test.cost_source.v1'},'consumer':{'widget':'typed_test.cost_consumer.v1','bindings':{'sources':{'s':{'widget':'source','port':'result'}},'inputs':{'title':D.ref('s','title')}}}}
    body['flow']=[{'id':'source','widgets':['source']},{'id':'consumer','widgets':['consumer']}]
    p=compile_strict_program(h);args=p['run']['program']['flow'][1]['overrides']['args']['consumer']
    original=runtime.validate;calls=[]
    def counted(value,schema,path=()):calls.append(schema.kind);return original(value,schema,path)
    monkeypatch.setattr(runtime,'validate',counted)
    for payload_size,output_size in ((0,0),(1000,0),(1000,1000)):
        row={'key':'source','public_step_name':'typed_test.source','value':{'state':{OUTPUT_STATE:{'result':{'title':'selected','unrelated':list(range(payload_size))}}}}}
        fill={'fill_shell':{'args':{**args,'size':output_size,'__kernel':{'past_wires':{'strict_sources_v1':[row]}}}},'current_fills':{}}
        events=[]
        widget=CostConsumer(q={},emit=lambda payload,**kw:events.append(deepcopy(payload)) or {})
        calls.clear();start=perf_counter();widget._on_mount({},fill,{},{});elapsed=perf_counter()-start
        assert calls==['str']
        assert len(events[0]['body']['history_wires']['strict_sources_v1'][0][OUTPUT_STATE]['result']['unrelated'])==payload_size
        writes=events[1]['body']['state_writes']
        assert writes[MOUTH_STATE]=={'title':'selected'}
        assert len(writes[OUTPUT_STATE]['result']['items'])==output_size
        print({'selected_wire_items_copied_by_analytics':payload_size,'output_items':output_size,'binding_projection_validations':len(calls),'total_widget_seconds':elapsed})


def test_runtime_parameter_failure_is_one_audited_operation():
    h=higher();body=h['run']['program'];h['symbols']={'start':{'value':3,'parametrize':True}}
    body['widgets']['counter']['bindings']={'parameters':{'start':{'type':int,'value':'$start'}},'inputs':{'start':D.ref('parameters','start')}}
    p=compile_strict_program(h)
    args=p['run']['program']['flow'][1]['overrides']['args']['counter']
    args['strict_binding_parameters_v1']={'start':'bad'}
    events=[]
    widget=Counter(q={},emit=lambda payload,**kw:events.append({'name':kw['name'],'payload':deepcopy(payload)}) or {})
    with pytest.raises(RuntimeValueError): widget._on_mount({}, {'fill_shell':{'args':args},'current_fills':{}},{},{})
    assert_operation(events,'audit-error')
    assert events[-1]['payload']['body']['details']['code']=='value_type'
