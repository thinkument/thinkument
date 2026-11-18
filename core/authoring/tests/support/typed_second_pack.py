"""Independent adoption fixture; imports templates without the teaching series."""
from authoring_funneling.a_typed_PSMCW_authoring import StrictServiceWidget,strict_widget,TypedAuthoringProfile,D,Dict
from _thinkprogram.thinkwidgetTM.types import Reexplode

WIDGET_ID='typed_second.echo.v1'
PROFILE_ID='typed_second.typed_ports.v1'

@strict_widget(WIDGET_ID,overwrite=True,inputs={'message':str},outputs={'result':Dict({'message':str})})
class Echo(StrictServiceWidget):
    def _on_mount(self,position,fill_data,limits,stats):
        self.outputs.write('result','message',self.mouth.read('message'))
        return Reexplode(next_fill_shell=self.replacement_shell(fill_data['fill_shell'],title=self.mouth.read('message'),micros=[{'name':'ack','type':'text','required':True}]),pre_computed_fills={})
    def _on_fill(self,signal,position,fill_data,limits,stats):
        self.outputs.keep_port('result');return True

def profile(): return TypedAuthoringProfile('second_pack',profile_id=PROFILE_ID,widget_ids=[WIDGET_ID])
def draft():
    return {'profile_id':PROFILE_ID,'W':[WIDGET_ID],'P':{'kind':'think_program_v1','surface_version':'v1','symbols':{},'puppeteering':{},'run':{'program':{'info':{'id':'second_echo','title':'Independent'},'widgets':{'echo':{'widget':WIDGET_ID,'bindings':{'inputs':{'message':D.value('Independent $pack')}}}},'flow':[{'id':'echo','widgets':['echo']}]},'config':{}}},'SM':{},'C':None}
