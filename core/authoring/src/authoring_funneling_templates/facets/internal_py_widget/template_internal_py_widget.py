"""Trusted package-maintainer template: keep behavior in a registered class."""
from authoring_funneling.a_typed_PSMCW_authoring import (
    Dict, StrictServiceWidget, analytica_signal_catcher, strict_widget,
)
from _thinkprogram.thinkwidgetTM.types import Reexplode


@strict_widget(
    'example.review_widget',
    args={'title': {'type': 'str', 'default': 'Review'}},
    inputs={},
    outputs={'result': Dict({'accepted': bool})},
)
class ReviewWidget(StrictServiceWidget):
    def _on_mount(self, position, fill_data, limits, stats):
        self.outputs.write_port('result', {'accepted': False})
        return Reexplode(next_fill_shell=self.replacement_shell(
            fill_data['fill_shell'], title=self.configuration['title'],
            micros=[{'name': 'decision', 'type': 'text'}]), pre_computed_fills={})

    def _on_fill(self, signal, position, fill_data, limits, stats):
        self.outputs.write_port('result', {'accepted': bool(fill_data['current_fills'].get('decision'))})
        return True

    @analytica_signal_catcher('reset')
    def reset(self, signal, position, fill_data, limits, stats):
        self.outputs.write_port('result', {'accepted': False})
        return Reexplode(next_fill_shell=self.replacement_shell(
            fill_data['fill_shell'], title=self.configuration['title'],
            micros=[{'name': 'decision', 'type': 'text'}]), pre_computed_fills={})
