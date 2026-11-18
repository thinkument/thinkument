from copy import deepcopy
import json
import pytest
from ways_to_create.app_pack_publication_registrar.authoring_profiles import resolve_authoring_profile
from ways_to_create.app_pack_publication_registrar.contracts import PackPublicationRowV1
from authoring_funneling.a_typed_PSMCW_authoring.authoring import AuthoringError
from authoring_funneling.examples.crystal.publication import register_app_pack_v1
from authoring_funneling.examples.crystal.examples.typed_flow import CRYSTAL_FLOW_P
from authoring_funneling.examples.metal.publication import register_metal_standard
from authoring_funneling.examples.metal.examples.program1__typed_ports import HIGHER_P

PROFILE_ID = 'crystal.typed_ports.v1'


@pytest.fixture(autouse=True)
def register_trusted_runtime_contributions():
    register_app_pack_v1()
    register_metal_standard()


class GenericAuthoringClient:
    """Uses only the four common methods, with no pack-specific conditionals."""

    def __init__(self, profile):
        self.profile = profile
        self.descriptor = profile.describe()
        self.widgets = profile.describe_widgets()
        json.dumps(self.descriptor)
        json.dumps(self.widgets)

    def submit(self, draft):
        receipt = self.profile.validate(draft)
        if not receipt['ok']:
            return receipt, None
        return receipt, self.profile.compile(draft)


def crystal_draft():
    register_app_pack_v1()
    return {
        'profile_id': PROFILE_ID,
        'W': sorted({w['widget'] for w in CRYSTAL_FLOW_P['run']['program']['widgets'].values()}),
        'P': deepcopy(CRYSTAL_FLOW_P),
        'SM': {},
        'C': None,
    }


def metal_draft():
    register_metal_standard()
    return {
        'profile_id': 'metal_standard.typed_ports.v1',
        'W': sorted({w['widget'] for w in HIGHER_P['run']['program']['widgets'].values()}),
        'P': deepcopy(HIGHER_P),
        'SM': {},
        'C': None,
    }


def test_generic_client_common_interface_and_switch_revalidation():
    typed = GenericAuthoringClient(resolve_authoring_profile('crystal'))
    chrome = GenericAuthoringClient(resolve_authoring_profile('metal_standard'))
    draft = crystal_draft()
    assert typed.submit(draft)[0]['ok']
    assert typed.descriptor['refined_surfaces'] == ['W', 'P']
    assert typed.descriptor['passthrough_surfaces'] == ['SM', 'C']
    assert not chrome.submit(draft)[0]['ok']

    m_draft = metal_draft()
    receipt, export = chrome.submit(m_draft)
    assert receipt['ok']
    assert export['SM']['app_pack_mould']['app_pack'] == 'metal_standard'


def test_publication_requires_strict_profiles_and_packito_is_absent():
    with pytest.raises(TypeError):
        PackPublicationRowV1(lambda: None, None)
    with pytest.raises(AuthoringError, match='packito'):
        resolve_authoring_profile('packito')
    draft = crystal_draft()
    draft['W'] = ['unsupported.widget']
    receipt, _ = GenericAuthoringClient(resolve_authoring_profile('crystal')).submit(draft)
    assert receipt['errors'][0]['path'] == ['W']


def test_contract_fingerprint_stability_and_configuration_change():
    p = resolve_authoring_profile('crystal')
    draft = crystal_draft()
    assert p.compile(draft)['contract_fingerprint'] == p.compile(deepcopy(draft))['contract_fingerprint']
    draft['P']['run']['program']['widgets']['seed_1']['args']['title'] = 'New title'
    assert p.compile(draft)['contract_fingerprint'] == p.compile(crystal_draft())['contract_fingerprint']


@pytest.mark.parametrize('surface,value', [('W', [{}]), ('P', []), ('SM', None), ('C', [])])
def test_invalid_surface_receipts_identify_the_surface(surface, value):
    draft = crystal_draft()
    draft[surface] = value
    receipt = resolve_authoring_profile('crystal').validate(draft)
    assert receipt['ok'] is False
    assert receipt['errors'][0]['path'] == [surface]
    json.dumps(receipt, allow_nan=False)


def test_malformed_nested_program_returns_a_receipt():
    draft = crystal_draft()
    draft['P']['run']['program']['widgets'] = []
    receipt = resolve_authoring_profile('crystal').validate(draft)
    assert not receipt['ok']
    assert receipt['errors'][0]['path'] == ['P']
