"""Versioned, package-local authoring template catalogue."""
from copy import deepcopy
import json
from pathlib import Path

_ROOT = Path(__file__).parent
_CATALOG_PATH = _ROOT / 'catalog.v1.json'


def _catalog():
    return json.loads(_CATALOG_PATH.read_text(encoding='utf-8'))


def list_templates_v1():
    """Return public template summaries without exposing mutable catalog state."""
    catalog = _catalog()
    return tuple(deepcopy(row) for row in catalog['templates'])


def get_template_v1(template_id):
    for row in _catalog()['templates']:
        if row['id'] == template_id:
            return deepcopy(row)
    raise KeyError(f'Unknown public authoring template {template_id!r}.')


def template_artifacts_v1(template_id, authored_artifacts=None):
    """Load default facet assets and overlay caller-owned draft artifacts."""
    template = get_template_v1(template_id)
    result = {}
    for key, relative in template.get('artifacts', {}).items():
        path = (_ROOT / relative).resolve()
        if _ROOT.resolve() not in path.parents:
            raise ValueError(f'Catalog artifact path escapes template package: {relative!r}.')
        result[key] = path.read_text(encoding='utf-8')
    for key, value in (authored_artifacts or {}).items():
        result[key] = deepcopy(value)
    return result
