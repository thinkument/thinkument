"""Metal App Pack: 1-to-K Chromeset Petals over Base + Layer A + Layer B.

Funneling Architecture:
1. Base Specs (Layer 0 - Raw Kernel Substrate):
   - Inherits DatumLifecycleWidget lifecycle: _on_mount, _on_fill, @signal_catcher.
   - Executes under live I/O sessions (interactive step pauses, micro replacement)
     and headless black-box runs.
   - Maintains self._state and communicates via self._emit events.
2. Layer A Specs (Service-Tracked Computation):
   - Inherits ServiceReadyWidget: monotonic audit spans (audit-ins -> audit-outs/error),
     event indexing, and EconomicsWidgetMixin credit holds.
   - Storagics and financial integration ensure audit-grade traceability.
3. Layer B Specs (Typed PSMCW Authoring):
   - StrictServiceWidget: closed typed port contracts (PORT_INPUTS, PORT_OUTPUTS)
     defined via bindings2bindingsTM schemas.
   - Inbound wires evaluated into self.mouth; staged atomic writes to self.outputs.
   - Compile-time tape and graph verification via ChromedAuthoringProfile.

What Metal Builds On Top:
- 1-to-K Flower Petal Architecture: One shared widget library (shared_widgets/) blooms
  across K published chromesets (metal_standard, metal_compact, etc.).
- Card-Row Presentation: Widgets are arranged in card rows with explicit placement
  axes (vertical/horizontal) and standardized micro controls (integer, text, bool, button).
- Aesthetics Cascade: with_aesthetics engine compiling CSS rules, pseudo-classes,
  media queries, and CSS variables with validation against admitted micro targets.

Scaling Surface:
- Developers extend Metal by adding widgets to shared_widgets/, new micro controls
  to the shared rendering catalogue, or new chromesets to CHROMETABLES.
"""
from authoring_funneling.a_typed_PSMCW_authoring import (
    Bool,
    D,
    Dict,
    Float,
    Int,
    List,
    Map,
    Nullable,
    Str,
    analytica_signal_catcher,
)
from .shared_rendering.aesthetics import with_aesthetics
from .shared_widgets.base import LibraryWidget, strict_widget


def __getattr__(name):
    if name in ("ChromedAuthoringProfile", "DEFAULT_CHROME"):
        from . import publication
        return getattr(publication, name)
    raise AttributeError(name)


def compile_tape(P, SM=None, C=None, *, chrome=None):
    from .publication import ChromedAuthoringProfile, DEFAULT_CHROME, chrome_rows
    chrome = DEFAULT_CHROME if chrome is None else chrome
    if chrome not in chrome_rows():
        raise ValueError(f"Unknown chrome {chrome!r}.")
    profile = ChromedAuthoringProfile(chrome)
    return profile.compile({
        "profile_id": profile.profile_id,
        "W": sorted({w["widget"] for w in P["run"]["program"]["widgets"].values()}),
        "P": P,
        "SM": {} if SM is None else SM,
        "C": C,
    })


__all__ = [
    "with_aesthetics",
    "compile_tape",
    "LibraryWidget",
    "strict_widget",
    "analytica_signal_catcher",
    "D",
    "Str",
    "Int",
    "Float",
    "Bool",
    "Dict",
    "List",
    "Map",
    "Nullable",
    "DEFAULT_CHROME",
]
