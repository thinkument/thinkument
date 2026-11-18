from __future__ import annotations

"""Public, data-only manifest contract for independently authored HAI packs.

Pack implementations can depend on think-app, think-backend, and
think-frontend. They do not need to import the framework-4-services integrator. Pack
installation is mediated by distribution entry points, never arbitrary JSON.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping


APP_PACK_MANIFEST_KIND = "app_pack_mould_app_pack_manifest_v1"
APP_PACK_ENTRYPOINT_GROUP = "thinkument.app_packs_examples.v1"
DEFAULT_APP_PACK_ID = "example_notes"
APP_PACK_COLLECTION_ENTRYPOINT_GROUP = "thinkument.app_pack_collections.v1"
_APP_PACK_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


def _nonempty_string(value: Any, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{path} must be a non-empty string")
    return value.strip()


def _normalize_static_root(value: Any) -> Path:
    try:
        path = Path(value).expanduser()
    except TypeError as exc:
        raise TypeError("manifest.static_root must be path-like") from exc
    if not path.is_absolute():
        raise ValueError("manifest.static_root must be absolute")
    return path.resolve()


def _normalize_registrar(value: Any) -> str | None:
    if value is None:
        return None
    ref = _nonempty_string(value, path="manifest.python_registrar")
    module, separator, attribute = ref.partition(":")
    if (
        not separator
        or not module
        or not attribute
        or not all(part.isidentifier() for part in module.split("."))
        or not all(part.isidentifier() for part in attribute.split("."))
    ):
        raise ValueError(
            "manifest.python_registrar must be 'python.module:attribute'"
        )
    return ref


@dataclass(frozen=True, slots=True)
class AppPackManifestV1:
    """One installed Python/browser pack, independent of its distribution.

    Files inside ``static_root`` are served under ``logical_prefix``. The
    browser must provide ``index.js``; it exports the existing HAI app-pack
    object. Optional Python registration is a zero-argument callable.
    """

    id: str
    label: str
    static_root: Path
    python_registrar: str | None = None
    kind: str = APP_PACK_MANIFEST_KIND

    def __post_init__(self) -> None:
        if self.kind != APP_PACK_MANIFEST_KIND:
            raise ValueError(f"unknown app-pack manifest kind {self.kind!r}")
        pack_id = _nonempty_string(self.id, path="manifest.id")
        if not _APP_PACK_ID_RE.fullmatch(pack_id):
            raise ValueError("manifest.id must match ^[a-z][a-z0-9_-]*$")
        object.__setattr__(self, "id", pack_id)
        object.__setattr__(
            self, "label", _nonempty_string(self.label, path="manifest.label")
        )
        object.__setattr__(self, "static_root", _normalize_static_root(self.static_root))
        object.__setattr__(
            self, "python_registrar", _normalize_registrar(self.python_registrar)
        )

    @property
    def logical_prefix(self) -> str:
        return f"bootstrap_higher_app/app_packs_examples/{self.id}"

    @property
    def js_module(self) -> str:
        return f"./app_packs_examples/{self.id}/index.js"

    @property
    def browser_module_path(self) -> Path:
        return self.static_root / "index.js"

    def assert_files_accessible(self) -> None:
        if not self.static_root.is_dir():
            raise FileNotFoundError(
                f"app-pack {self.id!r} static_root is not a directory: "
                f"{self.static_root}"
            )
        if not self.browser_module_path.is_file():
            raise FileNotFoundError(
                f"app-pack {self.id!r} browser module is missing: "
                f"{self.browser_module_path}"
            )


def coerce_app_pack_manifest_v1(value: Any) -> AppPackManifestV1:
    if isinstance(value, AppPackManifestV1):
        manifest = value
    elif isinstance(value, Mapping):
        source = dict(value)
        unknown = set(source) - {
            "kind", "id", "label", "static_root", "python_registrar"
        }
        if unknown:
            raise KeyError(f"app-pack manifest has unknown keys: {sorted(unknown)}")
        manifest = AppPackManifestV1(
            kind=source.get("kind", APP_PACK_MANIFEST_KIND),
            id=source.get("id"),
            label=source.get("label"),
            static_root=source.get("static_root"),
            python_registrar=source.get("python_registrar"),
        )
    else:
        raise TypeError(
            "app-pack entry point must expose AppPackManifestV1, a manifest "
            "mapping, or a zero-argument provider returning one"
        )
    manifest.assert_files_accessible()
    return manifest


__all__ = [
    "APP_PACK_ENTRYPOINT_GROUP",
    "APP_PACK_MANIFEST_KIND",
    "DEFAULT_APP_PACK_ID",
    "AppPackManifestV1",
    "coerce_app_pack_manifest_v1",
]


@dataclass(frozen=True, slots=True)
class AppPackCollectionV1:
    """A publication of packs with at most one explicit default selection."""

    manifests: tuple[AppPackManifestV1, ...]
    default_app_pack: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifests", tuple(
            coerce_app_pack_manifest_v1(row) for row in self.manifests
        ))
        if self.default_app_pack is not None:
            target = _nonempty_string(self.default_app_pack, path="collection.default_app_pack")
            if target not in {row.id for row in self.manifests}:
                raise ValueError(f"collection default target {target!r} is absent from its manifests")
            object.__setattr__(self, "default_app_pack", target)


def coerce_app_pack_collection_v1(value: Any) -> AppPackCollectionV1:
    if isinstance(value, AppPackCollectionV1):
        return AppPackCollectionV1(value.manifests, value.default_app_pack)
    if isinstance(value, Mapping):
        unknown = set(value) - {"manifests", "default_app_pack"}
        if unknown:
            raise KeyError(f"app-pack collection has unknown keys: {sorted(unknown)}")
        return AppPackCollectionV1(**value)
    raise TypeError("app-pack collection provider must return AppPackCollectionV1 or a mapping")


__all__ += ["APP_PACK_COLLECTION_ENTRYPOINT_GROUP", "AppPackCollectionV1", "coerce_app_pack_collection_v1", "PackPublicationRowV1"]


@dataclass(frozen=True)
class PackPublicationRowV1:
    """Common publication contract for direct and generated creative packs."""

    manifest_provider: object
    authoring_profile_provider: object

    def __post_init__(self) -> None:
        if not callable(self.manifest_provider) or not callable(self.authoring_profile_provider):
            raise TypeError("Publication requires manifest and strict profile providers.")

