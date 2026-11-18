"""Allowlisted runtime registration for curated public templates."""

_TRUSTED_RUNTIME_REGISTRARS = {
    'metal_typed_json_widget_v1': 'authoring_funneling.examples.metal.shared_widgets.registry:register_library_v1',
    'metal_micro_v1': 'authoring_funneling.examples.metal.shared_widgets.micros:register_microtables_v1',
    'metal_chromeset_family_v1': 'authoring_funneling.examples.metal.shared_widgets.registry:register_library_v1',
    'crystal_direct_pack_v1': 'authoring_funneling.examples.crystal.declare_pack:register_app_pack_v1',
}


def register_template_runtime_v1(template_id):
    """Install one known trusted family runtime; catalog content cannot name code."""
    reference = _TRUSTED_RUNTIME_REGISTRARS.get(template_id)
    if reference is None:
        raise KeyError(f'Template {template_id!r} has no trusted runtime contribution.')
    module_name, function_name = reference.split(':', 1)
    from importlib import import_module
    registrar = getattr(import_module(module_name), function_name)
    return registrar()
