"""Install the ordinary teaching pack only for its framework test fixtures."""
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'fixtures'))


@pytest.fixture(autouse=True)
def installed_packito_fixture(monkeypatch):
    from ways_to_create.app_pack_mould.publication import catalog
    from ways_to_create.app_pack_mould.runtime import register_APP_PACK_SESSION_metadata_surface_v1
    from packito_fixture.declare_pack import app_pack_manifest_v1
    original = catalog._installed_entry_points_v1
    ep = SimpleNamespace(name='packito', value='packito_fixture.declare_pack:app_pack_manifest_v1',
                         dist=None, load=lambda:app_pack_manifest_v1)
    monkeypatch.setattr(catalog,'_installed_entry_points_v1',lambda:(*original(),ep))
    catalog.reset_app_pack_catalog_cache_v1()
    register_APP_PACK_SESSION_metadata_surface_v1()
    yield
    catalog.reset_app_pack_catalog_cache_v1()
    register_APP_PACK_SESSION_metadata_surface_v1()
