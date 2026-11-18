"""Pure preparation and explicit publication of generated strict classes."""
from dataclasses import dataclass, field
from hashlib import sha256
import json
from threading import RLock
from types import MappingProxyType
from bindings2bindingsTM import Dict, Map, Str, compatible
from JSONfnchainTM import compile_flow
from ..a_typed_PSMCW_authoring import analytica_signal_catcher
from ..a_typed_PSMCW_authoring.contracts import (
    prepare_strict_widget, register_prepared_strict_widget_v1,
)
from .manifest import normalize_manifest_v1, normalize_port_schema_v1, fail
from .widget import JsonDefinedLibraryWidget
from .interceptor import VendorBinding
from .vocab_hub import THINKUMENT_GLOBAL_VOCAB


@dataclass(frozen=True)
class PreparedJsonWidgetV1:
    """An immutable source/fingerprint pair plus its locally compiled class."""
    widget_id: str
    fingerprint: str
    manifest_json: str
    widget_class: type
    _proof: object = field(repr=False, compare=False)


_REGISTRATION_LOCK = RLock()
_REGISTERED_JSON_WIDGETS = {}
_PREPARED_ARTIFACT_PROOF = object()


def prepare_json_widget_v1(manifest, *, widget_id=None, publisher_user_id=None, vocab=None, vendor_bindings=None, base=JsonDefinedLibraryWidget):
    """Validate and compile a manifest without changing kernel registries.

    ``widget_id`` optionally binds the immutable source definition to a
    version-qualified runtime identity. The fingerprint remains over the
    canonical source manifest, while the prepared class is registered under
    the supplied identity. Omitting it preserves the historical manifest-name
    identity.
    """
    if not isinstance(base, type) or not issubclass(base, JsonDefinedLibraryWidget):
        fail('base must inherit JsonDefinedLibraryWidget')
    if vendor_bindings is not None and (type(vendor_bindings) is not dict or any(not isinstance(binding, VendorBinding) for binding in vendor_bindings.values())):
        fail('vendor_bindings must map approved names to VendorBinding instances')
    manifest = normalize_manifest_v1(manifest)
    runtime_widget_id = manifest['name'] if widget_id is None else widget_id
    if type(runtime_widget_id) is not str or not runtime_widget_id.strip():
        fail('widget_id must be a non-empty string')
    declaration = manifest['declaration']
    vocab = vocab if vocab is not None else THINKUMENT_GLOBAL_VOCAB
    schemas = {group: {k: normalize_port_schema_v1(v) for k,v in declaration[group].items()}
               for group in ('inputs','outputs')}
    config = {}
    for key, spec in declaration['args'].items():
        if type(spec) is not dict or 'type' not in spec: fail('Arguments require type declarations')
        config[key] = normalize_port_schema_v1(spec['type'])
    sources = {'mouth': Dict(schemas['inputs']), 'prior_outputs': Dict(schemas['outputs']),
               'config': Dict(config), 'fills': normalize_port_schema_v1(declaration.get('fills', {'type':'map','key':'str','value':'str'})),
               'signal': normalize_port_schema_v1(declaration.get('signal', {'type':'map','key':'str','value':'str'}))}
    plans = {}
    async_transitions = {}
    for name, flow in manifest['signals'].items():
        scope = {**sources, **({'prior_outputs': Dict({})} if name == 'mount' else {})}
        flow_def = {'steps': flow.get('steps', []), 'returns': flow.get('returns', {})}
        plan = compile_flow(flow_def, scope, None, vocab)
        target = plan.target_type
        if target.kind != 'dict' or set(target._field_map) - {'done','reexplode','outputs','keep'}:
            fail('Signal must return an outcome record', ('signals', name))
        fields = target._field_map
        if ('done' in fields) == ('reexplode' in fields): fail('Choose done or reexplode', ('signals', name))
        if 'done' in fields and fields['done'].kind != 'bool':
            fail('done must be boolean')
        if 'reexplode' in fields:
            shell = fields['reexplode']
            if shell.kind != 'dict' or not {'title','micros'} <= shell._field_map.keys():
                fail('reexplode requires title and micros')
            if shell.field_type('title').kind != 'str' or shell.field_type('micros').kind != 'list':
                fail('reexplode requires string title and micros array')
        if 'outputs' in fields:
            if fields['outputs'].kind != 'dict': fail('outputs must be a record')
            for port, schema in fields['outputs'].fields:
                if port not in schemas['outputs']:
                    fail('Output contract mismatch', ('signals', name, 'outputs', port))
                expected = schemas['outputs'][port]
                target_expected = expected.item if getattr(expected, 'kind', None) == 'promise' else expected
                if not compatible(schema, expected) and not compatible(schema, target_expected):
                    fail('Output contract mismatch', ('signals', name, 'outputs', port))
        plans[name] = plan

        has_async_ops = any(fn.startswith(('vendor.', 'asyncwork.', 'async.')) for fn in plan._contracts.keys())
        mode = flow.get('execution', 'auto')
        if mode == 'sync':
            is_async = False
        elif mode == 'async':
            is_async = True
        else:
            is_async = has_async_ops
        async_transitions[name] = is_async

    attrs = {'__module__': __name__, '_compiled_transitions': MappingProxyType(plans),
             '_async_transitions': MappingProxyType(async_transitions),
             '_vocab': vocab, '_vendor_bindings': MappingProxyType(dict(vendor_bindings or {}))}
    if publisher_user_id is not None:
        if type(publisher_user_id) not in (str, int) or not str(publisher_user_id).strip():
            fail('publisher_user_id must be a non-empty stable identifier')
        attrs['_published_widget_version_id_v1'] = runtime_widget_id
        attrs['_published_widget_publisher_user_id_v1'] = str(publisher_user_id)
    def mount(self, position, fill_data, limits, stats): return self._execute_transition('mount', fill_data, {})
    def fill(self, signal, position, fill_data, limits, stats): return self._execute_transition('fill', fill_data, signal)
    attrs.update(_on_mount=mount, _on_fill=fill)
    def handler(name):
        def receive(self, signal, position, fill_data, limits, stats):
            return self._execute_transition(name, fill_data, signal)
        return analytica_signal_catcher(name)(receive)
    for name in plans.keys() - {'mount','fill'}: attrs['json_signal_' + name] = handler(name)
    manifest_json = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    fingerprint = sha256(('json_widget_v1\0' + manifest_json).encode('utf-8')).hexdigest()
    cls = type(manifest['name'].replace('.', '_'), (base,), attrs)
    cls = prepare_strict_widget(runtime_widget_id, args=declaration['args'], inputs=schemas['inputs'],
                                outputs=schemas['outputs'])(cls)
    return PreparedJsonWidgetV1(runtime_widget_id, fingerprint, manifest_json, cls, _PREPARED_ARTIFACT_PROOF)


def register_prepared_json_widget_v1(artifact):
    """Publish one prepared immutable widget ID into this process's kernel."""
    if not isinstance(artifact, PreparedJsonWidgetV1):
        raise TypeError('Expected a PreparedJsonWidgetV1 artifact.')
    if artifact._proof is not _PREPARED_ARTIFACT_PROOF:
        raise ValueError('Prepared widget artifacts must come from prepare_json_widget_v1().')
    if not issubclass(artifact.widget_class, JsonDefinedLibraryWidget):
        raise TypeError('Prepared widget class must inherit JsonDefinedLibraryWidget.')
    with _REGISTRATION_LOCK:
        prior = _REGISTERED_JSON_WIDGETS.get(artifact.widget_id)
        if prior is not None:
            if prior.fingerprint != artifact.fingerprint:
                raise ValueError(f'JSON widget {artifact.widget_id!r} is already registered with different content.')
            for attr in (
                '_published_widget_version_id_v1',
                '_published_widget_publisher_user_id_v1',
            ):
                incoming = getattr(artifact.widget_class, attr, None)
                existing_value = getattr(prior.widget_class, attr, None)
                if existing_value not in (None, incoming) and incoming is not None:
                    raise ValueError(f'JSON widget {artifact.widget_id!r} has conflicting publication attribution.')
                if incoming is not None:
                    setattr(prior.widget_class, attr, incoming)
        from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import kernel_widget_class_repr_v1
        from _thinkprogram._thinkcontinuitykernelTM._contracts import kernel_widget_contract_v1
        try:
            kernel_widget_contract_v1(artifact.widget_id)
        except (ValueError, KeyError, TypeError):
            register_prepared_strict_widget_v1(prior.widget_class if prior is not None else artifact.widget_class)
        else:
            registered_class = prior.widget_class if prior is not None else artifact.widget_class
            existing = kernel_widget_class_repr_v1(artifact.widget_id)
            expected = {'module': registered_class.__module__,
                        'qualname': registered_class.__qualname__,
                        'name': registered_class.__name__}
            if existing.get('class') != expected:
                raise ValueError(f'Kernel widget ID {artifact.widget_id!r} is already registered differently.')
        if prior is None:
            _REGISTERED_JSON_WIDGETS[artifact.widget_id] = artifact
            return artifact.widget_class
        return prior.widget_class
