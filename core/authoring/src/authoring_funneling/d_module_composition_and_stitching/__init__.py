from __future__ import annotations

"""
authoring_funneling.d_module_composition_and_stitching
======================================================
First-class module composition, (P x C) publishing, and hermetic flow stitching.
"""

from .manifest import (
    LANG_THINK_MODULE_V1,
    compute_module_fingerprint,
    normalize_think_module_v1,
    validate_think_module_v1,
)
from .registry import (
    ModuleCatalogRegistry,
    parse_module_reference,
)
from .stitching_registry import (
    SMPocketStitchingPolicy,
    SMPocketStitchingRegistry,
)
from .stitcher import (
    MAX_IMPORT_DEPTH,
    stitch_program_modules,
)

__all__ = [
    "LANG_THINK_MODULE_V1",
    "MAX_IMPORT_DEPTH",
    "ModuleCatalogRegistry",
    "SMPocketStitchingPolicy",
    "SMPocketStitchingRegistry",
    "compute_module_fingerprint",
    "normalize_think_module_v1",
    "parse_module_reference",
    "stitch_program_modules",
    "validate_think_module_v1",
]
