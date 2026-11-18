from pathlib import Path
import pytest

import authoring_funneling_templates
from authoring_funneling_templates import (
    get_template_v1, list_templates_v1, register_template_runtime_v1, validate_template_v1,
)


def test_catalog_is_versioned_and_all_artifacts_are_packaged():
    templates = list_templates_v1()
    templates_root = Path(authoring_funneling_templates.__file__).resolve().parent
    assert any(row['id'] == 'metal_typed_json_widget_v1' for row in templates)
    for row in templates:
        assert row['version'] == 1
        for relative in row.get('artifacts', {}).values():
            assert (templates_root / relative).is_file()
    assert get_template_v1('metal_typed_json_widget_v1')['chromesets'][0]['app_pack_id'] == 'metal_standard'


def test_invalid_json_artifact_returns_pathful_error():
    result = validate_template_v1('metal_typed_json_widget_v1', {'widget': '{bad'})
    assert not result['ok']
    assert result['errors'][0]['artifact'] == 'widget'
    assert result['errors'][0]['code'] == 'invalid_json'


def test_integrated_example_compiles_and_validator_does_not_register_widgets():
    # Loading the host's trusted publication modules is normal service startup;
    # validation itself must not add or replace runtime definitions.
    import ways_to_create.app_pack_publication_registrar.app_packs  # noqa: F401
    from authoring_funneling.examples.metal.publication import register_metal_standard
    register_metal_standard()
    from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import list_kernel_widget_class_reprs_v1
    before = tuple(list_kernel_widget_class_reprs_v1())
    result = validate_template_v1('metal_typed_json_widget_v1')
    after = tuple(list_kernel_widget_class_reprs_v1())
    assert result['ok'], result['errors']
    assert result['lowered_surfaces']['program_language'] == 'think_program_v1'
    assert before == after


def test_catalog_returns_independent_values():
    changed = get_template_v1('metal_typed_json_widget_v1')
    changed['facets'].clear()
    assert get_template_v1('metal_typed_json_widget_v1')['facets']


def test_custom_operation_facet_registers_typed_versioned_function():
    import json
    from JSONfnchainTM import FlowCompilationError, execute_flow
    from authoring_funneling_templates.facets.custom_operation.custom_operation import create_vocab, prepare_example
    vocab = create_vocab()
    templates_root = Path(authoring_funneling_templates.__file__).resolve().parent
    manifest = json.loads((templates_root / 'facets/custom_operation/widget.json').read_text())
    prepared = prepare_example(manifest)
    plan = prepared.widget_class._compiled_transitions['mount']
    scope = {'mouth': {}, 'prior_outputs': {}, 'signal': {}, 'fills': {}, 'config': {}}
    assert execute_flow(plan, scope, vocab=vocab)['outputs']['result']['text'] == 'Ready.'
    assert json.loads(plan.to_json())['functions']['example.text.add_period']['version'] == '1'
    manifest['signals']['mount']['steps'][0]['fn'] = 'example.unknown'
    with pytest.raises(FlowCompilationError) as exc:
        prepare_example(manifest)
    assert exc.value.details['code'] == 'unknown_function'


def test_static_validator_reports_negative_surfaces_and_json_widget_overlay():
    import json
    templates_root = Path(authoring_funneling_templates.__file__).resolve().parent
    base = get_template_v1('metal_typed_json_widget_v1')
    root = templates_root
    widget = json.loads((root / base['artifacts']['widget']).read_text())
    program = json.loads((root / base['artifacts']['P']).read_text())

    result = validate_template_v1(base['id'], {'widget': {**widget, 'signals': {
        **widget['signals'], 'mount': {**widget['signals']['mount'], 'reexplode': {
            'title': 'Invalid', 'micros': [{'name': 'bad', 'type': 'not_admitted'}]}}}}})
    assert not result['ok'] and 'unadmitted_micro' in {row['code'] for row in result['errors']}

    wrong_id = json.loads(json.dumps(program))
    wrong_id['run']['program']['widgets']['idea']['widget'] = 'unreferenced.widget'
    result = validate_template_v1(base['id'], {'P': wrong_id})
    assert 'widget_not_referenced' in {row['code'] for row in result['errors']}

    result = validate_template_v1(base['id'], {'SM': []})
    assert result['errors'][0]['code'] == 'invalid_session_metadata'
    result = validate_template_v1(base['id'], {'C': []})
    assert result['errors'][0]['code'] == 'invalid_initial_overrides'

    result = validate_template_v1(base['id'], {'chromesets': {'chromesets': [
        {'app_pack_id': 'same', 'chrome_id': 'x'}, {'app_pack_id': 'same', 'chrome_id': 'x'}]}})
    assert 'invalid_chromeset_family' in {row['code'] for row in result['errors']}


def test_validator_lints_python_facets_and_unknown_templates_and_catalog_path_escape(monkeypatch):
    import pytest
    import authoring_funneling_templates.catalog as catalog
    result = validate_template_v1('internal_py_widget_v1', {'python': 'def broken(:\n pass'})
    assert not result['ok'] and result['errors'][0]['code'] == 'syntax_error'
    assert validate_template_v1('internal_py_widget_v1')['ok']
    assert validate_template_v1('metal_micro_v1')['ok']
    with pytest.raises(KeyError, match='Unknown public authoring template'):
        validate_template_v1('missing_template')
    original = catalog._catalog
    def escaped_catalog():
        value = original()
        next(row for row in value['templates'] if row['id'] == 'internal_py_widget_v1')['artifacts']['python'] = '../../outside.py'
        return value
    monkeypatch.setattr(catalog, '_catalog', escaped_catalog)
    with pytest.raises(ValueError, match='escapes template package'):
        catalog.template_artifacts_v1('internal_py_widget_v1')


def test_runtime_registration_is_explicit_and_allowlisted():
    result = register_template_runtime_v1('metal_micro_v1')
    assert 'creativity_bounded_integer' in {row.name for row in result}
    import pytest
    with pytest.raises(KeyError, match='no trusted runtime'):
        register_template_runtime_v1('untrusted_user_template')
