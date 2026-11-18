from __future__ import annotations

"""Discover installed individual manifests and collections, independent of authors."""

from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from importlib.metadata import entry_points
from inspect import signature
from typing import Any, Callable

from bootstrap_higher_app.app_pack_contract import (
    APP_PACK_COLLECTION_ENTRYPOINT_GROUP,
    coerce_app_pack_collection_v1,
    APP_PACK_ENTRYPOINT_GROUP,
    DEFAULT_APP_PACK_ID,
    AppPackManifestV1,
    coerce_app_pack_manifest_v1,
)


CATALOG_KIND = "app_pack_mould_app_pack_catalog_v1"
AppPackSpecV1 = AppPackManifestV1


@dataclass(frozen=True, slots=True)
class AppPackCatalogV1:
    default_app_pack: str
    packs: tuple[AppPackManifestV1, ...]
    kind: str = CATALOG_KIND

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(row.id for row in self.packs)

    def by_id(self, app_pack_id: str) -> AppPackManifestV1:
        normalized = str(app_pack_id or "").strip()
        for row in self.packs:
            if row.id == normalized:
                return row
        raise KeyError(f"unknown installed HAI app pack {normalized!r}")


def resolve_object_ref_v1(ref: str) -> Any:
    module_name, separator, attr_path = str(ref or "").strip().partition(":")
    if not separator or not module_name or not attr_path:
        raise ValueError("object reference must be 'python.module:attribute'")
    value: Any = import_module(module_name)
    for part in attr_path.split("."):
        if not part or not part.isidentifier():
            raise ValueError(f"invalid attribute in object ref {ref!r}")
        value = getattr(value, part)
    return value


def _provider_value_v1(value: Any) -> Any:
    return value() if callable(value) else value


def _entry_points_for_group_v1(group: str):
    discovered = entry_points()
    if hasattr(discovered, "select"):
        return tuple(discovered.select(group=group))
    return tuple(discovered.get(group, ()))  # pragma: no cover


def _installed_entry_points_v1():
    return _entry_points_for_group_v1(APP_PACK_ENTRYPOINT_GROUP)


def _provider_source_v1(ep) -> str:
    distribution = getattr(getattr(ep, "dist", None), "name", None)
    return f"{distribution or 'unknown distribution'}:{ep.name} -> {ep.value}"


@lru_cache(maxsize=1)
def load_app_pack_catalog_v1() -> AppPackCatalogV1:
    manifests: dict[str, AppPackManifestV1] = {}
    sources: dict[str, str] = {}
    defaults: list[tuple[str, str]] = []

    def insert(manifest: AppPackManifestV1, source: str) -> None:
        if manifest.id in manifests:
            raise ValueError(
                f"duplicate installed HAI app-pack id {manifest.id!r}; "
                f"providers: {sources[manifest.id]} and {source}"
            )
        try:
            manifest.assert_files_accessible()
            resolve_registrar_v1(manifest)
        except Exception as exc:
            raise ValueError(f"invalid app pack {manifest.id!r} from provider {source}: {exc}") from exc
        manifests[manifest.id] = manifest
        sources[manifest.id] = source

    for ep in sorted(_installed_entry_points_v1(), key=lambda item: (item.name, item.value)):
        source = _provider_source_v1(ep)
        try:
            manifest = coerce_app_pack_manifest_v1(_provider_value_v1(ep.load()))
            if ep.name != manifest.id:
                raise ValueError(f"entry-point name {ep.name!r} must equal manifest id {manifest.id!r}")
        except Exception as exc:
            raise ValueError(f"could not load HAI app-pack provider {source}: {exc}") from exc
        insert(manifest, source)

    for ep in sorted(_entry_points_for_group_v1(APP_PACK_COLLECTION_ENTRYPOINT_GROUP), key=lambda item: (item.name, item.value)):
        source = _provider_source_v1(ep)
        try:
            collection = coerce_app_pack_collection_v1(_provider_value_v1(ep.load()))
        except Exception as exc:
            raise ValueError(f"could not load HAI app-pack collection provider {source}: {exc}") from exc
        for manifest in collection.manifests:
            insert(manifest, source)
        if collection.default_app_pack is not None:
            defaults.append((collection.default_app_pack, source))

    if len(defaults) > 1:
        raise ValueError(f"multiple explicit app-pack defaults declared by providers: {defaults!r}")
    selected = defaults[0][0] if defaults else DEFAULT_APP_PACK_ID
    if selected not in manifests:
        raise ValueError(f"default HAI app pack {selected!r} is not installed; providers: {list(sources.values())!r}")
    return AppPackCatalogV1(default_app_pack=selected, packs=tuple(manifests[key] for key in sorted(manifests)))


def reset_app_pack_catalog_cache_v1() -> None:
    load_app_pack_catalog_v1.cache_clear()


def resolve_registrar_v1(
    spec: AppPackManifestV1,
) -> Callable[[], Any] | None:
    if spec.python_registrar is None:
        return None
    value = resolve_object_ref_v1(spec.python_registrar)
    if not callable(value):
        raise TypeError(
            f"app-pack registrar {spec.python_registrar!r} is not callable"
        )
    try:
        signature(value).bind()
    except TypeError as exc:
        raise TypeError(f"app-pack registrar {spec.python_registrar!r} must accept zero arguments") from exc
    return value


def validate_installed_app_pack_manifests_v1() -> dict[str, Any]:
    """Check manifests and registrar references without executing registrars."""

    catalog = load_app_pack_catalog_v1()
    rows: list[dict[str, Any]] = []
    for manifest in catalog.packs:
        registrar = resolve_registrar_v1(manifest)
        rows.append({
            "id": manifest.id,
            "label": manifest.label,
            "logical_module": manifest.js_module,
            "browser_module_path": str(manifest.browser_module_path),
            "python_registrar": manifest.python_registrar,
            "registrar_resolved": registrar is not None,
        })

    return {
        "kind": "app_pack_mould_manifest_health_receipt_v1",
        "ok": True,
        "entry_point_group": APP_PACK_ENTRYPOINT_GROUP,
        "default_app_pack": catalog.default_app_pack,
        "app_packs_examples": rows,
    }


__all__ = [
    "APP_PACK_ENTRYPOINT_GROUP",
    "AppPackCatalogV1",
    "AppPackManifestV1",
    "AppPackSpecV1",
    "CATALOG_KIND",
    "load_app_pack_catalog_v1",
    "reset_app_pack_catalog_cache_v1",
    "resolve_object_ref_v1",
    "resolve_registrar_v1",
    "validate_installed_app_pack_manifests_v1",
]
