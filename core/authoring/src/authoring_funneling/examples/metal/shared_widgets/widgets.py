"""Shared Metal widgets; reused directly by other families."""
from authoring_funneling.a_typed_PSMCW_authoring import Dict, List, Nullable, analytica_signal_catcher
from _thinkprogram.thinkwidgetTM.types import Reexplode
from .base import LibraryWidget, strict_widget

SEED='metal.seed'
CONSUMER='metal.consumer'
COUNTER='metal.counter'

@strict_widget(SEED,args={'title':{'type':'str','default':'Draft'},'count':{'type':'int','default':1}},inputs={},outputs={'result':Dict({'title':str,'count':int,'note':Nullable(str)}),'entries':Dict({'rows':List(Dict({'title':str,'count':int}))})})
class Seed(LibraryWidget):
    def _on_mount(self,position,fill_data,limits,stats):
        title=self.configuration.get('title','Draft');count=self.configuration.get('count',1)
        self.outputs.write_many({'result':{'title':title,'count':count,'note':None},'entries':{'rows':[{'title':title,'count':count}]}})
        return Reexplode(next_fill_shell=self.replacement_shell(fill_data['fill_shell'],title=title,micros=[{'name':'confirm','type':'text','required':True}]),pre_computed_fills={})
    def _on_fill(self,signal,position,fill_data,limits,stats):
        self.outputs.keep_port('result');self.outputs.keep_port('entries');return True

@strict_widget(CONSUMER,inputs={'context':Dict({'heading':str,'items':List(Dict({'label':str,'count':int})),'note':Nullable(str)})},outputs={'result':Dict({'heading':str,'items':List(Dict({'label':str,'count':int})),'note':Nullable(str)})})
class Consumer(LibraryWidget):
    def _on_mount(self,position,fill_data,limits,stats):
        context=self.mouth.read('context')
        self.outputs.write_port('result',context)
        return Reexplode(next_fill_shell=self.replacement_shell(fill_data['fill_shell'],title=context['heading'],micros=[{'name':'ack','type':'text','required':True}]),pre_computed_fills={})
    def _on_fill(self,signal,position,fill_data,limits,stats):
        self.outputs.keep_port('result');return True

@strict_widget(COUNTER,args={'fail':{'type':'bool','default':False}},inputs={'start':int},outputs={'result':Dict({'count':int,'note':Nullable(str)})})
class Counter(LibraryWidget):
    def _shell(self,fill_data, count):
        return self.replacement_shell(fill_data['fill_shell'],title='Count '+str(count),micros=[{'name':'finish','type':'text','required':True}])
    def _on_mount(self,position,fill_data,limits,stats):
        self.outputs.write_port('result',{'count':self.mouth.read('start'),'note':None})
        return Reexplode(next_fill_shell=self.replacement_shell(fill_data['fill_shell'],title='Typed counter',micros=[{'name':'finish','type':'text','required':True}]),pre_computed_fills={})
    def _on_fill(self,signal,position,fill_data,limits,stats):
        self.outputs.keep('result','count');self.outputs.write('result','note',str(fill_data['current_fills']['finish']))
        if self.configuration.get('fail'): raise ValueError('deliberate audited failure')
        return True
    @analytica_signal_catcher('increment')
    def increment(self,signal,position,fill_data,limits,stats):
        count=self.outputs.read('result','count')+1
        self.outputs.write('result','count',count)
        self.outputs.keep('result','note')
        return Reexplode(next_fill_shell=self._shell(fill_data,count),pre_computed_fills={})

BOUNDED='metal.bounded'

@strict_widget(BOUNDED, inputs={'start':int}, outputs={'result':Dict({'value':int,'revision':int})})
class Bounded(LibraryWidget):
    def _shell(self, fill_data, revision):
        return self.replacement_shell(fill_data['fill_shell'], title='Bounded value', micros=[{
            'name':'value','type':'creativity_bounded_integer','required':True,
            'label':f'Value (revision {revision})','minimum':0,'maximum':100,
            'render_args':{'revision':revision,'hints':['0 through 100']},
        }])
    def _on_mount(self, position, fill_data, limits, stats):
        from .micros import bounded_integer
        value = bounded_integer(self.mouth.read('start'))
        self.outputs.write_port('result',{'value':value,'revision':0})
        return Reexplode(next_fill_shell=self._shell(fill_data,0),pre_computed_fills={'value':value})
    @analytica_signal_catcher('refresh')
    def refresh(self, signal, position, fill_data, limits, stats):
        self.outputs.keep('result','value')
        revision=self.outputs.read('result','revision')+1
        self.outputs.write('result','revision',revision)
        return Reexplode(next_fill_shell=self._shell(fill_data,revision),pre_computed_fills={})
    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.outputs.write('result','value',fill_data['current_fills']['value'])
        self.outputs.keep('result','revision')
        return True



from pathlib import Path
from authoring_funneling import JsonDefinedLibraryWidget, prepare_json_widget_v1, register_prepared_json_widget_v1

class JsonLibraryWidget(JsonDefinedLibraryWidget, LibraryWidget):
    """Retain Metal shell admission around the JSON lifecycle."""

METAL_JSON_WIDGET_ARTIFACT_V1 = prepare_json_widget_v1(
    Path(__file__).with_name("json_widgets").joinpath("metal_ideator.json").read_text(),
    base=JsonLibraryWidget)
register_prepared_json_widget_v1(METAL_JSON_WIDGET_ARTIFACT_V1)
