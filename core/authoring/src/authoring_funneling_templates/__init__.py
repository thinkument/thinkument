"""Copyable public authoring facets over the service-innovations funnels."""
from .catalog import get_template_v1, list_templates_v1
from .validation import validate_template_v1
from .runtime import register_template_runtime_v1
from authoring_funneling.b_typed_JSON_widget_declaration import (
    prepare_json_widget_v1, register_prepared_json_widget_v1,
)

__all__ = [
    'list_templates_v1', 'get_template_v1', 'validate_template_v1',
    'register_template_runtime_v1', 'prepare_json_widget_v1',
    'register_prepared_json_widget_v1',
]
