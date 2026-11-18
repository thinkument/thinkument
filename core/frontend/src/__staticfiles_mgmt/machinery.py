from __future__ import annotations

"""Reusable machinery for resolving package-owned static assets."""

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import entry_points as _metadata_entry_points
from pathlib import Path, PurePosixPath


THINKUMENT_STATIC_ROOT_ENTRYPOINT_GROUP = "thinkument.static_roots.v1"


@dataclass(frozen=True)
class StaticRootSpec:
    name: str
    path: Path
    logical_prefix: str = ""
    opinionation_module: str | None = None


class StaticAssetError(RuntimeError):
    """Base error for package static-root configuration."""


class StaticAssetCollisionError(StaticAssetError):
    """Raised when one logical file has multiple physical owners."""


class StaticNamespaceCollisionError(StaticAssetError):
    """Raised when registered roots cannot form one unambiguous tree."""


class StaticOpinionationCollisionError(StaticAssetError):
    """Raised when more than one installed root claims app opinionation."""


class InvalidStaticAssetName(ValueError):
    """Raised when a logical static name is unsafe or malformed."""


IGNORED_STATIC_FILENAMES = frozenset({".DS_Store"})
OPINIONATION_MODULE_SUFFIXES = frozenset({".js", ".mjs"})


def _normalize_asset_name(filename: str) -> PurePosixPath:
    text = str(filename or "").strip()
    if not text:
        raise InvalidStaticAssetName("static asset name must not be empty")
    if "\\" in text:
        raise InvalidStaticAssetName(
            "static asset names must use forward slashes"
        )

    logical = PurePosixPath(text)
    if logical.is_absolute():
        raise InvalidStaticAssetName("static asset name must be relative")
    if any(part in {"", ".", ".."} for part in logical.parts):
        raise InvalidStaticAssetName(
            "static asset name may not traverse directories"
        )
    return logical


def _normalize_logical_prefix(value: str) -> str:
    text = str(value or "").strip().strip("/")
    if not text:
        return ""
    return _normalize_asset_name(text).as_posix()


def _normalize_static_root_spec(spec: StaticRootSpec) -> StaticRootSpec:
    name = str(spec.name or "").strip()
    if not name:
        raise StaticAssetError("static root spec name must not be empty")

    opinionation_module = spec.opinionation_module
    if opinionation_module is not None:
        opinionation_module = _normalize_asset_name(
            opinionation_module
        ).as_posix()

    return StaticRootSpec(
        name=name,
        path=Path(spec.path).resolve(),
        logical_prefix=_normalize_logical_prefix(spec.logical_prefix),
        opinionation_module=opinionation_module,
    )


def _selected_static_root_entry_points():
    discovered = _metadata_entry_points()

    if hasattr(discovered, "select"):
        rows = discovered.select(
            group=THINKUMENT_STATIC_ROOT_ENTRYPOINT_GROUP
        )
    else:
        rows = discovered.get(
            THINKUMENT_STATIC_ROOT_ENTRYPOINT_GROUP,
            (),
        )

    return tuple(
        sorted(
            rows,
            key=lambda entry_point: (
                str(
                    getattr(
                        getattr(entry_point, "dist", None),
                        "name",
                        "",
                    )
                ),
                str(entry_point.name),
                str(entry_point.value),
            ),
        )
    )


def _entry_point_label(entry_point) -> str:
    distribution = str(
        getattr(
            getattr(entry_point, "dist", None),
            "name",
            "",
        )
        or "<unknown-distribution>"
    )
    return f"{distribution}:{entry_point.name}"


@lru_cache(maxsize=1)
def _external_static_root_specs() -> tuple[StaticRootSpec, ...]:
    out: list[StaticRootSpec] = []

    for entry_point in _selected_static_root_entry_points():
        label = _entry_point_label(entry_point)

        try:
            provider = entry_point.load()
        except Exception as exc:
            raise StaticAssetError(
                f"could not load Thinkument static-root provider {label}"
            ) from exc

        if not callable(provider):
            raise StaticAssetError(
                f"Thinkument static-root entry point {label} "
                "must resolve to a callable"
            )

        try:
            provided = provider()
        except Exception as exc:
            raise StaticAssetError(
                f"Thinkument static-root provider {label} failed"
            ) from exc

        if isinstance(provided, StaticRootSpec):
            candidates = (provided,)
        elif isinstance(provided, (tuple, list)):
            candidates = tuple(provided)
        else:
            raise StaticAssetError(
                f"Thinkument static-root provider {label} must return "
                "StaticRootSpec or a tuple/list of StaticRootSpec"
            )

        if not candidates:
            raise StaticAssetError(
                f"Thinkument static-root provider {label} returned no roots"
            )

        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, StaticRootSpec):
                raise StaticAssetError(
                    f"Thinkument static-root provider {label}[{index}] "
                    "did not return StaticRootSpec"
                )

            normalized = _normalize_static_root_spec(candidate)

            if not normalized.logical_prefix:
                raise StaticNamespaceCollisionError(
                    "installed higher-package static roots must declare "
                    f"logical_prefix: provider={label!r}, "
                    f"root={normalized.name!r}"
                )

            out.append(normalized)

    return tuple(out)


def _base_static_root_specs() -> tuple[StaticRootSpec, ...]:
    from __staticfiles_mgmt.globals import STATIC_ROOT_SPECS

    return tuple(
        _normalize_static_root_spec(spec)
        for spec in STATIC_ROOT_SPECS
    )


def get_static_root_specs(
    *,
    require_exists: bool = True,
) -> tuple[StaticRootSpec, ...]:
    specs = (
        *_base_static_root_specs(),
        *_external_static_root_specs(),
    )

    names = [spec.name for spec in specs]
    if len(names) != len(set(names)):
        raise StaticNamespaceCollisionError(
            "the same static-root name is registered more than once: "
            f"{names}"
        )

    physical = [spec.path for spec in specs]
    if len(physical) != len(set(physical)):
        raise StaticNamespaceCollisionError(
            "the same physical static root is registered more than once: "
            f"{[str(path) for path in physical]}"
        )

    if require_exists:
        missing = [
            str(spec.path)
            for spec in specs
            if not spec.path.is_dir()
        ]

        if missing:
            raise StaticAssetError(
                f"configured static root(s) are missing: {missing}"
            )

    return tuple(specs)


def get_static_paths(
    *,
    require_exists: bool = True,
) -> tuple[Path, ...]:
    return tuple(
        spec.path
        for spec in get_static_root_specs(
            require_exists=require_exists
        )
    )


def django_get_static_paths() -> tuple[
    Path | tuple[str, Path],
    ...,
]:
    return tuple(
        (spec.logical_prefix, spec.path)
        if spec.logical_prefix
        else spec.path
        for spec in get_static_root_specs()
    )


def _logical_module_filename(
    spec: StaticRootSpec,
    relative: str | None,
) -> str | None:
    if relative is None:
        return None

    logical = PurePosixPath(relative)

    if spec.logical_prefix:
        logical = PurePosixPath(spec.logical_prefix) / logical

    return logical.as_posix()


def get_opinionation_module_filename() -> str | None:
    """
    Return the one installed default higher-app opinionation module.

    Static roots are additive; the installed default opinionation claim is a
    singleton. Multiple claims fail instead of acquiring precedence from
    package or import order. A concrete launch may explicitly select another
    registered JavaScript module without mutating this installed default.
    """
    claims: list[tuple[StaticRootSpec, str]] = []

    for spec in get_static_root_specs():
        logical = _logical_module_filename(
            spec,
            spec.opinionation_module,
        )

        if logical is None:
            continue

        if (
            PurePosixPath(logical).suffix.lower()
            not in OPINIONATION_MODULE_SUFFIXES
        ):
            raise StaticAssetError(
                "configured opinionation module must be a .js or .mjs asset: "
                f"name={spec.name!r}, logical={logical!r}"
            )

        physical = (
            spec.path
            / str(spec.opinionation_module)
        ).resolve()

        if not physical.is_file():
            raise StaticAssetError(
                "Configured opinionation module is missing.\n\n"
                f"Static root:\n"
                f"    {spec.name}\n\n"
                f"Physical root:\n"
                f"    {spec.path}\n\n"
                f"Logical/virtual prefix:\n"
                f"    {spec.logical_prefix or '<none>'}\n\n"
                f"Configured module relative to that physical root:\n"
                f"    {spec.opinionation_module}\n\n"
                f"Expected physical file:\n"
                f"    {physical}\n\n"
                f"Expected logical/virtual path:\n"
                f"    {logical}\n\n"
                "The static-root configuration says that files physically "
                "inside the root above are exposed through the logical "
                "namespace shown above. Check whether the physical file, "
                "physical root, logical_prefix, or configured module name "
                "is wrong."
            )

        claims.append((spec, logical))

    if len(claims) > 1:
        raise StaticOpinionationCollisionError(
            "more than one installed static root claims the active "
            "Thinkument opinionation: "
            f"{[(spec.name, logical) for spec, logical in claims]!r}"
        )

    return claims[0][1] if claims else None


def _relative_logical_for_spec(
    logical: PurePosixPath,
    spec: StaticRootSpec,
) -> PurePosixPath | None:
    if not spec.logical_prefix:
        return logical

    prefix = PurePosixPath(spec.logical_prefix)

    if logical == prefix:
        return None

    try:
        return logical.relative_to(prefix)
    except ValueError:
        return None


def _is_ignored_static_filename(filename: str) -> bool:
    return filename in IGNORED_STATIC_FILENAMES


def static_asset_matches(filename: str) -> tuple[Path, ...]:
    logical = _normalize_asset_name(filename)

    if _is_ignored_static_filename(logical.name):
        return ()

    matches: list[Path] = []

    for spec in get_static_root_specs():
        relative = _relative_logical_for_spec(
            logical,
            spec,
        )

        if relative is None:
            continue

        candidate = (
            spec.path
            / relative.as_posix()
        ).resolve()

        if (
            candidate != spec.path
            and spec.path not in candidate.parents
        ):
            raise InvalidStaticAssetName(
                "static asset resolved outside its configured root"
            )

        if (
            candidate.is_file()
            and not _is_ignored_static_filename(candidate.name)
        ):
            matches.append(candidate)

    return tuple(matches)


def _static_asset_not_found_message(
    filename: str,
) -> str:
    """
    Explain the physical-root -> logical-prefix mapping for a missing asset.

    Static callers use logical/virtual names, not arbitrary filesystem paths.
    The diagnostic shows both sides of that mapping so stale prefixes and
    incorrect relative paths are immediately visible.
    """
    requested = _normalize_asset_name(filename)
    specs = get_static_root_specs()

    lines = [
        "Static asset was not found in the registered virtual static namespace.",
        "",
        "Requested logical/virtual path:",
        f"    {requested.as_posix()}",
        "",
        "Static assets are not resolved from arbitrary filesystem paths.",
        "Each StaticRootSpec maps one physical directory into the aggregate",
        "logical/virtual static namespace.",
        "",
        "The mapping is:",
        "",
        "    physical root + relative file",
        "        ->",
        "    logical_prefix + relative file",
        "",
        "Registered static roots:",
    ]

    for spec in specs:
        virtual = (
            f"{spec.logical_prefix}/"
            if spec.logical_prefix
            else "<no prefix; files live at logical root>/"
        )

        lines.extend(
            [
                "",
                f"    {spec.name}",
                f"        physical root: {spec.path}",
                f"        virtual root:  {virtual}",
            ]
        )

        if spec.opinionation_module:
            logical_opinionation = _logical_module_filename(
                spec,
                spec.opinionation_module,
            )
            physical_opinionation = (
                spec.path
                / spec.opinionation_module
            ).resolve()

            lines.extend(
                [
                    "        configured opinionation physical file:",
                    f"            {physical_opinionation}",
                    "        configured opinionation logical path:",
                    f"            {logical_opinionation}",
                ]
            )

    requested_prefix = (
        requested.parts[0]
        if len(requested.parts) > 1
        else None
    )

    known_prefixes = {
        spec.logical_prefix
        for spec in specs
        if spec.logical_prefix
    }

    if (
        requested_prefix
        and requested_prefix not in known_prefixes
    ):
        lines.extend(
            [
                "",
                "The first segment of the requested logical path does not "
                "match any registered logical prefix:",
                f"    {requested_prefix}/",
                "",
                "Registered logical prefixes are:",
            ]
        )

        if known_prefixes:
            for prefix in sorted(known_prefixes):
                lines.append(f"    {prefix}/")
        else:
            lines.append("    <none>")

        lines.extend(
            [
                "",
                "If this asset belongs to a prefixed static root, this usually "
                "means the caller is using a stale or incorrect virtual prefix.",
            ]
        )

    basename_matches: list[
        tuple[StaticRootSpec, Path, str]
    ] = []

    for spec in specs:
        for physical in spec.path.rglob(requested.name):
            if not physical.is_file():
                continue
            if _is_ignored_static_filename(physical.name):
                continue

            relative = physical.relative_to(spec.path)

            logical = (
                PurePosixPath(spec.logical_prefix)
                / PurePosixPath(relative.as_posix())
                if spec.logical_prefix
                else PurePosixPath(relative.as_posix())
            )

            basename_matches.append(
                (
                    spec,
                    physical.resolve(),
                    logical.as_posix(),
                )
            )

    if basename_matches:
        lines.extend(
            [
                "",
                "A file with the same basename DOES exist in the registered "
                "static namespace:",
            ]
        )

        for spec, physical, logical in basename_matches:
            lines.extend(
                [
                    "",
                    f"    static root: {spec.name}",
                    f"    physical:    {physical}",
                    f"    logical:     {logical}",
                ]
            )

        lines.extend(
            [
                "",
                "If one of these is the asset you intended, use its logical "
                "path shown above. Do not use its filesystem path or an old "
                "virtual prefix.",
            ]
        )

    lines.extend(
        [
            "",
            "Check these four things:",
            "",
            "    1. Is the intended physical directory registered as a "
            "StaticRootSpec?",
            "    2. Is that StaticRootSpec.logical_prefix the virtual name "
            "you intend?",
            "    3. Is the caller using that logical/virtual prefix?",
            "    4. Does the remaining relative filename match the physical "
            "file under the registered root?",
        ]
    )

    return "\n".join(lines)


def resolve_static_asset_path(filename: str) -> Path:
    matches = static_asset_matches(filename)

    if not matches:
        raise FileNotFoundError(
            _static_asset_not_found_message(filename)
        )

    if len(matches) > 1:
        raise StaticAssetCollisionError(
            "logical static asset is defined by multiple roots: "
            f"name={filename!r}, "
            f"matches={[str(path) for path in matches]}"
        )

    return matches[0]


def validate_opinionation_module_filename(filename: str) -> str:
    """
    Validate one launch-selected logical browser module.

    The value is a logical name inside the already registered aggregate static
    namespace. This intentionally does not register a new directory and does
    not alter the installed default opinionation claim.
    """
    if not isinstance(filename, str):
        raise TypeError(
            "opinionation module filename must be a string"
        )

    logical = _normalize_asset_name(filename).as_posix()
    suffix = PurePosixPath(logical).suffix.lower()

    if suffix not in OPINIONATION_MODULE_SUFFIXES:
        raise InvalidStaticAssetName(
            "opinionation module must be a .js or .mjs static asset"
        )

    # Exact-one ownership and physical existence are part of launch validity.
    resolve_static_asset_path(logical)

    return logical


def select_opinionation_module_filename(
    *,
    explicit: str | None = None,
    use_installed_default: bool = True,
) -> str | None:
    """
    Select the browser opinionation for one concrete launch.

    ``explicit`` selects any registered JS module and wins over the installed
    default. When no explicit module is supplied, ``use_installed_default``
    decides whether the singleton package claim is used or opinionation is
    disabled for that launch.

    This is intentionally a pure selection operation. It never mutates static
    roots, importlib metadata caches, or process-global "current app" state, so
    independent tests/servers can choose different opinionations safely.
    """
    if explicit not in (None, ""):
        return validate_opinionation_module_filename(explicit)

    if not use_installed_default:
        return None

    return get_opinionation_module_filename()


def _logical_for_physical(
    spec: StaticRootSpec,
    physical: Path,
) -> PurePosixPath:
    relative = PurePosixPath(
        physical.relative_to(spec.path).as_posix()
    )

    return (
        PurePosixPath(spec.logical_prefix) / relative
        if spec.logical_prefix
        else relative
    )


def validate_static_namespace() -> None:
    selected = get_static_root_specs()

    # Validate the singleton claim and its physical file as part of the same
    # fail-fast composition boundary.
    get_opinionation_module_filename()

    file_owners: dict[
        PurePosixPath,
        list[Path],
    ] = defaultdict(list)

    directory_owners: dict[
        PurePosixPath,
        list[Path],
    ] = defaultdict(list)

    for spec in selected:
        if not spec.path.is_dir():
            raise StaticAssetError(
                f"configured static root is missing: {spec.path}"
            )

        for physical in spec.path.rglob("*"):
            if not physical.is_file():
                continue

            if _is_ignored_static_filename(physical.name):
                continue

            logical = _logical_for_physical(
                spec,
                physical,
            )

            relative = physical.relative_to(spec.path)
            if physical.suffix in {".py", ".pyc", ".pyo"} or "__pycache__" in relative.parts:
                raise StaticAssetError(
                    f"Python exposed in static root {spec.name!r}: "
                    f"root={spec.path}, source={physical}, logical={logical}"
                )

            file_owners[logical].append(
                physical.resolve()
            )

            for parent in logical.parents:
                if str(parent) == ".":
                    continue

                directory_owners[parent].append(
                    physical.resolve()
                )

    duplicate_files = {
        logical: owners
        for logical, owners in file_owners.items()
        if len(owners) > 1
    }

    if duplicate_files:
        details = {
            logical.as_posix(): [
                str(owner)
                for owner in owners
            ]
            for logical, owners in duplicate_files.items()
        }

        raise StaticNamespaceCollisionError(
            "aggregate static namespace contains logical files "
            f"with multiple physical owners: {details}"
        )

    file_directory_conflicts = {
        logical: {
            "file": [
                str(owner)
                for owner in file_owners[logical]
            ],
            "directory_required_by": [
                str(owner)
                for owner in directory_owners[logical]
            ],
        }
        for logical
        in (
            set(file_owners)
            & set(directory_owners)
        )
    }

    if file_directory_conflicts:
        raise StaticNamespaceCollisionError(
            "aggregate static namespace contains file/directory conflicts: "
            f"{file_directory_conflicts}"
        )


__all__ = [
    "IGNORED_STATIC_FILENAMES",
    "OPINIONATION_MODULE_SUFFIXES",
    "THINKUMENT_STATIC_ROOT_ENTRYPOINT_GROUP",
    "InvalidStaticAssetName",
    "StaticAssetCollisionError",
    "StaticAssetError",
    "StaticNamespaceCollisionError",
    "StaticOpinionationCollisionError",
    "StaticRootSpec",
    "django_get_static_paths",
    "get_opinionation_module_filename",
    "get_static_paths",
    "get_static_root_specs",
    "resolve_static_asset_path",
    "select_opinionation_module_filename",
    "static_asset_matches",
    "validate_opinionation_module_filename",
    "validate_static_namespace",
]
