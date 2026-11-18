"""Direct and generated publications share contracts and actual widget identities."""
from dataclasses import replace
import pytest
from ways_to_create.app_pack_publication_registrar.contracts import PackPublicationRowV1
from ways_to_create.app_pack_publication_registrar.publication import validate_publications
from authoring_funneling.examples.metal import publication as metal
from authoring_funneling.examples.crystal import publication as crystal
from ways_to_create.app_pack_publication_registrar.app_packs import app_pack_collection_v1
from ways_to_create.app_pack_publication_registrar.static_roots import shared_static_roots_v1


def test_three_publications_one_explicit_default_and_shared_widgets():
    metal.register_metal_standard()
    crystal.register_app_pack_v1()
    collection = app_pack_collection_v1()
    assert [m.id for m in collection.manifests] == ['metal_standard', 'metal_compact', 'crystal']
    assert collection.default_app_pack == 'metal_standard'
    profiles = [row.authoring_profile_provider() for row in (*metal.publication_rows(), *crystal.publication_rows())]
    assert profiles[0].describe_widgets() == profiles[1].describe_widgets()
    assert {w['widget_id'] for w in profiles[2].describe_widgets()} == {
        'crystal.seed', 'crystal.consumer', 'crystal.json_ideator'}
    assert all(w['widget_id'].startswith('crystal.') for w in profiles[2].describe_widgets())
    assert profiles[2].__class__.__name__ == 'TypedAuthoringProfile'
    roots = shared_static_roots_v1()
    assert len(roots) == 1
    assert roots[0].logical_prefix == '_funneled_apps/examples/metal/shared_rendering'


def test_duplicate_and_mismatched_publications_are_rejected():
    row = crystal.publication_rows()[0]
    with pytest.raises(ValueError, match='Duplicate pack'):
        validate_publications((row, row))
    wrong = PackPublicationRowV1(metal.publication_rows()[0].manifest_provider, row.authoring_profile_provider)
    with pytest.raises(ValueError, match='mismatch'):
        validate_publications((wrong,))


def test_new_chrome_changes_only_metal_cardinality(monkeypatch):
    from authoring_funneling.examples.metal.per_pack_chromesets import declarations
    rows = declarations.CHROMETABLES
    monkeypatch.setattr(declarations, 'CHROMETABLES', (*rows, replace(rows[0], id='metal_extra', chrome_id='extra')))
    assert len(metal.publication_rows()) == 3
    assert len(crystal.publication_rows()) == 1


def test_conflicting_static_mount_is_rejected(monkeypatch, tmp_path):
    from ways_to_create.app_pack_publication_registrar import static_roots
    from __staticfiles_mgmt import StaticRootSpec
    roots = static_roots.shared_static_roots_v1()
    conflict = StaticRootSpec(name='conflict', path=tmp_path, logical_prefix=roots[0].logical_prefix)
    monkeypatch.setattr(static_roots, 'STATIC_ROOT_PROVIDERS', (lambda: roots, lambda: (conflict,)))
    with pytest.raises(ValueError, match='Conflicting static mount'):
        static_roots.shared_static_roots_v1()


def test_shared_roots_publish_only_browser_resources():
    from __staticfiles_mgmt import resolve_static_asset_path
    from authoring_funneling.examples.metal.shared_rendering.static_assets import STATIC_ROOT, STATIC_PREFIX

    roots = shared_static_roots_v1()
    assert metal.shared_static_roots_v1() != crystal.shared_static_roots_v1()
    metal_root = next(r for r in roots if r.logical_prefix == STATIC_PREFIX)
    assert metal_root.path == STATIC_ROOT
    for spec in roots:
        resources = [path for path in spec.path.rglob('*') if path.is_file()]
        assert resources
        for source in resources:
            relative = source.relative_to(spec.path)
            assert source.suffix not in {'.py', '.pyc', '.pyo'}
            assert '__pycache__' not in relative.parts
            logical = f'{spec.logical_prefix}/{relative.as_posix()}'
            assert resolve_static_asset_path(logical) == source.resolve()
