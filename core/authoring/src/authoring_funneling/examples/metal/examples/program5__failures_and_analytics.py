"""A deliberate rejected fill leaves previously accepted outputs intact."""
from ._shared import *
HIGHER_P=program(5,{'counter':counter(D.value(5),fail=True)},[step('reject','counter'),step('recover','counter',overrides={'args':{'counter':{'fail':False}}})])
# The first appearance demonstrates atomic failure; an increment signal remains
# valid. The completion tape replaces the configuration before launch.
FAILURE_TAPE=export(HIGHER_P)
COMPLETION_HIGHER_P=deepcopy(HIGHER_P)
COMPLETION_HIGHER_P['run']['program']['flow'][0].setdefault('overrides',{})['args']={'counter':{'fail':False}}
TAPE=export(COMPLETION_HIGHER_P)
PROGRAM,SESSION_METADATA,PUPPET=TAPE['P'],TAPE['SM'],TAPE['C']
