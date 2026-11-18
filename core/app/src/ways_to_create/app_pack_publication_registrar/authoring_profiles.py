"""Resolve a published typed profile by its concrete pack identity."""
from authoring_funneling.a_typed_PSMCW_authoring.authoring import AuthoringError

def resolve_authoring_profile(pack_id):
    from .app_packs import APP_PACK_PROVIDERS_V1
    for row in APP_PACK_PROVIDERS_V1:
        if row.manifest_provider().id==pack_id:
            profile = row.authoring_profile_provider()
            from authoring_funneling.a_typed_PSMCW_authoring.profile import TypedAuthoringProfile
            if not isinstance(profile, TypedAuthoringProfile):
                raise AuthoringError('strict_profile_required', ['profile_id'], pack_id)
            return profile
    raise AuthoringError('unknown_pack',['profile_id'],pack_id)
