from __future__ import annotations

"""Copy/paste template: system/session runtime bounds.

These knobs bound transport/context/storage cost. They do not change
ThinkWidget domain semantics or ThinkProgram topology.
"""

from typing import Any, Dict


SESSION_METADATA_SYSTEM: Dict[str, Any] = {
    "manual_io": {
        "persistence": "boundary",  # "eager" | "boundary" | "disabled"
        "profile": False,
        "include_full_multiframespec_in_ctx": True,
        "include_global_fill_keys_in_ctx": False,
        "include_field_value_keys_in_ctx": False,
        "include_forms_emitted_order_in_ctx": True,
        "max_fields_per_submit": 1024,
        "max_payload_chars": 2_000_000,
    },
    "session_storage": {
        "events_snapshot_window": 64,
        "forms_emitted_snapshot_window": 16,
        "redo_max_depth": 8,
        "redo_action_max_payload_chars": 20_000,
    },
}


__all__ = ["SESSION_METADATA_SYSTEM"]
