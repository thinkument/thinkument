"""Multi-source text, field projections, lists, records and nested map composition."""
from ._shared import *
reader=consumer(heading=D.text(D.ref('draft','title'),' / ',D.ref('review','title'),' $literal'))
reader['bindings']['sources']['review']={'widget':'reviewer','port':'result'}
reader['bindings']['inputs']['context']['fields']['items']=D.list(D.dict({'label':D.text('Entry: ',D.ref('draft','title')),'count':D.ref('draft','count')}))
HIGHER_P=program(2,{'writer':seed('Draft',2),'reviewer':seed('Review',3),'reader':reader},[step('write','writer','reviewer'),step('read','reader')])
TAPE=export(HIGHER_P)
PROGRAM,SESSION_METADATA,PUPPET=TAPE['P'],TAPE['SM'],TAPE['C']
