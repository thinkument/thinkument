"""Audited signals, repeated explosions and explicit carry-forward."""
from ._shared import *
HIGHER_P=program(3,{'counter':counter(D.value(4))},[step('count','counter')])
TAPE=export(HIGHER_P)
PROGRAM,SESSION_METADATA,PUPPET=TAPE['P'],TAPE['SM'],TAPE['C']
