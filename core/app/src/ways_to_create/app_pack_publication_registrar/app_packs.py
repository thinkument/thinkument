"""Explicit central publication list and application-wide default."""
from bootstrap_higher_app.app_pack_contract import AppPackCollectionV1
from .app_pack_families import (AppPackFamilyPublicationV1, SharedWidgetLibraryV1,
                                register_app_pack_family_v1)
from .publication import validate_publications

DEFAULT_APP_PACK_V1 = 'metal_standard'


def _family_v1(family_id, rows, *, chrome_ids, catalog_fingerprint):
    rows = tuple(rows)
    if not catalog_fingerprint:
        raise ValueError(f'Family {family_id!r} has no trusted catalog fingerprint.')
    shared = SharedWidgetLibraryV1(f'{family_id}.widget_library.v1', catalog_fingerprint)
    if len(chrome_ids) != len(rows):
        raise ValueError(f'Family {family_id!r} chrome IDs do not match publication rows.')
    members = tuple(AppPackFamilyPublicationV1(
        app_pack_id=row.manifest_provider().id,
        chrome_id=chrome_id,
        shared_widget_library=shared,
        publication=row,
    ) for row, chrome_id in zip(rows, chrome_ids))
    return register_app_pack_family_v1(family_id, shared, members)


try:
    from authoring_funneling.examples.metal.publication import publication_rows as metal_publications
    from authoring_funneling.examples.metal.per_pack_chromesets.declarations import CHROMETABLES
    from authoring_funneling.examples.metal.shared_widgets.registry import library_catalog_fingerprint_v1 as metal_catalog_fingerprint_v1
    from authoring_funneling.examples.crystal.publication import publication_rows as crystal_publications
    from authoring_funneling.examples.crystal.widgets import library_catalog_fingerprint_v1 as crystal_catalog_fingerprint_v1

    METAL_FAMILY_V1 = _family_v1('metal', metal_publications(),
                                 chrome_ids=tuple(row.chrome_id for row in CHROMETABLES),
                                 catalog_fingerprint=metal_catalog_fingerprint_v1())
    CRYSTAL_FAMILY_V1 = _family_v1('crystal', crystal_publications(), chrome_ids=('crystal',),
                                   catalog_fingerprint=crystal_catalog_fingerprint_v1())
    APP_PACK_FAMILIES_V1 = (METAL_FAMILY_V1, CRYSTAL_FAMILY_V1)
    APP_PACK_PROVIDERS_V1 = tuple(
        member.publication for family in APP_PACK_FAMILIES_V1 for member in family.publication_rows
    )
except ImportError:
    METAL_FAMILY_V1 = None
    CRYSTAL_FAMILY_V1 = None
    APP_PACK_FAMILIES_V1 = ()
    APP_PACK_PROVIDERS_V1 = ()


def app_pack_collection_v1():
    rows = validate_publications(APP_PACK_PROVIDERS_V1)
    manifests = tuple(row.manifest_provider() for row in rows)
    if DEFAULT_APP_PACK_V1 not in {m.id for m in manifests}:
        if not manifests:
            return AppPackCollectionV1(manifests=(), default_app_pack=DEFAULT_APP_PACK_V1)
        raise ValueError('Default app pack must be explicitly published.')
    return AppPackCollectionV1(manifests=manifests, default_app_pack=DEFAULT_APP_PACK_V1)
