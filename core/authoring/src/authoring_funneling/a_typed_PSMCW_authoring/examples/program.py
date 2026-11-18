"""Explicit compilation example for an independently declared pack widget."""
from .. import D,compile_strict_tape

def authored_tape(widget_id,*,pack_id):
    higher={'kind':'think_program_v1','surface_version':'v1','symbols':{},'puppeteering':{},'run':{'program':{'info':{'id':'template','title':'Typed authoring'},'widgets':{'consumer':{'widget':widget_id,'bindings':{'inputs':{'context':D.value('A literal $title')}}}},'flow':[{'id':'consume','widgets':['consumer']}]},'config':{}}}
    return compile_strict_tape(higher,{'app_pack_mould':{'app_pack':pack_id}})
