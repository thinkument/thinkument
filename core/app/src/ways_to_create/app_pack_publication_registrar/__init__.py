"""
app_pack_publication_registrar
=============================
App pack publication, collection assembly, and static roots registration.
"""

from .contracts import PackPublicationRowV1

_MODULE_MAP = {
    "AppPackFamilyPublicationV1": ".app_pack_families",
    "SharedWidgetLibraryV1": ".app_pack_families",
    "register_app_pack_family_v1": ".app_pack_families",
    "RegisteredAppPackFamilyV1": ".app_pack_families",
    "app_pack_collection_v1": ".app_packs",
    "DEFAULT_APP_PACK_V1": ".app_packs",
    "APP_PACK_FAMILIES_V1": ".app_packs",
    "APP_PACK_PROVIDERS_V1": ".app_packs",
    "resolve_authoring_profile": ".authoring_profiles",
    "validate_publications": ".publication",
    "shared_static_roots_v1": ".static_roots",
}

def __getattr__(name: str):
    if name in _MODULE_MAP:
        from importlib import import_module
        mod = import_module(_MODULE_MAP[name], package=__package__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "PackPublicationRowV1",
    "AppPackFamilyPublicationV1",
    "SharedWidgetLibraryV1",
    "register_app_pack_family_v1",
    "RegisteredAppPackFamilyV1",
    "app_pack_collection_v1",
    "DEFAULT_APP_PACK_V1",
    "APP_PACK_FAMILIES_V1",
    "APP_PACK_PROVIDERS_V1",
    "resolve_authoring_profile",
    "validate_publications",
    "shared_static_roots_v1",
]
