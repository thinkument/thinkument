"""One ordinary app-pack declaration, with no chromeset generator."""
from pathlib import Path
from bootstrap_higher_app.app_pack_contract import AppPackManifestV1
from .widgets import register_crystal_widgets_v1


def register_app_pack_v1():
    return register_crystal_widgets_v1()


def app_pack_manifest_v1():
    return AppPackManifestV1(
        id="crystal",
        label="Crystal",
        static_root=Path(__file__).with_name("rendering").resolve(),
        python_registrar=f"{__name__}:register_app_pack_v1",
    )
