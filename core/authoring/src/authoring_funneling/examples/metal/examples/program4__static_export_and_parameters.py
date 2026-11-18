"""Ordinary C parameters and whole-expression appearance overrides."""
from ._shared import *
reader=consumer(heading=D.text(D.ref('parameters','label'),': ',D.ref('draft','title')))
reader['bindings']['parameters']={'label':{'type':str,'value':'$ui.label'}}
HIGHER_P=program(4,{'writer':seed(),'reader':reader},[step('write','writer'),step('read','reader'),step('read_again','reader',overrides={'bindings':{'reader':{'inputs':{'context':D.dict({'heading':D.text('Again ',D.ref('parameters','label')),'items':D.list(),'note':D.value(None)})}}}})],symbols={'ui.label':{'value':'Default','parametrize':True}})
PUPPET={'ui.label':'Published'}
TAPE=export(HIGHER_P,PUPPET)
PROGRAM,SESSION_METADATA=TAPE['P'],TAPE['SM']
