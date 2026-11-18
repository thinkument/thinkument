"""Copy/adapt this declaration in your pack; importing it does not register it."""
from .. import strict_widget,StrictServiceWidget,Dict,Nullable
from _thinkprogram.thinkwidgetTM.types import Reexplode

def declare_widget(widget_id):
    @strict_widget(widget_id,inputs={'context':str},outputs={'result':Dict({'title':str,'note':Nullable(str)})})
    class Consumer(StrictServiceWidget):
        def _on_mount(self,position,fill_data,limits,stats):
            self.outputs.write_port('result',{'title':self.mouth.read('context'),'note':None})
            return Reexplode(next_fill_shell=self.replacement_shell(fill_data['fill_shell'],title=self.mouth.read('context'),micros=[{'name':'note','type':'text','required':True}]),pre_computed_fills={})
        def _on_fill(self,signal,position,fill_data,limits,stats):
            self.outputs.keep('result','title')
            self.outputs.write('result','note',fill_data['current_fills']['note'])
            return True
    return Consumer
