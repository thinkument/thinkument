"""Immutable family contributions sharing one widget library across packs."""
from dataclasses import dataclass

from .contracts import PackPublicationRowV1
from .publication import validate_publications


@dataclass(frozen=True)
class SharedWidgetLibraryV1:
    library_id: str
    catalog_fingerprint: str

    def __post_init__(self):
        if not self.library_id or not self.catalog_fingerprint:
            raise ValueError('A shared widget library needs an ID and catalog fingerprint.')


@dataclass(frozen=True)
class AppPackFamilyPublicationV1:
    app_pack_id: str
    chrome_id: str
    shared_widget_library: SharedWidgetLibraryV1
    publication: PackPublicationRowV1


@dataclass(frozen=True)
class RegisteredAppPackFamilyV1:
    family_id: str
    shared_widget_library: SharedWidgetLibraryV1
    publication_rows: tuple[AppPackFamilyPublicationV1, ...]


def register_app_pack_family_v1(family_id, shared_widget_library, publication_rows):
    """Validate a K-publication family without mutating process registries."""
    if not isinstance(family_id, str) or not family_id.strip():
        raise ValueError('Family ID must be a nonempty string.')
    if not isinstance(shared_widget_library, SharedWidgetLibraryV1):
        raise TypeError('Expected a SharedWidgetLibraryV1 reference.')
    rows = tuple(publication_rows)
    if not rows:
        raise ValueError('An app-pack family requires at least one publication row.')
    ids, chromes = set(), set()
    for row in rows:
        if not isinstance(row, AppPackFamilyPublicationV1):
            raise TypeError('Expected AppPackFamilyPublicationV1 rows.')
        if row.shared_widget_library != shared_widget_library:
            raise ValueError('All family publications must reference the same shared widget library.')
        if not row.app_pack_id or row.app_pack_id in ids:
            raise ValueError(f'Duplicate or empty app-pack ID {row.app_pack_id!r}.')
        if not row.chrome_id or row.chrome_id in chromes:
            raise ValueError(f'Duplicate or empty chrome ID {row.chrome_id!r}.')
        if not isinstance(row.publication, PackPublicationRowV1):
            raise TypeError('Each family row requires a PackPublicationRowV1.')
        manifest = row.publication.manifest_provider()
        if manifest.id != row.app_pack_id:
            raise ValueError(f'Family app-pack ID does not match manifest {manifest.id!r}.')
        ids.add(row.app_pack_id)
        chromes.add(row.chrome_id)
    validate_publications(tuple(row.publication for row in rows))
    return RegisteredAppPackFamilyV1(family_id, shared_widget_library, rows)
