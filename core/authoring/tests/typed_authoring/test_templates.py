import json
import pytest
from bindings2bindingsTM import CompilationError,D
from authoring_funneling.a_typed_PSMCW_authoring import *
from authoring_funneling.examples.metal.shared_widgets.widgets import SEED,CONSUMER,COUNTER
from _thinkprogram.thinkprogramTM.api import lower_think_program_to_kernel_program_v1


def higher():
    return {'kind':'think_program_v1','surface_version':'v1','symbols':{},'puppeteering':{},'run':{'program':{'info':{'id':'typed_test','title':'Typed'},'widgets':{'writer':{'widget':SEED,'args':{},'bindings':{}},'counter':{'widget':COUNTER,'args':{},'bindings':{'sources':{'draft':{'widget':'writer','port':'result'}},'inputs':{'start':D.ref('draft','count')}}}},'flow':[{'id':'seed','widgets':['writer']},{'id':'count','widgets':['counter']}]},'config':{}}}


def test_ordinary_export_and_dollar_isolation():
    h=higher();h['run']['program']['widgets']['counter']['bindings']['inputs']['start']=D.value(4)
    p=compile_strict_program(h)
    assert h['run']['program']['widgets']['counter']['bindings']['inputs']['start']==D.value(4)
    assert 'bindings' not in json.dumps(p)
    lowered=lower_think_program_to_kernel_program_v1(p)
    assert lowered
    p2=compile_strict_tape(h,{},None)
    assert set(p2)=={'profile_id','P','SM','C','widget_ids','contract_fingerprint'}

@pytest.mark.parametrize('kind',['future','missing','unknown_port','reserved','incomplete','untyped'])
def test_static_rejections(kind):
    h=higher();b=h['run']['program']['widgets']['counter']['bindings']
    if kind=='future': h['run']['program']['flow'].reverse()
    if kind=='missing': b['sources']['draft']['widget']='absent'
    if kind=='unknown_port': b['sources']['draft']['port']='nope'
    if kind=='reserved': h['run']['program']['widgets']['counter']['args']['strict_binding_recipe_v1']='fake'
    if kind=='incomplete': b['inputs']={}
    if kind=='untyped': h['run']['program']['widgets']['counter']['widget']='packito.choice.v1'
    with pytest.raises((CompilationError,ValueError)): compile_strict_program(h)


def test_override_replaces_named_expression_and_self_previous():
    h=higher();h['run']['program']['flow'].append({'id':'count_again','widgets':['counter'],'overrides':{'bindings':{'counter':{'sources':{'draft':{'widget':{'self':'previous'},'port':'result'}},'inputs':{'start':D.ref('draft','count')}}}}})
    p=compile_strict_program(h)
    recipe=p['run']['program']['flow'][-1]['overrides']['args']['counter']['strict_binding_recipe_v1']
    assert json.loads(recipe)['sources']['draft']['step']=='typed_test.count'


def test_import_templates_does_not_compile_teaching_series():
    import subprocess,sys
    subprocess.run([sys.executable,'-c',"import sys; import authoring_funneling.a_typed_PSMCW_authoring; assert not any(n.startswith('authoring_funneling.examples.metal.examples.') for n in sys.modules)"],check=True)


def test_parameters_C_validation_and_runtime_later_changes():
    from copy import deepcopy
    from authoring_funneling.examples.metal.examples.program4__static_export_and_parameters import HIGHER_P,SESSION_METADATA
    good=compile_strict_tape(HIGHER_P,SESSION_METADATA,{'ui.label':'Changed'})
    assert good['C']=={'ui.label':'Changed'}
    with pytest.raises(CompilationError): compile_strict_tape(HIGHER_P,SESSION_METADATA,{'ui.label':2})


def test_contract_fingerprint_and_cached_recipe_change():
    from copy import deepcopy
    from authoring_funneling.a_typed_PSMCW_authoring.examples.widget import declare_widget
    from bindings2bindingsTM import BindingPlan
    id='typed_test.contract_refresh.v1'
    @strict_widget(id,inputs={'context':str},outputs={'result':Dict({'title':str})})
    class First(StrictServiceWidget):
        def _on_mount(self,*a):self.outputs.write('result','title',self.mouth.read('context'));return True
        def _on_fill(self,*a):self.outputs.keep_port('result');return True
    h={'kind':'think_program_v1','surface_version':'v1','symbols':{},'puppeteering':{},'run':{'program':{'info':{'id':'fingerprint','title':'Contract'},'widgets':{'w':{'widget':id,'bindings':{'inputs':{'context':D.value('value')}}}},'flow':[{'id':'w','widgets':['w']}]},'config':{}}}
    first=compile_strict_tape(h)
    old_recipe=json.loads(first['P']['run']['program']['flow'][0]['overrides']['args']['w']['strict_binding_recipe_v1'])['inputs']['context']
    BindingPlan.from_json(old_recipe)
    second_id='typed_test.contract_refresh.v2'
    @strict_widget(second_id,inputs={'context':Nullable(str)},outputs={'result':Dict({'title':str})})
    class Second(First): pass
    h2=deepcopy(h)
    h2['run']['program']['widgets']['w']['widget']=second_id
    second=compile_strict_tape(h2)
    new_recipe=json.loads(second['P']['run']['program']['flow'][0]['overrides']['args']['w']['strict_binding_recipe_v1'])['inputs']['context']
    assert first['contract_fingerprint']!=second['contract_fingerprint']
    assert old_recipe!=new_recipe
    assert BindingPlan.from_json(old_recipe).evaluate({})==BindingPlan.from_json(new_recipe).evaluate({})=='value'

@pytest.mark.parametrize('value',['$topology.id',' padded ',''])
def test_source_availability_rejects_dynamic_or_noncanonical_topology(value):
    h=higher();h['run']['program']['info']['id']=value
    with pytest.raises(CompilationError) as error: compile_strict_program(h)
    assert error.value.details['code']=='literal_topology_required'


def test_higher_program_v2_expressions_and_sugar():
    """Verify higher typed programs can use v2 operators and compact sugar."""
    from bindings2bindingsTM import BindingPlan
    h = higher()
    h['run']['program']['widgets']['counter']['bindings']['inputs']['start'] = {
        "$cond": [{"$gt": ["$draft.count", 0]}, "$draft.count", 1]
    }
    p = compile_strict_program(h)
    recipe_json = p['run']['program']['flow'][-1]['overrides']['args']['counter']['strict_binding_recipe_v1']
    bundle = json.loads(recipe_json)
    plan = BindingPlan.from_json(bundle['inputs']['start'])
    assert plan.target_type.kind == 'int'
    assert plan.evaluate({'draft': {'count': 42}}) == 42
    assert plan.evaluate({'draft': {'count': 0}}) == 1

