from __future__ import annotations

"""Install-time HAI runtime composition, independent of host frameworks."""

from copy import deepcopy
from threading import RLock
from typing import Any, Mapping

from _thinksessions.sesh_metadata.__sesh_meta_dynamic_augmentation_by_apps import (
    SessionMetadataSurfaceRegistry,
)

from ways_to_create.app_pack_mould.publication.catalog import (
    load_app_pack_catalog_v1,
    resolve_registrar_v1,
)


APP_PACK_SESSION_METADATA_KEY = "app_pack_mould"
_ACTIVATION_LOCK = RLock()


def _pocket_schema_v1(app_pack_ids: tuple[str, ...]) -> dict[str, Any]:
    return {
        "kind": "session_metadata_pocket_schema_v1",
        "label": "Thinkument HAI presentation",
        "description": (
            "Selects an installed HAI app pack. Runtime behavior remains "
            "installed code; session metadata is inert JSON."
        ),
        "allow_none": False,
        "fields": {
            "app_pack": {
                "type": "string",
                "required": True,
                "enum": list(app_pack_ids),
            },
            "app_args": {
                "type": "object",
                "required": False,
                "additional_keys": True,
                "default": {},
            },
        },
        "additional_keys": False,
        "laws": [
            "app_pack must name an installed individual or collection manifest.",
            "app_args is inert dead JSON and never contains executable code.",
            "Browser assets are served from the selected manifest's static root.",
            "No HTML is transported through session state merely to render a widget.",
        ],
    }


def register_APP_PACK_SESSION_metadata_surface_v1() -> dict[str, Any]:
    catalog = load_app_pack_catalog_v1()
    schema = _pocket_schema_v1(catalog.ids)
    registered = SessionMetadataSurfaceRegistry.register_pocket(
        key=APP_PACK_SESSION_METADATA_KEY,
        schema=schema,
        replace=True,
    )
    return {
        "kind": "app_pack_mould_session_metadata_registration_receipt_v1",
        "key": APP_PACK_SESSION_METADATA_KEY,
        "default_app_pack": catalog.default_app_pack,
        "app_pack_ids": list(catalog.ids),
        "schema": registered,
    }


def _activate_manifest_v1(spec) -> dict[str, Any] | None:
    registrar = resolve_registrar_v1(spec)
    if registrar is None:
        return None

    receipt = registrar()
    if not isinstance(receipt, Mapping):
        raise TypeError(
            f"app-pack registrar {spec.python_registrar!r} must return a mapping receipt"
        )
    if receipt.get("app_pack") != spec.id:
        raise ValueError(
            f"app-pack registrar {spec.python_registrar!r} returned app_pack="
            f"{receipt.get('app_pack')!r}; expected {spec.id!r}"
        )
    # Older registrars may omit ok; preserve their existing receipt law.
    # An explicit unsuccessful result, however, must never be accepted.
    if "ok" in receipt and receipt["ok"] is not True:
        raise RuntimeError(
            f"app-pack registrar {spec.python_registrar!r} did not report "
            f"successful activation: {receipt!r}"
        )
    return deepcopy(dict(receipt))


def activate_app_pack_mould_v1() -> dict[str, Any]:
    """Register the metadata pocket and all installed Python-side packs.

    Runtime activation belongs to the process boot. Discovery itself remains
    safe during Django settings import. The higher app activates this function
    through the installed runtime-contributor entry point, so a service or
    worker never needs a list of pack names or paths.
    """

    with _ACTIVATION_LOCK:
        catalog = load_app_pack_catalog_v1()
        metadata = register_APP_PACK_SESSION_metadata_surface_v1()
        app_pack_receipts = [
            receipt
            for spec in catalog.packs
            if (receipt := _activate_manifest_v1(spec)) is not None
        ]
        return {
            "kind": "app_pack_mould_runtime_activation_receipt_v1",
            "metadata": metadata,
            "app_packs_examples": app_pack_receipts,
        }


def with_hai_app_pack_v1(
    session_metadata: Mapping[str, Any] | None,
    *,
    app_pack: str | None = None,
    app_args: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy SM and graft an installed HAI app-pack selection pocket."""

    catalog = load_app_pack_catalog_v1()
    selected = (
        catalog.default_app_pack
        if app_pack in (None, "")
        else str(app_pack).strip()
    )
    catalog.by_id(selected)
    if app_args is not None and not isinstance(app_args, Mapping):
        raise TypeError("app_args must be a mapping or None")
    out = deepcopy(dict(session_metadata or {}))
    out[APP_PACK_SESSION_METADATA_KEY] = {
        "app_pack": selected,
        "app_args": deepcopy(dict(app_args or {})),
    }
    return out


__all__ = [
    "APP_PACK_SESSION_METADATA_KEY",
    "activate_app_pack_mould_v1",
    "register_APP_PACK_SESSION_metadata_surface_v1",
    "with_hai_app_pack_v1",
    "browser_boot_config_v1",
]


def browser_boot_config_v1() -> dict[str, Any]:
    """Publish the discovered pack default to both Django and Flask shells."""
    return {"appPackDefault": load_app_pack_catalog_v1().default_app_pack}
