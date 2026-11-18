from __future__ import annotations

"""Framework data contracts for UI authors. No host or service imports."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

UI_WEB_APP_COLLECTION_ENTRYPOINT_GROUP = "thinkument.ui_web_app_collections.v1"
_ID = re.compile(r"^[a-z][a-z0-9_-]*$")
_ROUTE = re.compile(r"^(?:[a-zA-Z0-9_-]+/)*$")


def _asset_name(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"invalid UI asset name {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError(f"UI asset name must be a relative file path: {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class WebappPageSpecV1:
    name: str
    route: str
    title: str
    template_name: str
    module_static_name: str
    service_contracts: tuple[str, ...] = ()
    uses_webcore: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _ID.fullmatch(self.name):
            raise ValueError(f"invalid webapp page name {self.name!r}")
        if not isinstance(self.route, str) or not _ROUTE.fullmatch(self.route):
            raise ValueError(f"webapp page route {self.route!r} must be a relative literal route with a trailing slash")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("webapp page title must be non-empty")
        _asset_name(self.template_name)
        _asset_name(self.module_static_name)
        if isinstance(self.service_contracts, str):
            raise TypeError("service_contracts must be a sequence of contract keys")
        keys = tuple(self.service_contracts)
        if any(not isinstance(key, str) or not key.strip() for key in keys):
            raise ValueError("service contract keys must be non-empty strings")
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate service contract keys")
        object.__setattr__(self, "service_contracts", keys)
        if not isinstance(self.uses_webcore, bool):
            raise TypeError("uses_webcore must be boolean")


def validate_webapp_page_specs_v1(specs: Iterable[WebappPageSpecV1]) -> None:
    names, routes = set(), set()
    for spec in specs:
        if not isinstance(spec, WebappPageSpecV1):
            raise TypeError("pages must be WebappPageSpecV1 declarations")
        if spec.name in names:
            raise ValueError(f"duplicate webapp page name: {spec.name!r}")
        if spec.route in routes:
            raise ValueError(f"duplicate webapp page route: {spec.route!r}")
        names.add(spec.name)
        routes.add(spec.route)


def build_webapp_pages_by_name_v1(specs: Iterable[WebappPageSpecV1]) -> Mapping[str, WebappPageSpecV1]:
    rows = tuple(specs)
    validate_webapp_page_specs_v1(rows)
    return MappingProxyType({spec.name: spec for spec in rows})


def get_webapp_page_spec_v1(pages_by_name: Mapping[str, WebappPageSpecV1], name: str) -> WebappPageSpecV1:
    try:
        return pages_by_name[str(name or "").strip()]
    except KeyError as exc:
        raise KeyError(f"unknown webapp page: {name!r}") from exc


@dataclass(frozen=True, slots=True)
class WebappManifestV1:
    id: str
    route_prefix: str
    url_namespace: str
    pages: tuple[WebappPageSpecV1, ...]
    template_root: Path
    static_root: Path

    def __post_init__(self) -> None:
        for key in ("id", "url_namespace"):
            if not isinstance(getattr(self, key), str) or not _ID.fullmatch(getattr(self, key)):
                raise ValueError(f"invalid webapp {key}: {getattr(self, key)!r}")
        if not isinstance(self.route_prefix, str) or not _ROUTE.fullmatch(self.route_prefix):
            raise ValueError("webapp route_prefix must be a relative literal route with a trailing slash")
        object.__setattr__(self, "pages", tuple(self.pages))
        if not self.pages:
            raise ValueError("webapp must declare at least one page")
        validate_webapp_page_specs_v1(self.pages)
        for key in ("template_root", "static_root"):
            path = Path(getattr(self, key))
            if not path.is_absolute():
                raise ValueError(f"webapp {key} must be absolute")
            object.__setattr__(self, key, path.resolve())

    def assert_files_accessible(self) -> None:
        for root in (self.template_root, self.static_root):
            if not root.is_dir():
                raise FileNotFoundError(f"webapp {self.id!r} asset root is missing: {root}")
        for page in self.pages:
            for root, name in ((self.template_root, page.template_name), (self.static_root, page.module_static_name)):
                asset = (root / name).resolve()
                if not asset.is_relative_to(root) or not asset.is_file():
                    raise FileNotFoundError(f"webapp {self.id!r} page {page.name!r} asset is missing or outside its root: {asset}")


def coerce_webapp_manifest_v1(value: Any) -> WebappManifestV1:
    if isinstance(value, WebappManifestV1):
        manifest = value
    elif isinstance(value, Mapping):
        data = dict(value)
        data["pages"] = tuple(WebappPageSpecV1(**page) if isinstance(page, Mapping) else page for page in data.get("pages", ()))
        manifest = WebappManifestV1(**data)
    else:
        raise TypeError("UI manifests must be WebappManifestV1 or mappings")
    manifest.assert_files_accessible()
    return manifest


@dataclass(frozen=True, slots=True)
class WebappCollectionV1:
    manifests: tuple[WebappManifestV1, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifests", tuple(coerce_webapp_manifest_v1(row) for row in self.manifests))


def coerce_webapp_collection_v1(value: Any) -> WebappCollectionV1:
    if isinstance(value, WebappCollectionV1):
        return WebappCollectionV1(value.manifests)
    if isinstance(value, Mapping):
        return WebappCollectionV1(**value)
    raise TypeError("UI collection provider must return WebappCollectionV1 or a mapping")
