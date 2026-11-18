import pytest

from ways_to_create.app_pack_publication_registrar.app_pack_families import (
    AppPackFamilyPublicationV1, SharedWidgetLibraryV1, register_app_pack_family_v1,
)
from ways_to_create.app_pack_publication_registrar.app_packs import (
    APP_PACK_FAMILIES_V1, DEFAULT_APP_PACK_V1, app_pack_collection_v1,
)
from ways_to_create.app_pack_publication_registrar.contracts import PackPublicationRowV1


def test_metal_family_has_k_publications_over_one_shared_catalogue():
    metal, crystal = APP_PACK_FAMILIES_V1
    assert metal.family_id == 'metal'
    assert len(metal.publication_rows) == 2
    assert len({row.app_pack_id for row in metal.publication_rows}) == 2
    assert {row.shared_widget_library for row in metal.publication_rows} == {metal.shared_widget_library}
    assert len(crystal.publication_rows) == 1
    assert app_pack_collection_v1().default_app_pack == DEFAULT_APP_PACK_V1 == 'metal_standard'


def test_family_rejects_empty_duplicate_and_mismatched_shared_references():
    library = SharedWidgetLibraryV1('example.library.v1', 'fingerprint')
    with pytest.raises(ValueError, match='at least one'):
        register_app_pack_family_v1('example', library, ())
    row = PackPublicationRowV1(lambda: type('Manifest', (), {'id': 'example_pack'})(), lambda: None)
    member = AppPackFamilyPublicationV1('example_pack', 'standard', library, row)
    with pytest.raises(ValueError, match='Duplicate'):
        register_app_pack_family_v1('example', library, (member, member))
    other = SharedWidgetLibraryV1('other.library.v1', 'other-fingerprint')
    mismatch = AppPackFamilyPublicationV1('other_pack', 'compact', other, row)
    with pytest.raises(ValueError, match='same shared widget library'):
        register_app_pack_family_v1('example', library, (member, mismatch))


def test_family_rejects_manifest_id_mismatch_and_empty_or_duplicate_chrome_ids():
    library = SharedWidgetLibraryV1('family.boundary.v1', 'fingerprint')
    def publication(manifest_id):
        row = PackPublicationRowV1(lambda: type('Manifest', (), {'id': manifest_id})(), lambda: None)
        return row
    mismatch = AppPackFamilyPublicationV1('claimed_pack', 'standard', library, publication('actual_pack'))
    with pytest.raises(ValueError, match='does not match manifest'):
        register_app_pack_family_v1('family', library, (mismatch,))

    empty = AppPackFamilyPublicationV1('empty_chrome', '', library, publication('empty_chrome'))
    with pytest.raises(ValueError, match='empty chrome ID'):
        register_app_pack_family_v1('family', library, (empty,))

    first = AppPackFamilyPublicationV1('pack_a', 'same', library, publication('pack_a'))
    second = AppPackFamilyPublicationV1('pack_b', 'same', library, publication('pack_b'))
    with pytest.raises(ValueError, match='Duplicate or empty chrome ID'):
        register_app_pack_family_v1('family', library, (first, second))
