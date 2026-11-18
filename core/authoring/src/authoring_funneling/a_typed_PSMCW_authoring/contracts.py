"""Typed metadata lives on ordinary registered class representations."""
from copy import deepcopy
from types import MappingProxyType
from bindings2bindingsTM import normalize, CompilationError
from _thinkprogram.thinkwidgetTM.decorators import thinkwidgetTM_config
from _thinkprogram.thinkwidgetTM.constants import CONFIG_KEY
from _thinkprogram.thinkprogramTM.__integrate_thinkkernel_pulls_thinkwidgets import pull_thinkwidget_class_into_kernel_v1, kernel_widget_class_repr_v1, list_kernel_widget_class_reprs_v1

RECIPE = 'strict_binding_recipe_v1'
PARAMETERS = 'strict_binding_parameters_v1'
SOURCES = 'strict_sources_v1'
CONTRACT = 'strict_ports_v1'

def prepare_strict_widget(name, *, args=None, inputs=None, outputs=None, **config):
    """Prepare strict metadata on a class without publishing it to registries."""
    if config.get('enforce_no_premount_shell',True) is not True: raise CompilationError('requires_mount_shelling',('W',name))
    config['enforce_no_premount_shell']=True
    args=deepcopy(args or {})
    if {RECIPE,PARAMETERS} & args.keys() or 'wires' in config or CONTRACT in config:
        raise CompilationError('reserved_contract_field',('W',name))
    schemas={group:{k:normalize(v) for k,v in (values or {}).items()} for group,values in [('inputs',inputs),('outputs',outputs)]}
    ports={group:{k:v.to_json() for k,v in values.items()} for group,values in schemas.items()}
    if not all(type(k) is str and k for group in ports.values() for k in group): raise CompilationError('invalid_port_name',('W',name))
    if any(t['kind'] not in ('dict', 'promise') or (t['kind'] == 'promise' and t.get('item', {}).get('kind') != 'dict') for t in ports['outputs'].values()):
        raise CompilationError('output_requires_closed_record',('W',name,'outputs'))
    args.update({RECIPE:{'type':'str','required':True},PARAMETERS:{'type':'dict','required':False,'default':{}}})
    def decorate(cls):
        from .widget import StrictServiceWidget
        if not issubclass(cls,StrictServiceWidget): raise CompilationError('requires_strict_widget',('W',name))
        for base in cls.__mro__:
            for fn in vars(base).values():
                if getattr(fn,'__datum_widget_signal_catcher_v1__',None) and not getattr(fn,'__analytica_wrapped__',False):
                    raise CompilationError('requires_analytica_signal_catcher',('W',name))
        cls._strict_schemas_v1=MappingProxyType({group:MappingProxyType(values) for group,values in schemas.items()})
        static_config = {'wires':{SOURCES:{'multiplicity':'many','required':False}},
                         'strict_ports_v1':ports, **config}
        cls._strict_registration_v1 = {
            'name': name,
            'args': args,
            'config': static_config,
        }
        setattr(cls, CONFIG_KEY, {'args': args, **static_config})
        return cls
    return decorate


def register_prepared_strict_widget_v1(cls, *, overwrite=False):
    """Install a class produced by prepare_strict_widget in the two registries."""
    registration = getattr(cls, '_strict_registration_v1', None)
    if not isinstance(registration, dict):
        raise TypeError('Class was not prepared by prepare_strict_widget().')
    name = registration['name']
    if overwrite:
        if cls.__dict__.get('__datum_widget_compiled_fn_v1__') is None:
            cls = thinkwidgetTM_config(name, overwrite=True,
                                       args=registration['args'], **registration['config'])(cls)
        return pull_thinkwidget_class_into_kernel_v1(cls, overwrite=True)
    from _thinkprogram._thinkcontinuitykernelTM._contracts import kernel_widget_contract_v1
    try:
        kernel_widget_contract_v1(name)
    except ValueError:
        if cls.__dict__.get('__datum_widget_compiled_fn_v1__') is None:
            cls = thinkwidgetTM_config(name, overwrite=overwrite,
                                       args=registration['args'], **registration['config'])(cls)
        return pull_thinkwidget_class_into_kernel_v1(cls, overwrite=overwrite or cls.__dict__.get(
            '__datum_widget_compiled_fn_v1__') is not None)
    existing = kernel_widget_class_repr_v1(name)
    expected = {'module': cls.__module__, 'qualname': cls.__qualname__, 'name': cls.__name__}
    if existing.get('class') != expected:
        raise ValueError(f'Strict widget ID {name!r} is already registered to a different class.')
    return existing


def strict_widget(name, *, args=None, inputs=None, outputs=None, overwrite=False, **config):
    """Declare strict ports and immediately publish the trusted Python class."""
    prepared = prepare_strict_widget(name, args=args, inputs=inputs, outputs=outputs, **config)
    def decorate(cls):
        cls = prepared(cls)
        register_prepared_strict_widget_v1(cls, overwrite=overwrite)
        return cls
    return decorate

def _prepared_json_contracts(artifacts):
    """Build a call-local contract overlay from genuine preparation artifacts."""
    from ..b_typed_JSON_widget_declaration.factory import (
        PreparedJsonWidgetV1, _PREPARED_ARTIFACT_PROOF,
    )
    result = {}
    for artifact in artifacts:
        if type(artifact) is not PreparedJsonWidgetV1 or artifact._proof is not _PREPARED_ARTIFACT_PROOF:
            raise TypeError('Contract overlays require genuine PreparedJsonWidgetV1 artifacts.')
        cls = artifact.widget_class
        registration = getattr(cls, '_strict_registration_v1', None)
        if (not isinstance(cls, type) or registration is None or
                registration.get('name') != artifact.widget_id or
                not issubclass(cls, __import__(
                    'authoring_funneling.b_typed_JSON_widget_declaration.widget',
                    fromlist=['JsonDefinedLibraryWidget']).JsonDefinedLibraryWidget)):
            raise TypeError('Prepared JSON widget contract does not match its artifact.')
        result[artifact.widget_id] = {
            'ports': deepcopy(registration['config'][CONTRACT]),
            'configuration': {k: v for k, v in registration['args'].items() if k not in (RECIPE, PARAMETERS)},
            'implementation': {'module': cls.__module__, 'qualname': cls.__qualname__, 'name': cls.__name__},
        }
    return result


def widget_contract(widget_id, *, prepared_json_widgets=()):
    overlay = _prepared_json_contracts(prepared_json_widgets)
    if widget_id in overlay:
        return deepcopy(overlay[widget_id]['ports'])
    try: metadata=kernel_widget_class_repr_v1(widget_id)
    except (ValueError,TypeError) as exc: raise CompilationError('unsupported_widget',('W',widget_id)) from exc
    ports=metadata['adapter_config'].get(CONTRACT)
    if ports is None: raise CompilationError('unsupported_widget',('W',widget_id))
    return deepcopy(ports)

def widget_catalogue(widget_ids=None, *, prepared_json_widgets=()):
    names=widget_ids if widget_ids is not None else list_kernel_widget_class_reprs_v1()
    overlay = _prepared_json_contracts(prepared_json_widgets)
    result=[]
    for name in names:
        if name in overlay:
            result.append({'widget_id': name, **deepcopy(overlay[name])})
            continue
        meta=kernel_widget_class_repr_v1(name)
        if CONTRACT in meta['adapter_config']:
            result.append({'widget_id':name,'ports':widget_contract(name),'configuration':{k:v for k,v in meta['adapter_config']['args'].items() if k not in (RECIPE,PARAMETERS)},'implementation':meta['class']})
    return result
