from __future__ import annotations

"""Lightweight declaration for the bundled ``example_notes`` app pack."""

from pathlib import Path

from ways_to_create.app_pack_mould.publication.manifest import AppPackManifestV1


_STATIC_ROOT = Path(__file__).with_name("js").resolve()


def app_pack_manifest_v1() -> AppPackManifestV1:
    return AppPackManifestV1(
        id="example_notes",
        label="Example notes",
        static_root=_STATIC_ROOT,
        python_registrar=(
            "ways_to_create.app_packs_examples.example_notes.py.registration:register_app_pack_v1"
        ),
    )


__all__ = ["app_pack_manifest_v1"]
