"""Closed typed outputs and explicit nullable channels on every transition."""
from ._shared import *
HIGHER_P=program(1,{'writer':seed(),'reader':consumer()},[step('write','writer'),step('read','reader')])
TAPE=export(HIGHER_P)
PROGRAM,SESSION_METADATA,PUPPET=TAPE['P'],TAPE['SM'],TAPE['C']
