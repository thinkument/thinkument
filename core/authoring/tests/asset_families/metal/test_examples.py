"""Exported JSON tapes run through the highest public façade."""
from copy import deepcopy
from importlib import import_module
import json
import pytest
from _thinksessions.run import run_from_here as api
from authoring_funneling.examples.metal.publication import register_metal_standard as register_app_pack_v1
from authoring_funneling.examples.metal.examples import SERIES_MODULES
from authoring_funneling.a_typed_PSMCW_authoring.widget import OUTPUT_STATE

pytestmark = pytest.mark.django_db


def events(sid, collected=None):
    if collected:
        return collected
    return api.get_live_session_events(session_id=sid)

def output_writes(sid, collected=None):
    return [e['payload']['body']['state_writes'][OUTPUT_STATE] for e in events(sid, collected) if e.get('name')=='audit-outs' and OUTPUT_STATE in e.get('payload', {}).get('body', {}).get('state_writes', {})]

def dispatch(sid, callbacks=None, **kwargs):
    return api.dispatch_live_session_action(session_id=sid, action='STEP', identity_id='typed-client', threaded_callbacks=callbacks, **kwargs)

def launch(tape):
    register_app_pack_v1()
    return api.create_live_session_from_program(program=tape['P'],program_language='think_program_v1',session_metadata=tape['SM'],initial_parameter_overrides=tape['C'])['session_id']

def fills_for(widgets):
    return {name:{'confirm' if w['widget'].endswith('.seed') else 'ack' if w['widget'].endswith('.consumer') else 'finish':'accepted'} for name,w in widgets.items()}

@pytest.mark.parametrize('module',SERIES_MODULES)
def test_exported_series_completion_and_public_outputs(module):
    tape=json.loads(json.dumps(import_module('authoring_funneling.examples.metal.examples.'+module).TAPE))
    sid=launch(tape)
    captured = []
    callbacks = {'explosion_events_callback': captured.append}
    try:
        dispatch(sid, callbacks=callbacks)
        body=tape['P']['run']['program']
        for step in body['flow']:
            receipt=dispatch(sid, callbacks=callbacks, user_fill=fills_for({name:body['widgets'][name] for name in step['widgets']}))
            assert receipt.get('system_error') is None
            assert receipt.get('last_error') is None
        assert api.get_live_session_current_report(session_id=sid)['finished'] is True
        assert output_writes(sid, captured)
        if module.startswith('program2'): assert any(w.get('result',{}).get('heading')=='Draft / Review $literal' for w in output_writes(sid, captured))
        if module.startswith('program4'): assert any(w.get('result',{}).get('heading')=='Again Published' for w in output_writes(sid, captured))
        ops={}
        for e in events(sid, captured):
            if e.get('name') in ('audit-ins','audit-outs','audit-error'): ops.setdefault(e['payload']['operation_id'],[]).append(e['name'])
        assert all(names==['audit-ins','audit-outs'] for names in ops.values())
    finally: api.delete_live_session(session_id=sid)


def test_latest_materialization_after_repeated_explosions_undo_redo():
    tape=import_module('authoring_funneling.examples.metal.examples.'+SERIES_MODULES[-1]).TAPE
    sid=launch(tape)
    captured = []
    callbacks = {'explosion_events_callback': captured.append}
    try:
        dispatch(sid, callbacks=callbacks)
        for i in range(3): dispatch(sid, callbacks=callbacks, user_signal={'datum_id':'counter','kind':'increment','info':{}})
        assert output_writes(sid, captured)[-1]['result']['count']==4
        dispatch(sid, callbacks=callbacks, user_fill={'counter':{'finish':'first'}})
        # Second mount sees the accepted value from the first appearance, even
        # though its generated cap selected the first mounting reference row.
        assert output_writes(sid, captured)[-1]['result']['count']==4
        api.dispatch_live_session_action(session_id=sid,action='UNDO',identity_id='typed-client')
        # Ordinary continuity first unwinds the second mount, then the manual fill.
        api.dispatch_live_session_action(session_id=sid,action='UNDO',identity_id='typed-client')
        api.dispatch_live_session_action(session_id=sid,action='REDO',identity_id='typed-client')
        dispatch(sid,user_fill={'counter':{'finish':'second'}})
        assert api.get_live_session_current_report(session_id=sid)['finished']
    finally: api.delete_live_session(session_id=sid)


def test_audited_failure_preserves_outputs():
    tape=import_module('authoring_funneling.examples.metal.examples.'+SERIES_MODULES[4]).FAILURE_TAPE
    sid=launch(tape)
    captured = []
    callbacks = {'explosion_events_callback': captured.append}
    try:
        dispatch(sid, callbacks=callbacks); before=deepcopy(output_writes(sid, captured))
        receipt=dispatch(sid, callbacks=callbacks, user_fill={'counter':{'finish':'rejected'}})
        assert receipt.get('last_error') or receipt.get('system_error')
        assert any(e.get('name')=='audit-error' for e in events(sid, captured))
        assert output_writes(sid, captured)==before
        dispatch(sid, callbacks=callbacks, user_signal={'datum_id':'counter','kind':'increment','info':{}})
        assert output_writes(sid, captured)[-1]['result']=={'count':6,'note':None}
    finally: api.delete_live_session(session_id=sid)


def test_source_step_exceeds_default_cap():
    from authoring_funneling.examples.metal.examples._shared import program,seed,consumer,step,export
    widgets={f'seed{i}':seed(str(i)) for i in range(25)}
    widgets['writer']=seed('Last source',7);widgets['reader']=consumer()
    tape=export(program(99,widgets,[step('many',*list(widgets)[:-1]),step('read','reader')]))
    history=tape['P']['run']['program']['flow'][1]['overrides']['wires']['reader']['strict_sources_v1']['history']
    assert history['max_results']==26
    sid=launch(tape)
    captured = []
    callbacks = {'explosion_events_callback': captured.append}
    try:
        dispatch(sid, callbacks=callbacks)
        dispatch(sid, callbacks=callbacks, user_fill={name:{'confirm':'yes'} for name in list(widgets)[:-1]})
        assert output_writes(sid, captured)[-1]['result']['heading']=='Last source'
        dispatch(sid, callbacks=callbacks, user_fill={'reader':{'ack':'yes'}})
        assert api.get_live_session_current_report(session_id=sid)['finished']
    finally: api.delete_live_session(session_id=sid)


def test_later_incompatible_C_fails_inside_audited_mount():
    tape=deepcopy(import_module('authoring_funneling.examples.metal.examples.'+SERIES_MODULES[3]).TAPE)
    tape['C']={'ui.label':2}
    sid=launch(tape)
    captured = []
    callbacks = {'explosion_events_callback': captured.append}
    try:
        dispatch(sid, callbacks=callbacks)
        from bindings2bindingsTM import RuntimeValueError
        # Ordinary automatic mount/context preparation propagates this boundary
        # exception rather than guaranteeing a dispatch system-error packet.
        with pytest.raises(RuntimeValueError) as error:
            dispatch(sid, callbacks=callbacks, user_fill={'writer':{'confirm':'yes'}})
        assert error.value.details['code']=='value_type'
        assert error.value.details['path']==['P','parameters','label']
        assert not any('heading' in w.get('result',{}) for w in output_writes(sid, captured))
    finally: api.delete_live_session(session_id=sid)
