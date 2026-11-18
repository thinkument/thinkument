"""Read the explicit named-function browser contract without importing a catalogue."""
from functools import lru_cache
import re
from .static_assets import STATIC_ROOT

@lru_cache(maxsize=None)
def browser_exports(module):
    # Named function exports are the small, explicit Python-to-JS linkage contract.
    return frozenset(re.findall(r'export function ([A-Za-z_][A-Za-z_0-9]*)\(', (STATIC_ROOT/module).read_text()))


