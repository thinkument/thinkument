from __future__ import annotations

"""HAI static composition, including all installed app-pack browser roots."""

from pathlib import Path

from __staticfiles_mgmt import (
    THINKUMENT_STATIC_ROOT_ENTRYPOINT_GROUP,
    StaticRootSpec,
)

from ways_to_create.app_pack_mould.publication.catalog import load_app_pack_catalog_v1


# Only the shared HAI runtime lives here. Concrete app-pack browser trees are
# mounted from their manifests, including the bundled piles in src/app_packs_examples/.
STATIC_ROOT = Path(__file__).resolve().parent / "js"

STATIC_ROOT_SPEC = StaticRootSpec(
    name="package:think-app",
    path=STATIC_ROOT,
    logical_prefix="bootstrap_higher_app",
    opinionation_module="thinkumentJS_app_heartbeat.js",
)


def _is_inside_v1(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _app_pack_static_roots_v1() -> tuple[StaticRootSpec, ...]:
    roots: list[StaticRootSpec] = []
    for manifest in load_app_pack_catalog_v1().packs:
        # Defensive only: a future manifest physically inside the shared HAI root
        # is already reachable through STATIC_ROOT and must not be double-mounted.
        if _is_inside_v1(manifest.static_root, STATIC_ROOT):
            continue
        roots.append(
            StaticRootSpec(
                name=f"app-pack:{manifest.id}",
                path=manifest.static_root,
                logical_prefix=manifest.logical_prefix,
            )
        )
    return tuple(roots)


def thinkument_static_roots_v1() -> tuple[StaticRootSpec, ...]:
    """Return the shared HAI root plus every installed app-pack static root."""

    return (STATIC_ROOT_SPEC, *_app_pack_static_roots_v1())


__all__ = [
    "STATIC_ROOT",
    "STATIC_ROOT_SPEC",
    "THINKUMENT_STATIC_ROOT_ENTRYPOINT_GROUP",
    "thinkument_static_roots_v1",
]
