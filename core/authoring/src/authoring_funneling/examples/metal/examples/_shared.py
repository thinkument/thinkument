from copy import deepcopy
from authoring_funneling.a_typed_PSMCW_authoring import D,compile_strict_tape
from authoring_funneling.examples.metal.shared_widgets.widgets import SEED,CONSUMER,COUNTER

def program(number,widgets,flow,*,symbols=None):
    return {'kind':'think_program_v1','surface_version':'v1','symbols':symbols or {},'puppeteering':{},'run':{'program':{'info':{'id':f'typed_p{number}','title':f'Typed Thinkument {number}'},'widgets':deepcopy(widgets),'flow':deepcopy(flow)},'config':{}}}

def seed(title='Draft',count=1): return {'widget':SEED,'args':{'title':title,'count':count},'bindings':{}}
def counter(start=None,*,fail=False): return {'widget':COUNTER,'args':{'fail':fail},'bindings':{'inputs':{'start':D.value(0) if start is None else start}}}
def consumer(*,heading=None):
    return {'widget':CONSUMER,'args':{},'bindings':{'sources':{'draft':{'widget':'writer','port':'result'},'entries':{'widget':'writer','port':'entries'}},'inputs':{'context':D.dict({'heading':D.ref('draft','title') if heading is None else heading,'items':D.map(D.ref('entries','rows'),D.dict({'label':D.item('title'),'count':D.item('count')})),'note':D.ref('draft','note')})}}}
def step(id,*widgets,**kw): return {'id':id,'widgets':list(widgets),**kw}
def base_sm():
    return {'app_pack_mould':{'app_pack':'metal_standard'},'manual_io':{'persistence':'disabled','include_full_multiframespec_in_ctx':True,'include_forms_emitted_order_in_ctx':True},'session_storage':{'events_snapshot_window':256,'redo_max_depth':8,'redo_action_max_payload_chars':20000}}
def export(higher,C=None):
    from .. import compile_tape
    return compile_tape(higher,base_sm(),C)
