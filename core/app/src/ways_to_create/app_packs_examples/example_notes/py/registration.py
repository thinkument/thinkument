from __future__ import annotations

"""Runtime registration owned by the bundled ``example_notes`` pile."""

from typing import Any


def register_app_pack_v1() -> dict[str, Any]:
    from .widgets import EXAMPLE_NOTE_WIDGET

    return {
        "kind": "app_pack_mould_app_pack_registration_receipt_v1",
        "app_pack": "example_notes",
        "widgets": [EXAMPLE_NOTE_WIDGET],
        "funk_fillers": [],
    }


__all__ = ["register_app_pack_v1"]
