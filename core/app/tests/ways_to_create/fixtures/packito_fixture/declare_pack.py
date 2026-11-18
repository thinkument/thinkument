from __future__ import annotations

"""Packito's declaration uses only the public think-app author contract."""

from pathlib import Path

from bootstrap_higher_app.app_pack_contract import AppPackManifestV1


_STATIC_ROOT = Path(__file__).with_name("js").resolve()


def app_pack_manifest_v1() -> AppPackManifestV1:
    return AppPackManifestV1(
        id="packito",
        label="Packito pedagogy",
        static_root=_STATIC_ROOT,
        python_registrar="packito_fixture.py.registration:register_app_pack_v1",
    )


__all__ = ["app_pack_manifest_v1"]
