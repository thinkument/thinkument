from __future__ import annotations

"""Copy/paste template: launch-time ThinkProgram puppeteering C.

Frontend readiness adds no new puppeteering grammar. C only assigns values to
symbols already declared by P; it never changes program topology.
"""

from typing import Any, Dict

from _thinkprogram.thinkprogramTM.api import (
    PUPPETEERING_OVERLAY_KEY_V1,
    PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
    PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
)


# Everyday default: override only the symbols named here and preserve authored
# puppeteering for everything else.
PUPPET: Dict[str, Any] = {
    PUPPETEERING_OVERLAY_KEY_V1: {
        "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
        "strict": True,
    },
    "app.backend_policy": {"mode": "strict"},
    "ui.variant": "compact",
}


# Use only when launch configuration should replace the entire authored
# puppeteering pocket. Unmentioned symbols then fall back according to P's
# symbol semantics.
PUPPET_TAKE_OVER: Dict[str, Any] = {
    PUPPETEERING_OVERLAY_KEY_V1: {
        "mode": PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
        "strict": True,
    },
    "app.backend_policy": {"mode": "strict"},
}


__all__ = ["PUPPET", "PUPPET_TAKE_OVER"]
