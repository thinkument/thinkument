"""Assemble Metal shared assets into one typed pack per chrome."""
from functools import partial
from pathlib import Path
from bootstrap_higher_app.app_pack_contract import AppPackManifestV1, PackPublicationRowV1
from authoring_funneling.a_typed_PSMCW_authoring.authoring import AuthoringError, validate_launch_surfaces
from authoring_funneling.a_typed_PSMCW_authoring.profile import TypedAuthoringProfile
from .per_pack_chromesets.declarations import CHROMETABLES, DEFAULT_CHROME, chrome_rows
from .shared_rendering.catalogue import validate_browser_catalogue_v1
from .shared_rendering.static_assets import STATIC_ROOT, STATIC_PREFIX

class ChromedAuthoringProfile(TypedAuthoringProfile):
    def __init__(self, pack_id):
        from .shared_widgets.registry import widget_rows
        validate_browser_catalogue_v1()
        super().__init__(pack_id, profile_id=f'{pack_id}.typed_ports.v1', widget_ids=widget_rows())

    def compile(self, draft):
        from copy import deepcopy
        draft = deepcopy(draft)
        if not isinstance(draft, dict) or not isinstance(draft.get('SM'), dict):
            return super().compile(draft)
        pocket = draft['SM'].setdefault('app_pack_mould', {})
        if not isinstance(pocket, dict):
            raise AuthoringError('session_metadata',['SM','app_pack_mould'])
        chosen = pocket.get('app_pack', self.pack_id)
        if chosen != self.pack_id and not (isinstance(chosen,str) and chosen.startswith('$')):
            raise AuthoringError('pack_selection_mismatch',['SM','app_pack_mould','app_pack'])
        pocket.setdefault('app_pack', self.pack_id)
        pocket.setdefault('app_args', {})
        export = super().compile(draft)
        effective = validate_launch_surfaces(export['P'], export['SM'], export['C'])
        from _thinksessions.sesh_metadata.sesh_metadata_surface_puppeteering import bind_session_metadata_symbols_v1
        selected = bind_session_metadata_symbols_v1(effective['session_metadata'])['app_pack_mould']['app_pack']
        from .shared_rendering.aesthetics import AESTHETICS_KEY, validate_aesthetics
        metadata = bind_session_metadata_symbols_v1(effective['session_metadata'])
        if AESTHETICS_KEY in metadata:
            body = export['P']['run']['program']
            ids = {f"{body['info']['id']}.{step['id']}" for step in body['flow']}
            try: validate_aesthetics(metadata[AESTHETICS_KEY],step_ids=ids)
            except (ValueError,TypeError,KeyError) as exc:
                raise AuthoringError('aesthetics',['SM',AESTHETICS_KEY,*getattr(exc,'path',[])],str(exc)) from exc
        if selected != self.pack_id:
            raise AuthoringError('pack_selection_mismatch',['C'])
        return export


def manifest_for(row):
    return AppPackManifestV1(id=row.id,label=row.label,
        static_root=Path(__file__).with_name('per_pack_chromesets').joinpath(row.browser_asset_root).resolve(),
        python_registrar=f'{__name__}:register_{row.id}')


def publication_rows():
    return tuple(PackPublicationRowV1(partial(manifest_for,row),partial(ChromedAuthoringProfile,row.id))
                 for row in chrome_rows().values())


def shared_static_roots_v1():
    from __staticfiles_mgmt import StaticRootSpec
    return (StaticRootSpec(name='creativity:chromed-library',path=STATIC_ROOT,logical_prefix=STATIC_PREFIX),)


def _register(pack_id):
    from .shared_widgets.registry import register_library_v1
    validate_browser_catalogue_v1()
    return register_library_v1(pack_id)


# Each manifest's ordinary zero-argument registrar returns its own pack ID.
for _row in CHROMETABLES:
    globals()[f'register_{_row.id}'] = partial(_register,_row.id)


