"""One strict Python/widget-mechanics sheet shared by every chrome."""
from authoring_funneling.a_typed_PSMCW_authoring import StrictServiceWidget,strict_widget as declare_strict_widget,analytica_signal_catcher,Dict,List,Nullable
from _thinkprogram.thinkwidgetTM.types import Reexplode

def strict_widget(name, *, args=None, **config):
    args = dict(args or {})
    if 'hai_renderer' in args:
        raise ValueError('Library renderer selection belongs to the widget sheet.')
    args['hai_renderer'] = {'type':'str','default':name}
    return declare_strict_widget(name, args=args, **config)


class LibraryWidget(StrictServiceWidget):
    @staticmethod
    def replacement_shell(prior, *, title, micros, micro_placement=None):
        shell = StrictServiceWidget.replacement_shell(prior,title=title,micros=micros)
        if micro_placement is not None:
            from ..shared_rendering.aesthetics import MICRO_PLACEMENT_KEY
            shell[MICRO_PLACEMENT_KEY] = micro_placement
        return shell

    def _run_analytica_operation_v1(self, *, trigger, fill_data, signal, invoke):
        from .micros import validate_shell
        def checked():
            result = invoke()
            if isinstance(result, Reexplode):
                validate_shell(result.next_fill_shell)
            return result
        return super()._run_analytica_operation_v1(
            trigger=trigger, fill_data=fill_data, signal=signal, invoke=checked)


