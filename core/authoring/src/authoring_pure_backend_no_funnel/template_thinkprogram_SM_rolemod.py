from __future__ import annotations

"""Copy/paste template: role-modulated read/write session metadata.

Widget/span role assignments live in P. This SM declares the role vocabulary,
read adjacency, and mismatch projection mode for the one canonical session.
"""

from typing import Any, Dict


ROLE_MAKER: str = "maker"
ROLE_REVIEWER: str = "reviewer"
ROLE_AUDITOR: str = "auditor"


SESSION_METADATA_ROLEMOD: Dict[str, Any] = {
    "roles": {
        ROLE_MAKER: {
            "label": "Maker",
            "read_roles": [],
        },
        ROLE_REVIEWER: {
            "label": "Reviewer",
            # Visibility only. This does NOT grant reviewer write power to maker data.
            "read_roles": [ROLE_MAKER],
        },
        ROLE_AUDITOR: {
            "label": "Auditor",
            "read_roles": [],
        },
    },
    "role_mismatch_policy": {
        "default": "redacted",
        "role_modes": {
            ROLE_MAKER: "redacted",
            ROLE_REVIEWER: "redacted",
            ROLE_AUDITOR: (
                "redacted-w-identity-ownership-activity-receipt"
            ),
        },
    },
}


# Runtime law:
#   write(r,d) iff R(d)==[] or r in R(d)
#   read(r,d)  iff R(d)==[] or R(d) intersects ({r} union read_roles[r])


__all__ = [
    "ROLE_AUDITOR",
    "ROLE_MAKER",
    "ROLE_REVIEWER",
    "SESSION_METADATA_ROLEMOD",
]
