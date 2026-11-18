from copy import deepcopy
import pytest
from authoring_funneling.examples.crystal.publication import authoring_profile_v1
from authoring_funneling.examples.crystal.examples.typed_flow import CRYSTAL_FLOW_P
from authoring_funneling.a_typed_PSMCW_authoring.authoring import AuthoringError


def draft():
    from authoring_funneling.examples.crystal.declare_pack import register_app_pack_v1
    register_app_pack_v1()
    p = authoring_profile_v1()
    return {
        'profile_id': p.profile_id,
        'W': sorted(w['widget'] for w in CRYSTAL_FLOW_P['run']['program']['widgets'].values()),
        'P': deepcopy(CRYSTAL_FLOW_P),
        'SM': {},
        'C': None,
    }


def test_crystal_is_typed_and_needs_no_chrome_fields():
    p = authoring_profile_v1()
    result = p.compile(draft())
    assert result['SM']['app_pack_mould']['app_pack'] == 'crystal'
    assert 'paquete_aesthetics' not in result['SM']
    assert {w['widget_id'] for w in p.describe_widgets()} == {
        'crystal.seed', 'crystal.consumer', 'crystal.json_ideator',
    }


def test_crystal_json_widget_compiles_in_the_same_strict_profile():
    # Runtime restoration belongs to the explicit manifest registrar; profile
    # construction remains a descriptor-only operation.
    from authoring_funneling.examples.crystal.declare_pack import register_app_pack_v1
    register_app_pack_v1()
    p = authoring_profile_v1()
    json_flow = deepcopy(CRYSTAL_FLOW_P)
    json_flow['run']['program']['widgets'] = {
        'ideator': {'widget': 'crystal.json_ideator', 'args': {}, 'bindings': {}},
    }
    json_flow['run']['program']['flow'] = [{'id': 'ideas', 'widgets': ['ideator']}]
    compiled = p.compile({
        'profile_id': p.profile_id,
        'W': ['crystal.json_ideator'],
        'P': json_flow,
        'SM': {},
        'C': None,
    })
    assert compiled['SM']['app_pack_mould']['app_pack'] == 'crystal'
    assert 'paquete_aesthetics' not in compiled['SM']
    assert {w['widget_id'] for w in p.describe_widgets()} >= {'crystal.json_ideator'}


def test_crystal_rejects_wrong_pack_before_and_after_composition():
    p = authoring_profile_v1()
    d = draft()
    d['SM'] = {'app_pack_mould': {'app_pack': 'metal_standard'}}
    with pytest.raises(AuthoringError):
        p.compile(d)
    d = draft()
    d['SM'] = {
        'symbols': {'selected': {'value': 'crystal', 'parametrize': True}},
        'puppeteering': {},
        'app_pack_mould': {'app_pack': '$selected'},
    }
    assert p.compile(d)['SM']['app_pack_mould']['app_pack'] == '$selected'
    d['C'] = {'selected': 'metal_compact'}
    with pytest.raises(AuthoringError):
        p.compile(d)
