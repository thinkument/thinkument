"""Validate and register Metal widget and micro metadata."""
from dataclasses import dataclass
from hashlib import sha256
import json
from threading import RLock
from .base import LibraryWidget
from .widgets import Seed, Consumer, Counter, Bounded, METAL_JSON_WIDGET_ARTIFACT_V1

@dataclass(frozen=True)
class WidgetRow:
    implementation: type[LibraryWidget]
    renderer: str


THINKWIDGETS = tuple(WidgetRow(cls, 'standardWidget') for cls in (Seed,Consumer,Counter,Bounded)) + (
    WidgetRow(METAL_JSON_WIDGET_ARTIFACT_V1, 'standardWidget'),
)
_REGISTRATION_LOCK = RLock()


def widget_rows():
    from authoring_funneling.a_typed_PSMCW_authoring.contracts import CONTRACT
    rows = {}
    for row in THINKWIDGETS:
        artifact = row.implementation
        cls = getattr(artifact, 'widget_class', artifact)
        if not issubclass(cls, LibraryWidget):
            raise TypeError('Library widgets must use strict templates and shell admission.')
        name = getattr(artifact, 'widget_id', None) or cls.__datum_widget_registered_name_v1__
        if name in rows:
            raise ValueError(f'Duplicate widget {name!r}.')
        if CONTRACT not in cls.get_class_static_decorated_config():
            raise ValueError(f'Widget {name!r} requires strict port metadata.')
        if cls.get_class_static_decorated_config()['args'].get('hai_renderer', {}).get('default') != name:
            raise ValueError(f'Widget {name!r} must use the library strict_widget decorator.')
        rows[name] = row
    return rows


def library_catalog_fingerprint_v1():
    """Stable fingerprint for the one shared Metal widget/micro catalogue."""
    from .micros import micro_catalogue, MICRO_TABLES
    rows = widget_rows()
    micros = micro_catalogue()
    payload = {
        'widgets': [{'id': name, 'renderer': row.renderer,
                     'contract': getattr(row.implementation, 'widget_class', row.implementation)
                                 .get_class_static_decorated_config().get('strict_ports_v1')}
                    for name, row in sorted(rows.items())],
        'micros': [{'name': name, 'renderer': row.renderer,
                    'schema': row.definition.json_schema,
                    'modality': row.definition.modality,
                    'owners': sorted(table.id for table in MICRO_TABLES
                                     if any(item.definition.name == name for item in table.rows))}
                   for name, row in sorted(micros.items())],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return sha256(encoded.encode('utf-8')).hexdigest()


def register_library_v1(pack_id='metal_standard'):
    from .micros import register_microtables_v1
    from ..shared_rendering.catalogue import validate_browser_catalogue_v1
    from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import (
        pull_thinkwidget_class_into_kernel_v1, kernel_widget_class_repr_v1,
    )
    from _thinkprogram._thinkcontinuitykernelTM.api import register_kernel_step_fn_v1,register_thinking_flow_explicit_language_v1
    from _thinkprogram.thinkprogramTM.api import register_think_program_language_v1
    with _REGISTRATION_LOCK:
        validate_browser_catalogue_v1()
        rows = widget_rows()
        from authoring_funneling import register_prepared_json_widget_v1
        register_prepared_json_widget_v1(METAL_JSON_WIDGET_ARTIFACT_V1)
        from ..shared_rendering.aesthetics import register_aesthetics_metadata_v1
        register_aesthetics_metadata_v1()
        micros = register_microtables_v1()
        # Decorators register on import; restore only when a host has cleared its registry.
        receipts = []
        for name, row in rows.items():
            cls = getattr(row.implementation, 'widget_class', row.implementation)
            try: existing = kernel_widget_class_repr_v1(name)
            except (ValueError, KeyError):
                receipts.append(pull_thinkwidget_class_into_kernel_v1(cls))
            else:
                expected = {'module':cls.__module__,'qualname':cls.__qualname__,'name':cls.__name__}
                if existing['class'] != expected:
                    raise ValueError(f'Widget {name!r} is registered differently.')
        register_kernel_step_fn_v1();register_thinking_flow_explicit_language_v1();register_think_program_language_v1()
        return {'kind':'app_pack_mould_app_pack_registration_receipt_v1','app_pack':pack_id,'ok':True,
                'widgets':list(rows),'micros':[micro.name for micro in micros],
                'runtime_registration':{'widgets':receipts}}

