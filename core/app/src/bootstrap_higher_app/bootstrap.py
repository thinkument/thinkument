from __future__ import annotations

"""Highest-package composition façade for Thinkument."""

from pathlib import Path
from typing import Any, Dict, TypeAlias


DjangoStaticfilesDir: TypeAlias = Path | tuple[str, Path]


def inspect_thinkument_frontend_assets_v1() -> Dict[str, Any]:
    """
    Validate and describe the complete installed frontend composition.
    """
    from __staticfiles_mgmt import (
        get_opinionation_module_filename,
        get_static_root_specs,
        validate_static_namespace,
    )

    validate_static_namespace()
    specs = tuple(get_static_root_specs())

    return {
        "kind": "thinkument_frontend_assets_v1",
        "static_roots": [
            {
                "name": spec.name,
                "path": str(spec.path.resolve()),
                "logical_prefix": spec.logical_prefix,
                "opinionation_module": spec.opinionation_module,
            }
            for spec in specs
        ],
        "opinionation_module": get_opinionation_module_filename(),
    }


def thinkument_opinionation_module_filename_v1() -> str | None:
    """Return the one logical static asset used as browser opinionation."""
    from __staticfiles_mgmt import (
        get_opinionation_module_filename,
        validate_static_namespace,
    )

    validate_static_namespace()
    return get_opinionation_module_filename()


def django_staticfiles_dirs_v1() -> tuple[DjangoStaticfilesDir, ...]:
    """
    Return Django's view of the same immutable aggregate static registry.
    """
    from __staticfiles_mgmt import (
        django_get_static_paths,
        validate_static_namespace,
    )

    validate_static_namespace()
    return tuple(django_get_static_paths())


def activate_bootstrap_higher_app_v1() -> Dict[str, Any]:
    assets = inspect_thinkument_frontend_assets_v1()
    return {
        "kind": "bootstrap_higher_app_activation_receipt_v1",
        "ok": True,
        "assets": assets,
    }


__all__ = [
    "DjangoStaticfilesDir",
    "activate_bootstrap_higher_app_v1",
    "django_staticfiles_dirs_v1",
    "inspect_thinkument_frontend_assets_v1",
    "thinkument_opinionation_module_filename_v1",
]
