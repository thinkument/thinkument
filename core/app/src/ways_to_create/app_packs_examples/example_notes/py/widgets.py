from __future__ import annotations

"""Small app-pack widget proving Python widget <-> JS renderer pairing.

The browser never receives HTML from this widget. It receives ordinary widget
semantics plus the tiny stable ``hai_renderer`` static arg. The selected app
pack resolves that renderer key to local JavaScript.
"""

from copy import deepcopy
from typing import Any, Mapping

from _thinkprogram.thinkwidgetTM.base import DatumLifecycleWidget
from _thinkprogram.thinkwidgetTM.decorators import thinkwidgetTM_config
from _thinkprogram.thinkwidgetTM.types import Reexplode


EXAMPLE_NOTE_WIDGET = "app_pack_mould.example_notes.note.v1"
EXAMPLE_NOTE_RENDERER = "example_notes.note.v1"


def _shell(prior: Mapping[str, Any]) -> dict[str, Any]:
    shell = deepcopy(dict(prior))
    shell["title"] = "Note"
    shell["micros"] = [
        {
            "name": "text",
            "type": "text",
            "required": True,
        }
    ]
    return shell


@thinkwidgetTM_config(
    EXAMPLE_NOTE_WIDGET,
    overwrite=True,
    enforce_no_premount_shell=True,
    args={
        "hai_renderer": {
            "type": "str",
            "required": False,
            "default": EXAMPLE_NOTE_RENDERER,
        },
        "title": {
            "type": "str",
            "required": False,
            "default": "Note",
        },
        "placeholder": {
            "type": "str",
            "required": False,
            "default": "Write a note",
        },
    },
    wires={},
)
class ExampleNoteWidget(DatumLifecycleWidget):
    def _on_mount(
        self,
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del position, limits, stats
        self.last_text = ""
        return Reexplode(
            next_fill_shell=_shell(fill_data["fill_shell"]),
            pre_computed_fills={},
        )

    def _on_fill(
        self,
        signal: Mapping[str, Any],
        position: Mapping[str, Any],
        fill_data: Mapping[str, Any],
        limits: Mapping[str, Any],
        stats: Mapping[str, Any],
    ) -> Any:
        del signal, position, limits, stats
        current = dict(fill_data.get("current_fills") or {})
        value = str(current.get("text") or "")
        self.last_text = value
        self._emit(
            {
                "message_type": "example_notes.saved",
                "text": value,
            },
            name="example_notes.saved",
        )
        self.message("success", "note saved")
        return True


__all__ = [
    "EXAMPLE_NOTE_RENDERER",
    "EXAMPLE_NOTE_WIDGET",
    "ExampleNoteWidget",
]
