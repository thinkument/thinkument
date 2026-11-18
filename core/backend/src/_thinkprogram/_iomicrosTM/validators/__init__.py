from __future__ import annotations

"""Built-in semantic validators.

Importing this package registers the complete built-in leaf validator surface.
Datum-level cross-field validators live in ``validators.datum`` and are public,
but intentionally are not leaf-registered.
"""

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator

from . import boolean  # noqa: F401
from . import choice  # noqa: F401
from . import code  # noqa: F401
from . import collection  # noqa: F401
from . import date  # noqa: F401
from . import datum  # noqa: F401
from . import email  # noqa: F401
from . import file  # noqa: F401
from . import image  # noqa: F401
from . import latex_math  # noqa: F401
from . import number  # noqa: F401
from . import object_json  # noqa: F401
from . import text  # noqa: F401
from . import url  # noqa: F401

__all__ = ["validator", "guidance_for"]
