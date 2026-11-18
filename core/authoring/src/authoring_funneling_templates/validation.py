"""Static validation that reuses existing compilers without runtime registration."""
import ast
import json
from pathlib import Path

from .catalog import get_template_v1, template_artifacts_v1

_JSON_ARTIFACTS = {
    'P', 'SM', 'C', 'widget', 'system', 'roles', 'chainreaction_funk',
    'app_pack', 'paquete_aesthetics', 'chromesets', 'example',
}


def _decode(value, key):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f'{key} must contain valid JSON: {exc}') from exc
    return value


def validate_template_v1(template_id, authored_artifacts=None):
    """Validate a curated example or authored artifact overrides, without registration."""
    template = get_template_v1(template_id)
    artifacts = template_artifacts_v1(template_id, authored_artifacts)
    errors = []
    lowered = {}
    decoded = {}
    for key, value in artifacts.items():
        if key in {'python', 'definition', 'table'}:
            try:
                if not isinstance(value, str):
                    raise TypeError('Python facet must be source text.')
                ast.parse(value, filename=f'<{key}>')
            except (SyntaxError, TypeError, ValueError) as exc:
                errors.append({'artifact': key,
                               'path': [getattr(exc, 'lineno', None), getattr(exc, 'offset', None)],
                               'code': 'syntax_error', 'message': str(exc)})
        if key not in _JSON_ARTIFACTS:
            decoded[key] = value
            continue
        try:
            decoded[key] = _decode(value, key)
        except (ValueError, TypeError) as exc:
            errors.append({'artifact': key, 'path': [], 'code': 'invalid_json', 'message': str(exc)})
    if errors:
        return {'template_id': template_id, 'version': template['version'], 'ok': False,
                'errors': errors, 'lowered_surfaces': lowered}

    if 'SM' in decoded and type(decoded['SM']) is not dict:
        errors.append({'artifact': 'SM', 'path': [], 'code': 'invalid_session_metadata',
                       'message': 'SM must be a JSON object.'})
    if 'C' in decoded and decoded['C'] is not None and type(decoded['C']) is not dict:
        errors.append({'artifact': 'C', 'path': [], 'code': 'invalid_initial_overrides',
                       'message': 'C must be an object or null.'})
    if errors:
        return {'template_id': template_id, 'version': template['version'], 'ok': False,
                'errors': errors, 'lowered_surfaces': lowered}

    widget = decoded.get('widget')
    prepared = None
    if widget is not None:
        try:
            from authoring_funneling.b_typed_JSON_widget_declaration import (
                normalize_manifest_v1, prepare_json_widget_v1,
            )
            prepared = prepare_json_widget_v1(widget)
            lowered['widget'] = {'widget_id': prepared.widget_id, 'fingerprint': prepared.fingerprint}
            normalized = normalize_manifest_v1(widget)
            from authoring_funneling.examples.metal.shared_widgets.micros import validate_shell
            for signal, flow in normalized['signals'].items():
                shell = flow.get('returns', {}).get('reexplode')
                if shell is not None:
                    try:
                        validate_shell(shell)
                    except (ValueError, TypeError) as exc:
                        errors.append({'artifact': 'widget', 'path': ['signals', signal, 'reexplode'],
                                       'code': 'unadmitted_micro', 'message': str(exc)})
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            detail = getattr(exc, 'details', {})
            errors.append({'artifact': 'widget', 'path': detail.get('path', []),
                           'code': detail.get('code', 'invalid_widget'), 'message': str(exc)})

    program = decoded.get('P')
    if program is not None:
        try:
            program_widgets = program.get('run', {}).get('program', {}).get('widgets', {})
            referenced = {row.get('widget') for row in program_widgets.values() if isinstance(row, dict)}
            if prepared is not None and prepared.widget_id not in referenced:
                errors.append({'artifact': 'widget', 'path': ['name'], 'code': 'widget_not_referenced',
                               'message': 'The program must reference the JSON widget declared by this template.'})
            from authoring_funneling.a_typed_PSMCW_authoring.program import compile_strict_tape
            tape = compile_strict_tape(program, decoded.get('SM') or {}, decoded.get('C'),
                                       prepared_json_widgets=(prepared,) if prepared is not None else ())
            lowered['P'] = tape['P']
            lowered['widget_ids'] = tape['widget_ids']
            lowered['program_language'] = 'think_program_v1'
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            detail = getattr(exc, 'details', {})
            errors.append({'artifact': 'P', 'path': detail.get('path', []),
                           'code': detail.get('code', 'invalid_program'), 'message': str(exc)})

    chromesets = decoded.get('chromesets')
    if chromesets is not None:
        rows = chromesets.get('chromesets') if isinstance(chromesets, dict) else None
        ids = [row.get('app_pack_id') for row in rows or [] if isinstance(row, dict)]
        chrome_ids = [row.get('chrome_id') for row in rows or [] if isinstance(row, dict)]
        library = chromesets.get('shared_widget_library') if isinstance(chromesets, dict) else None
        if not rows or len(ids) != len(rows) or len(set(ids)) != len(ids) or \
                len(chrome_ids) != len(rows) or len(set(chrome_ids)) != len(chrome_ids) or \
                not isinstance(library, dict) or not library.get('library_id') or not library.get('catalog_fingerprint'):
            errors.append({'artifact': 'chromesets', 'path': [], 'code': 'invalid_chromeset_family',
                           'message': 'Require unique chrome and app-pack IDs referencing one shared library.'})
    micro_example = decoded.get('example')
    if micro_example is not None:
        try:
            from authoring_funneling.examples.metal.shared_widgets.micros import validate_shell
            validate_shell({'title': 'Micro example', 'micros': [micro_example]})
        except (ValueError, TypeError) as exc:
            errors.append({'artifact': 'example', 'path': [], 'code': 'unadmitted_micro', 'message': str(exc)})
    for key, relative in template.get('artifacts', {}).items():
        path = Path(__file__).parent / relative
        if not path.is_file():
            errors.append({'artifact': key, 'path': [relative], 'code': 'missing_asset',
                           'message': 'Catalog asset is missing.'})
    return {'template_id': template_id, 'version': template['version'], 'ok': not errors,
            'errors': errors, 'lowered_surfaces': lowered}
