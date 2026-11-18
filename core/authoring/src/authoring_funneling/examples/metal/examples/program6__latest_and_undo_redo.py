"""Latest earlier/self-previous outputs across ordinary continuity actions."""
from ._shared import *
HIGHER_P=program(6,{'counter':counter(D.value(1))},[step('first','counter'),step('second','counter',overrides={'bindings':{'counter':{'sources':{'previous':{'widget':{'self':'previous'},'port':'result'}},'inputs':{'start':D.ref('previous','count')}}}})])
TAPE=export(HIGHER_P)
PROGRAM,SESSION_METADATA,PUPPET=TAPE['P'],TAPE['SM'],TAPE['C']
