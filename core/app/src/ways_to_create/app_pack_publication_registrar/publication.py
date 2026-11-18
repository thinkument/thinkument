"""Validate publication rows without depending on concrete creative families."""
from .contracts import PackPublicationRowV1

def validate_publications(rows):
    rows = tuple(rows)
    pack_ids, profile_ids = set(), set()
    for row in rows:
        if not isinstance(row, PackPublicationRowV1):
            raise TypeError('Expected a PackPublicationRowV1.')
        manifest = row.manifest_provider()
        profile = row.authoring_profile_provider()
        description = profile.describe()
        if manifest.id in pack_ids:
            raise ValueError(f'Duplicate pack {manifest.id!r}.')
        if description['profile_id'] in profile_ids:
            raise ValueError(f"Duplicate profile {description['profile_id']!r}.")
        if description['pack_id'] != manifest.id:
            raise ValueError(f'Profile and manifest pack mismatch for {manifest.id!r}.')
        pack_ids.add(manifest.id)
        profile_ids.add(description['profile_id'])
    return rows
