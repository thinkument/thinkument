from authoring_funneling.examples.crystal.publication import publication_rows
from authoring_funneling.examples.crystal.declare_pack import register_app_pack_v1


def test_direct_manifest_has_complete_local_browser_entry_and_reused_registration():
    rows = publication_rows()
    assert len(rows) == 1
    manifest = rows[0].manifest_provider()
    assert manifest.id == 'crystal'
    assert manifest.browser_module_path.is_file()
    receipt = register_app_pack_v1()
    assert receipt['app_pack'] == 'crystal'
    assert set(receipt['widgets']) == {'crystal.seed', 'crystal.consumer', 'crystal.json_ideator'}
