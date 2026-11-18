from __future__ import annotations

"""Public package-static composition seam.

Higher installed packages should import their declaration vocabulary from
here, never from Flask/Django adapters and never from application globals.
"""

from .machinery import (
    THINKUMENT_STATIC_ROOT_ENTRYPOINT_GROUP,
    InvalidStaticAssetName,
    StaticAssetCollisionError,
    StaticAssetError,
    StaticNamespaceCollisionError,
    StaticRootSpec,
    django_get_static_paths,
    get_static_paths,
    get_static_root_specs,
    resolve_static_asset_path,
    static_asset_matches,
    validate_static_namespace,
    get_opinionation_module_filename
)


__all__ = [
    "THINKUMENT_STATIC_ROOT_ENTRYPOINT_GROUP",
    "InvalidStaticAssetName",
    "StaticAssetCollisionError",
    "StaticAssetError",
    "StaticNamespaceCollisionError",
    "StaticRootSpec",
    "django_get_static_paths",
    "get_static_paths",
    "get_static_root_specs",
    "resolve_static_asset_path",
    "static_asset_matches",
    "validate_static_namespace",
]
