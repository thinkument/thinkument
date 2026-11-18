from __future__ import annotations

"""Real importlib.metadata proof of independent external-pack installation."""

import importlib
from importlib import metadata
from pathlib import Path
import sys

import pytest

from bootstrap_higher_app.app_pack_contract import (
    APP_PACK_ENTRYPOINT_GROUP,
    AppPackManifestV1,
    coerce_app_pack_manifest_v1,
)
from ways_to_create.app_pack_mould.publication import catalog
from ways_to_create.app_pack_mould.publication.manifest import (
    AppPackManifestV1 as LegacyManifest,
)
from ways_to_create.app_pack_mould.runtime import _activate_manifest_v1, with_hai_app_pack_v1
from ways_to_create.app_pack_mould.static_assets import thinkument_static_roots_v1


PACK_ID = "vendor_think"
PACK_MICRO = "vendor_think_ref"


@pytest.fixture
def installed_external_pack(tmp_path: Path, monkeypatch):
    """Create a genuine discoverable distribution, without pip or network.

    Its package imports only framework APIs. Distribution metadata supplies the
    same entry-point mechanism as an installed wheel or editable distribution.
    """

    package = tmp_path / PACK_ID
    js = package / "js"
    js.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (js / "index.js").write_text(
        'export default {kind:"app_pack_mould_app_pack_v1",'
        'id:"vendor_think",styleUrls:[],callables:{},'
        'widgetRenderers:{},epsRoutes:{},outers:{}};\n',
        encoding="utf-8",
    )
    (package / "declare_pack.py").write_text(
        'from pathlib import Path\n'
        'from bootstrap_higher_app.app_pack_contract import AppPackManifestV1\n'
        'def app_pack_manifest_v1():\n'
        '    return AppPackManifestV1(\n'
        '        id="vendor_think", label="Vendor Think",\n'
        '        static_root=Path(__file__).with_name("js").resolve(),\n'
        '        python_registrar="vendor_think.registration:register_app_pack_v1",\n'
        '    )\n',
        encoding="utf-8",
    )
    (package / "registration.py").write_text(
        """from _thinkprogram._thinkcontinuitykernelTM import api as back_api
from _thinkprogram._iomicrosTM.core.micro_registry import (
    MicroTypeDefinition, ValidatorPolicy, register_micro_type_definition,
)

CALLS = 0


def normalize_vendor_ref(value):
    return str(value).strip().upper()


def is_vendor_ref(value):
    import re
    return re.fullmatch(r"VP-[0-9]{4}", str(value)) is not None


VENDOR_MICRO = MicroTypeDefinition(
    name="vendor_think_ref",
    description="External-pack reference number.",
    json_schema={"type": "string", "pattern": r"^VP-[0-9]{4}$"},
    modality="text",
    validators=(ValidatorPolicy(path="vendor_think.registration:is_vendor_ref"),),
    python_types=(str,),
    coerce=normalize_vendor_ref,
    coerce_to_micro_types=("text",),
    python_casts={str: normalize_vendor_ref},
)


def register_app_pack_v1():
    global CALLS
    register_micro_type_definition(VENDOR_MICRO)
    CALLS += 1
    back_api.register_kernel_step_fn_v1()
    return {"app_pack": "vendor_think", "ok": True, "calls": CALLS}


def fail_registration_v1():
    return {"app_pack": "vendor_think", "ok": False}
""",
        encoding="utf-8",
    )

    dist = tmp_path / "vendor_think_pack-0.0.1.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: vendor-think-pack\nVersion: 0.0.1\n",
        encoding="utf-8",
    )
    (dist / "entry_points.txt").write_text(
        f"[{APP_PACK_ENTRYPOINT_GROUP}]\n"
        "vendor_think = vendor_think.declare_pack:app_pack_manifest_v1\n",
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    catalog.reset_app_pack_catalog_cache_v1()
    try:
        yield package
    finally:
        # The integration runs in-process; undo only this test's extension.
        from _thinkprogram._iomicrosTM.core.micro_registry import MICRO_TYPES
        MICRO_TYPES.pop(PACK_MICRO, None)
        catalog.reset_app_pack_catalog_cache_v1()
        for name in tuple(sys.modules):
            if name == PACK_ID or name.startswith(f"{PACK_ID}."):
                sys.modules.pop(name, None)
        importlib.invalidate_caches()


def test_external_distribution_is_discovered_with_no_host_pack_list(
    installed_external_pack: Path,
) -> None:
    assert LegacyManifest is AppPackManifestV1
    matches = tuple(
        ep for ep in metadata.entry_points().select(group=APP_PACK_ENTRYPOINT_GROUP)
        if ep.name == PACK_ID
    )
    assert len(matches) == 1
    assert matches[0].value == "vendor_think.declare_pack:app_pack_manifest_v1"

    installed = catalog.load_app_pack_catalog_v1()
    assert PACK_ID in installed.ids
    manifest = installed.by_id(PACK_ID)
    assert manifest.static_root == installed_external_pack / "js"
    assert manifest.browser_module_path.is_file()
    assert manifest.js_module == "./app_packs_examples/vendor_think/index.js"

    static_roots = thinkument_static_roots_v1()
    vendor_roots = [row for row in static_roots if row.name == f"app-pack:{PACK_ID}"]
    assert len(vendor_roots) == 1
    assert vendor_roots[0].logical_prefix == manifest.logical_prefix
    assert vendor_roots[0].path.resolve() == manifest.static_root

    selected = with_hai_app_pack_v1(
        {"other_pocket": {"keep": True}},
        app_pack=PACK_ID,
        app_args={"source": "external"},
    )
    assert selected["other_pocket"] == {"keep": True}
    assert selected["app_pack_mould"] == {
        "app_pack": PACK_ID,
        "app_args": {"source": "external"},
    }
    with pytest.raises(KeyError, match="unknown installed"):
        with_hai_app_pack_v1({}, app_pack="uninstalled")


def test_external_registrar_imports_backend_and_runs_only_on_activation(
    installed_external_pack: Path, monkeypatch,
) -> None:
    del installed_external_pack
    backend = importlib.import_module("_thinkprogram._thinkcontinuitykernelTM.api")
    calls: list[str] = []
    monkeypatch.setattr(
        backend, "register_kernel_step_fn_v1", lambda: calls.append("kernel")
    )

    manifest = catalog.load_app_pack_catalog_v1().by_id(PACK_ID)
    registrar_module = importlib.import_module("vendor_think.registration")
    from _thinkprogram._iomicrosTM.core.micro_registry import (
        MICRO_TYPES,
        get_micro_type_definition,
        is_validator_allowed_for_micro,
        list_public_micro_types,
        validate_micro_registry_integrity,
    )

    # Manifest discovery and import of the registrar do not mutate the engine.
    assert PACK_MICRO not in MICRO_TYPES
    assert registrar_module.CALLS == 0
    assert calls == []

    receipt = _activate_manifest_v1(manifest)
    assert receipt == {"app_pack": PACK_ID, "ok": True, "calls": 1}
    assert registrar_module.CALLS == 1
    assert calls == ["kernel"]

    # This is the *real shared backend registry*, not an framework-4-services shadow map.
    definition = get_micro_type_definition(PACK_MICRO)
    assert definition is registrar_module.VENDOR_MICRO
    assert definition.coerce(" vp-0042 ") == "VP-0042"
    assert definition.json_schema == {
        "type": "string", "pattern": r"^VP-[0-9]{4}$",
    }
    assert {"text", "integer", PACK_MICRO} <= set(list_public_micro_types())
    assert is_validator_allowed_for_micro(
        micro_type=PACK_MICRO,
        validator_path="vendor_think.registration:is_vendor_ref",
    )
    validate_micro_registry_integrity()

    # Activating the same installed pack twice must not collide with itself.
    assert _activate_manifest_v1(manifest) == {
        "app_pack": PACK_ID, "ok": True, "calls": 2,
    }
    assert calls == ["kernel", "kernel"]

    failed_manifest = AppPackManifestV1(
        id=PACK_ID,
        label="Failure proof",
        static_root=manifest.static_root,
        python_registrar="vendor_think.registration:fail_registration_v1",
    )
    with pytest.raises(RuntimeError, match="did not report successful"):
        _activate_manifest_v1(failed_manifest)


def test_bad_contracts_rejected_before_activation(tmp_path: Path) -> None:
    js = tmp_path / "js"
    js.mkdir()
    with pytest.raises(ValueError, match="manifest.id must match"):
        AppPackManifestV1(id="../escape", label="Bad", static_root=js)
    with pytest.raises(FileNotFoundError, match="browser module is missing"):
        coerce_app_pack_manifest_v1({
            "id": "missing_js", "label": "Missing", "static_root": js,
        })
    with pytest.raises(KeyError, match="unknown keys"):
        coerce_app_pack_manifest_v1({
            "id": "unknown", "label": "Unknown", "static_root": js,
            "execute_python": "arbitrary code",
        })
    with pytest.raises(ValueError, match="python.module:attribute"):
        AppPackManifestV1(
            id="bad_ref", label="Bad", static_root=js,
            python_registrar="vendor_think.registration:../../escape",
        )


def test_external_pack_cannot_shadow_bundled_pack(
    installed_external_pack: Path, monkeypatch,
) -> None:
    original = catalog._installed_entry_points_v1
    external = next(ep for ep in original() if ep.name == PACK_ID)

    class ForgedEntryPoint:
        name = "example_notes"
        value = "vendor_think.declare_pack:app_pack_manifest_v1"
        dist = None

        def load(self):
            return lambda: AppPackManifestV1(
                id="example_notes", label="Forged", static_root=installed_external_pack / "js"
            )

    monkeypatch.setattr(
        catalog, "_installed_entry_points_v1",
        lambda: (external, ForgedEntryPoint()),
    )
    catalog.reset_app_pack_catalog_cache_v1()
    bundled = next(ep for ep in original() if ep.name == "example_notes")
    monkeypatch.setattr(catalog, "_installed_entry_points_v1", lambda: (external, bundled, ForgedEntryPoint()))
    with pytest.raises(ValueError, match="duplicate installed"):
        catalog.load_app_pack_catalog_v1()
