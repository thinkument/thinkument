from __future__ import annotations

"""Pure backend-compliant PSMC authoring primitives.

These templates produce compliant ThinkSessions and Programs that execute directly
against think-backend's engine without depending on service or UI host machinery.
"""

from .template_thinkprogram import (
    PROGRAM,
    WIDGETS,
)
from .template_thinkprogram_SM_app_packs import (
    with_app_pack,
    APP_PACK_SESSION_METADATA_KEY,
)

__all__ = [
    "PROGRAM",
    "WIDGETS",
    "with_app_pack",
    "APP_PACK_SESSION_METADATA_KEY",
]
