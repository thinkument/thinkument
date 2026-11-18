"""Pack-neutral authoring interfaces. Launch protocols remain ordinary P/SM/C."""
from copy import deepcopy
import hashlib
import json
from typing import Protocol, Mapping

class AuthoringProfile(Protocol):
    def describe(self) -> dict: ...
    def describe_widgets(self) -> list: ...
    def validate(self, draft: Mapping) -> dict: ...
    def compile(self, draft: Mapping) -> dict: ...

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

class AuthoringError(ValueError):
    def __init__(self,code,path=(),message='',details=None):
        self.details=dict(code=code,path=list(path),message=message,**(details or {}))
        super().__init__(message or code)

def check_draft(draft,profile_id):
    if not isinstance(draft,Mapping): raise AuthoringError('invalid_draft',[])
    if draft.get('profile_id')!=profile_id: raise AuthoringError('profile_mismatch',['profile_id'],'Switching profiles requires revalidation.')
    if set(draft)!={'profile_id','W','P','SM','C'}: raise AuthoringError('draft_fields',[],'Expected profile_id, W, P, SM and C.')
    if type(draft['W']) is not list or not all(type(w) is str and w for w in draft['W']): raise AuthoringError('invalid_widget_selection',['W'])
    for surface in ('P','SM'):
        if not isinstance(draft[surface],Mapping): raise AuthoringError('invalid_surface',[surface])
    if draft['C'] is not None and not isinstance(draft['C'],Mapping): raise AuthoringError('invalid_surface',['C'])

def validation_receipt(profile,draft):
    try:
        export=profile.compile(draft)
        return {'ok':True,'profile_id':profile.describe()['profile_id'],'errors':[],'contract_fingerprint':export['contract_fingerprint']}
    except (ValueError,TypeError,KeyError,AttributeError,IndexError) as exc:
        detail=deepcopy(getattr(exc,'details',{}))
        return {'ok':False,'profile_id':profile.describe()['profile_id'],'errors':[{'code':detail.pop('code','invalid_draft'),'path':detail.pop('path',['P']),'message':str(exc),**detail}]}

def validate_launch_surfaces(P,SM,C):
    from _thinksessions.sesh_metadata.sesh_metadata_surface_puppeteering import route_puppeteering_overlay_to_symbol_surfaces_v1,bind_session_metadata_symbols_v1
    from _thinksessions.sesh_metadata.sesh_metadata_surface import coerce_session_metadata
    from _thinkprogram.thinkprogramTM.api import lower_think_program_to_kernel_program_v1
    try:
        surfaces=route_puppeteering_overlay_to_symbol_surfaces_v1(surfaces={'program':P,'session_metadata':SM},initial_parameter_overrides=C)
    except (ValueError,TypeError) as exc: raise AuthoringError('customization_routing',['C'],str(exc)) from exc
    try: coerce_session_metadata(bind_session_metadata_symbols_v1(surfaces['session_metadata']))
    except (ValueError,TypeError) as exc: raise AuthoringError('session_metadata',['SM'],str(exc)) from exc
    try: lower_think_program_to_kernel_program_v1(surfaces['program'])
    except (ValueError,TypeError) as exc: raise AuthoringError('ordinary_program',['P'],str(exc)) from exc
    return surfaces

