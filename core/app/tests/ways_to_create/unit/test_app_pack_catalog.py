from __future__ import annotations

from ways_to_create.app_pack_mould.publication.catalog import load_app_pack_catalog_v1
from ways_to_create.app_pack_mould.runtime import (
    APP_PACK_SESSION_METADATA_KEY,
    activate_app_pack_mould_v1,
    with_hai_app_pack_v1,
)


def test_catalog_is_discovered_from_installed_manifests() -> None:
    catalog = load_app_pack_catalog_v1()

    assert catalog.default_app_pack is not None 

    assert {"example_notes"}.issubset(catalog.ids)

    for manifest in catalog.packs:
        assert manifest.browser_module_path.is_file(), manifest
        assert manifest.js_module == f"./app_packs_examples/{manifest.id}/index.js"


def test_runtime_activation_registers_all_python_sides() -> None:
    receipt = activate_app_pack_mould_v1()

    assert receipt["kind"] == "app_pack_mould_runtime_activation_receipt_v1"
    assert receipt["metadata"]["key"] == APP_PACK_SESSION_METADATA_KEY
    assert {"example_notes"}.issubset(
        receipt["metadata"]["app_pack_ids"]
    )

    registered_app_packs_examples = {
        row.get("app_pack")
        for row in receipt["app_packs_examples"]
    }

    assert "example_notes" in registered_app_packs_examples


def test_APP_PACK_SESSION_METADATA_KEY_is_the_stable_remote_psmc_wire() -> None:
    # Remote P/SM/C callers cannot import this package. Locking the literal is
    # therefore intentional: authoring_PSMC.template_thinkprogram_SM_app_packs writes the same dead-JSON key.
    assert APP_PACK_SESSION_METADATA_KEY == "app_pack_mould"

    authored = with_hai_app_pack_v1(
        {},
        app_pack="example_notes",
        app_args={"consumer": "remote-sdk"},
    )
    assert authored == {
        "app_pack_mould": {
            "app_pack": "example_notes",
            "app_args": {"consumer": "remote-sdk"},
        }
    }


def test_with_hai_app_pack_is_copying_and_rejects_unknown_pack() -> None:
    original = {
        "manual_io": {
            "persistence": "disabled",
        }
    }

    out = with_hai_app_pack_v1(
        original,
        app_pack="example_notes",
        app_args={"project": "demo"},
    )

    assert original == {
        "manual_io": {
            "persistence": "disabled",
        }
    }
    assert out[APP_PACK_SESSION_METADATA_KEY] == {
        "app_pack": "example_notes",
        "app_args": {
            "project": "demo",
        },
    }

    packito = with_hai_app_pack_v1(
        {},
        app_pack="example_notes",
        app_args={"lesson": "pedagogy"},
    )

    assert packito[APP_PACK_SESSION_METADATA_KEY] == {
        "app_pack": "example_notes",
        "app_args": {
            "lesson": "pedagogy",
        },
    }

    try:
        with_hai_app_pack_v1(
            {},
            app_pack="does-not-exist",
        )
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("unknown app pack must fail closed")



"""One auto-scaling health sheet for every installed HAI app pack."""


from pathlib import Path

from ways_to_create.app_pack_mould.publication.catalog import (
    load_app_pack_catalog_v1,
    APP_PACK_ENTRYPOINT_GROUP,
    validate_installed_app_pack_manifests_v1,
)


def test_every_installed_app_pack_manifest_is_healthy() -> None:
    receipt = validate_installed_app_pack_manifests_v1()

    assert receipt["ok"] is True
    assert receipt["entry_point_group"] == APP_PACK_ENTRYPOINT_GROUP
    assert receipt["app_packs_examples"]



ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
PILE_ROOT = SRC / "ways_to_create" / "app_packs_examples"


def test_bundled_piles_are_self_contained_and_declared_once() -> None:
    catalog = load_app_pack_catalog_v1()
    bundled = {"example_notes"}

    assert bundled.issubset(catalog.ids)
    for app_pack_id in bundled:
        pile = PILE_ROOT / app_pack_id
        manifest = catalog.by_id(app_pack_id)

        assert (pile / "declare_pack.py").is_file(), app_pack_id
        assert manifest.static_root == (pile / "js").resolve()
        assert manifest.browser_module_path == (pile / "js" / "index.js").resolve()
        assert manifest.browser_module_path.is_file()

