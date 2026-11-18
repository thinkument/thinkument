"""Library ownership, ordinary lowering, shell admission, and shared registration."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest
from bindings2bindingsTM import D
from _thinkprogram._iomicrosTM.core.micro_registry import MICRO_TYPES, MicroTypeDefinition, get_micro_type_definition
from _thinkprogram._iomicrosTM.core.api_coercion import coerce_micro_value
from authoring_funneling.examples.metal import compile_tape
from authoring_funneling.examples.metal.shared_widgets import micros as microtables, registry as thinkwidgets
from authoring_funneling.examples.metal.shared_widgets import widgets
from authoring_funneling.examples.metal import publication as chrometables
from authoring_funneling.examples.metal.shared_rendering import catalogue
from ways_to_create.app_pack_publication_registrar.authoring_profiles import resolve_authoring_profile
from authoring_funneling.a_typed_PSMCW_authoring.authoring import AuthoringError
from authoring_funneling.a_typed_PSMCW_authoring import compile_strict_program
from authoring_funneling.a_typed_PSMCW_authoring.widget import OUTPUT_STATE


def higher(widget=widgets.BOUNDED):
    return {'kind':'think_program_v1','surface_version':'v1','symbols':{},'puppeteering':{},
            'run':{'program':{'info':{'id':'library','title':'Library'},
                'widgets':{'bounded':{'widget':widget,'bindings':{'inputs':{'start':D.value(10)}}}},
                'flow':[{'id':'edit','widgets':['bounded']}]},'config':{}}}


def mounted(cls=widgets.Bounded):
    tape=compile_tape(higher())
    body=tape['P']['run']['program']
    args={**body['widgets']['bounded'].get('args',{}),**body['flow'][0]['overrides']['args']['bounded']}
    events=[]
    widget=cls(q={},emit=lambda payload,**kw: events.append((kw['name'],deepcopy(payload))) or {})
    fill={'fill_shell':{'id':'bounded','args':args,'micros':[]},'current_fills':{}}
    result=widget._on_mount({},fill,{},{} )
    return widget,fill,events,result


def test_shared_catalogue_strict_profiles_and_idempotent_registration():
    before_profiles = dict(MICRO_TYPES)
    tuple(row.authoring_profile_provider() for row in chrometables.publication_rows())
    assert dict(MICRO_TYPES) == before_profiles
    chrometables.register_metal_standard()
    manifests=[row.manifest_provider() for row in chrometables.publication_rows()]
    profiles=[resolve_authoring_profile(m.id) for m in manifests]
    assert profiles[0].describe_widgets()==profiles[1].describe_widgets()
    assert set(w['widget_id'] for w in profiles[0].describe_widgets())==set(thinkwidgets.widget_rows())
    assert all(p.describe()['refined_surfaces']==['W','P'] for p in profiles)
    before={name:get_micro_type_definition(name) for name in microtables.admitted_micros()}
    for manifest in manifests*3:
        receipt=getattr(chrometables,'register_'+manifest.id)()
        assert receipt['app_pack']==manifest.id and receipt['ok']
        assert receipt['runtime_registration']['widgets']==[]
        assert set(receipt['micros'])==set(before)
    assert all(get_micro_type_definition(name) is value for name,value in before.items())


def test_compile_sets_chrome_and_rejects_conflicts_without_mutation():
    source=higher(); sm={'public_ui':{}}
    for row in chrometables.CHROMETABLES:
        tape=compile_tape(source,sm,chrome=row.id)
        assert tape['SM']['app_pack_mould']['app_pack']==row.id
        assert 'bindings' not in json.dumps(tape['P'])
        assert sm=={'public_ui':{}} and source==higher()
        with pytest.raises(AuthoringError,match='selection_mismatch'):
            compile_tape(source,{'app_pack_mould':{'app_pack':'crystal'}},chrome=row.id)
    with pytest.raises(ValueError,match='Unknown chrome'): compile_tape(source,chrome='absent')


def test_effective_C_cannot_change_chrome():
    sm={'symbols':{'selected':{'value':'metal_standard','parametrize':True}},
        'puppeteering':{},
        'app_pack_mould':{'app_pack':'$selected','app_args':{}}}
    # A selected symbolic value can be changed by C through ordinary routing.
    assert compile_tape(higher(),sm)['SM']['app_pack_mould']['app_pack']=='$selected'
    with pytest.raises(AuthoringError,match='selection_mismatch'):
        compile_tape(higher(),sm,{'selected':'metal_compact'})


def test_generated_browser_catalogue_matches_central_sheets():
    assert (catalogue.STATIC_ROOT/'catalogue.js').read_text()==catalogue.browser_catalogue_source()
    assert len(chrometables.shared_static_roots_v1())==1
    for row in chrometables.CHROMETABLES:
        manifest=chrometables.manifest_for(row)
        assert manifest.browser_module_path.is_file()
        assert (manifest.static_root / 'aesthetics.js').is_file()
        assert (manifest.static_root / 'styles.css').is_file()


def test_duplicate_micro_ownership_and_missing_renderer_fail_before_registration(monkeypatch):
    before=dict(MICRO_TYPES)
    basic=microtables.MICRO_TABLES[0]
    with pytest.raises(ValueError,match='more than one subtable'):
        microtables.micro_catalogue((basic,microtables.MicroTable('duplicate',(basic.rows[0],))))
    with pytest.raises(ValueError,match='unique nonempty'):
        microtables.micro_catalogue((basic,basic))
    bad=replace(basic.rows[0],renderer='missing')
    with pytest.raises(ValueError,match='no browser renderer'):
        microtables.micro_catalogue((microtables.MicroTable('bad',(bad,)),))
    assert dict(MICRO_TYPES)==before


def test_cross_table_registration_is_atomic(monkeypatch):
    first=MicroTypeDefinition(name='creativity_test_first',description='First',coerce_to_micro_types=('creativity_test_second',))
    second=MicroTypeDefinition(name='creativity_test_second',description='Second',coerce_to_micro_types=('creativity_test_first',))
    tables=tuple(microtables.MicroTable(str(i),(microtables.MicroRow(d,'text'),)) for i,d in enumerate((first,second)))
    monkeypatch.setattr(microtables,'MICRO_TABLES',tables)
    microtables.admitted_micros.cache_clear()
    try:
        assert microtables.register_microtables_v1()==(first,second)
        assert microtables.register_microtables_v1()==(first,second)
        MICRO_TYPES.pop(first.name);MICRO_TYPES.pop(second.name)
        monkeypatch.setattr(microtables,'MICRO_TABLES',(*tables[:1],microtables.MicroTable('bad',(
            microtables.MicroRow(replace(second,coerce_to_micro_types=('missing_target',)),'text'),))))
        microtables.admitted_micros.cache_clear()
        with pytest.raises(ValueError,match='unknown coercion targets'): microtables.register_microtables_v1()
        assert first.name not in MICRO_TYPES and second.name not in MICRO_TYPES
    finally:
        MICRO_TYPES.pop(first.name,None);MICRO_TYPES.pop(second.name,None)
        microtables.admitted_micros.cache_clear()


def test_builtin_collision_preserves_platform_definition(monkeypatch):
    original=get_micro_type_definition('text')
    table=microtables.MicroTable('collision',(microtables.MicroRow(replace(original,description='Changed'),'text'),))
    monkeypatch.setattr(microtables,'MICRO_TABLES',(table,))
    microtables.admitted_micros.cache_clear()
    try:
        with pytest.raises(ValueError,match='registered differently'): microtables.register_microtables_v1()
        assert get_micro_type_definition('text') is original
    finally: microtables.admitted_micros.cache_clear()


@pytest.mark.parametrize('micros',[
    [{'name':'a','type':'unknown'}],
    [{'name':'a','type':'text'},{'name':'a','type':'integer'}],
    [{'name':'','type':'text'}],
    [{'name':'a','type':'text','render_args':{'not_json':(1,2)}}],
    [{'name':'a','type':'text','render_args':float('nan')}],
])
def test_invalid_shell_is_rejected(micros):
    with pytest.raises((ValueError,TypeError)): microtables.validate_shell({'micros':micros})


def test_descriptor_changes_are_preserved_and_invalid_reexplosion_is_audited_atomically():
    widget,fill,events,result=mounted()
    initial=result.next_fill_shell['micros'][0]
    assert initial['render_args']=={'revision':0,'hints':['0 through 100']}
    fill['fill_shell']=result.next_fill_shell
    result=widget.refresh({'kind':'refresh'},{},fill,{},{} )
    assert result.next_fill_shell['micros'][0]['render_args']['revision']==1
    assert initial['render_args']['revision']==0
    class Broken(widgets.Bounded):
        def _on_fill(self,signal,position,fill_data,limits,stats):
            self.outputs.write('result','value',50)
            return self.replacement(fill_data)
        def replacement(self,fill_data):
            from _thinkprogram.thinkwidgetTM.types import Reexplode
            return Reexplode(next_fill_shell=self.replacement_shell(fill_data['fill_shell'],title='bad',
                micros=[{'name':'bad','type':'unknown'}]),pre_computed_fills={})
    widget,fill,events,result=mounted(Broken)
    before=deepcopy(widget._state[OUTPUT_STATE]);events.clear()
    with pytest.raises(ValueError,match='not admitted'): widget._on_fill({}, {},fill,{},{} )
    assert widget._state[OUTPUT_STATE]==before
    assert [name for name,_ in events]==['audit-ins','audit-error']


def test_bounded_micro_platform_coercion():
    microtables.register_microtables_v1()
    assert coerce_micro_value(raw='42',src_micro_type='creativity_bounded_integer',dst_micro_type='integer')==42
    for value in (-1,101,'oops'):
        with pytest.raises((ValueError,TypeError)): coerce_micro_value(raw=value,src_micro_type='creativity_bounded_integer',dst_micro_type='integer')


def test_stale_browser_projection_fails_before_micro_registration(monkeypatch, tmp_path):
    original=catalogue.browser_catalogue_source()
    (tmp_path/'catalogue.js').write_text(original+'// stale\n')
    monkeypatch.setattr(catalogue,'STATIC_ROOT',tmp_path)
    catalogue.validate_browser_catalogue_v1.cache_clear()
    before=dict(MICRO_TYPES)
    try:
        with pytest.raises(ValueError,match='catalogue is stale'):
            chrometables.register_metal_standard()
        assert dict(MICRO_TYPES)==before
    finally: catalogue.validate_browser_catalogue_v1.cache_clear()


def test_official_metadata_extension_and_template_validate_placements():
    from authoring_funneling.examples.metal import with_aesthetics
    from authoring_funneling.examples.metal.shared_rendering.aesthetics import AESTHETICS_KEY,register_aesthetics_metadata_v1
    from _thinksessions.sesh_metadata.sesh_metadata_surface import coerce_session_metadata,coerce_and_validate_session_metadata_update
    register_aesthetics_metadata_v1()
    sm=with_aesthetics({'manual_io':{'persistence':'disabled'}},widget_placements={'defaults':{'placement':'horizontal'},
        'steps':[{'step':'library.edit','placement':'vertical','visibility':'all_appearances'}]})
    assert coerce_session_metadata(sm)[AESTHETICS_KEY]==sm[AESTHETICS_KEY]
    coerce_and_validate_session_metadata_update({AESTHETICS_KEY:sm[AESTHETICS_KEY]})
    assert compile_tape(higher(),sm)['SM'][AESTHETICS_KEY]==sm[AESTHETICS_KEY]
    for value in ('diagonal',None,[],3):
        with pytest.raises((ValueError,TypeError)):
            coerce_session_metadata({AESTHETICS_KEY:{'widget_placements':{'defaults':{'placement':value}}}})
    with pytest.raises(AuthoringError,match='Unknown placement step'):
        compile_tape(higher(),with_aesthetics(widget_placements={'steps':[{'step':'missing','placement':'horizontal'}]}))


def test_placement_symbols_obey_ordinary_SM_C_routing():
    from authoring_funneling.examples.metal.shared_rendering.aesthetics import AESTHETICS_KEY
    sm={'symbols':{'layout':{'value':'vertical','parametrize':True}},'puppeteering':{},
        AESTHETICS_KEY:{'widget_placements':{'defaults':{'placement':'$layout'}}}}
    export=compile_tape(higher(),sm,{'layout':'horizontal'})
    assert export['C']=={'layout':'horizontal'}
    with pytest.raises(AuthoringError): compile_tape(higher(),sm,{'layout':'unsupported'})


def test_placement_axis_members_are_local_and_scale_from_one_sheet(monkeypatch):
    from authoring_funneling.examples.metal.shared_rendering import aesthetics
    from _thinksessions.sesh_metadata.__sesh_meta_dynamic_augmentation_by_apps import SessionMetadataSurfaceRegistry
    original=deepcopy(aesthetics.PLACEMENT_AXES)
    monkeypatch.setitem(aesthetics.PLACEMENT_AXES,'widgets',{**original['widgets'],'row':'horizontal'})
    try:
        schema=aesthetics.register_aesthetics_metadata_v1()
        assert 'row' in schema['fields']['widget_placements']['fields']['defaults']['fields']['placement']['enum']
        aesthetics.validate_widget_placements({'defaults':{'placement':'row'}})
        with pytest.raises(ValueError,match='Unknown micro placement'):
            microtables.validate_shell({'micros':[],'paquete_micro_placement':'row'})
    finally:
        monkeypatch.setitem(aesthetics.PLACEMENT_AXES,'widgets',original['widgets'])
        aesthetics.register_aesthetics_metadata_v1()


def test_micro_placement_is_emitted_once_on_shell_and_preserved():
    prior={'id':'widget','args':{}}
    shell=thinkwidgets.LibraryWidget.replacement_shell(prior,title='Two micros',
        micros=[{'name':'a','type':'text'},{'name':'b','type':'integer'}],micro_placement='horizontal')
    assert shell['paquete_micro_placement']=='horizontal'
    assert microtables.validate_shell(shell) is shell
    replacement=thinkwidgets.LibraryWidget.replacement_shell(shell,title='Changed',micros=[])
    assert replacement['paquete_micro_placement']=='horizontal'
    assert 'paquete_micro_placement' not in prior
    with pytest.raises(ValueError): microtables.validate_shell({**shell,'paquete_micro_placement':'unknown'})


def test_aesthetics_gateway_merges_without_mutating_and_has_no_legacy_aliases():
    from authoring_funneling.examples import metal as family
    from authoring_funneling.examples.metal.shared_rendering.aesthetics import AESTHETICS_KEY
    source=family.with_aesthetics(widget_placements={'defaults':{'visibility':'all_appearances'}})
    before=deepcopy(source)
    sm=family.with_aesthetics(source,css_injection=[{'target':{},'declarations':{'--accent':'#477650'}}])
    assert source==before and sm[AESTHETICS_KEY]['widget_placements']==source[AESTHETICS_KEY]['widget_placements']
    assert not hasattr(family,'with_widget_placements')
    assert 'paquete_widget_placements' not in __import__(
        '_thinksessions.sesh_metadata.__sesh_meta_dynamic_augmentation_by_apps',fromlist=['SessionMetadataSurfaceRegistry']
    ).SessionMetadataSurfaceRegistry.registered_keys()
    with pytest.raises(KeyError,match='unknown sections'): family.with_aesthetics(missing={})
    with pytest.raises(TypeError): family.with_aesthetics([])


@pytest.mark.parametrize('rule,path',[
    ({'target':{},'declarations':{'color':7}},'declarations.color'),
    ({'target':{'part':'missing'},'declarations':{}},'target.part'),
    ({'target':{'unknown':'x'},'declarations':{}},'target'),
    ({'target':{},'declarations':{},'pseudo_classes':[7]},'pseudo_classes\\[0\\]'),
    ({'target':{},'declarations':{},'media':False},'media'),
    ({'declarations':{}},'target'),
    ({'target':{}},'declarations'),
])
def test_official_css_schema_validates_initial_metadata_and_partial_updates(rule,path):
    from authoring_funneling.examples.metal.shared_rendering.aesthetics import register_aesthetics_metadata_v1
    from _thinksessions.sesh_metadata.sesh_metadata_surface import coerce_session_metadata,coerce_and_validate_session_metadata_update
    register_aesthetics_metadata_v1()
    for validate in (coerce_session_metadata,coerce_and_validate_session_metadata_update):
        with pytest.raises((ValueError,TypeError,KeyError),match=path):
            validate({'paquete_aesthetics':{'css_injection':[rule]}})


def test_css_symbols_and_C_resolve_before_effective_target_validation():
    from authoring_funneling.examples.metal import with_aesthetics
    sm=with_aesthetics({'symbols':{'accent':{'value':'green','parametrize':True},
                                 'step':{'value':'library.edit','parametrize':True}},'puppeteering':{}},
        css_injection=[{'target':{'step':'$step','part':'control'},'declarations':{'color':'$accent','--accent':'$accent'}}])
    assert compile_tape(higher(),sm,{'accent':'red'})['SM']['paquete_aesthetics']['css_injection'][0]['declarations']['color']=='$accent'
    with pytest.raises(AuthoringError,match=r'css_injection\[0\].target.step') as error:
        compile_tape(higher(),sm,{'step':'library.missing'})
    assert error.value.details['path']==['SM','paquete_aesthetics','css_injection',0,'target','step']
    with pytest.raises(AuthoringError): compile_tape(higher(),sm,{'accent':3})


def test_missing_aesthetic_behavior_reference_fails_registration(monkeypatch):
    from authoring_funneling.examples.metal.shared_rendering import aesthetics
    monkeypatch.setitem(aesthetics.AESTHETICS_SECTIONS,'missing',{
        'schema':lambda:{'type':'string'},'validator':lambda *a,**kw:None,'browser':'absent'})
    with pytest.raises(ValueError,match='no browser behavior'): aesthetics.register_aesthetics_metadata_v1()
