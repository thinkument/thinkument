from __future__ import annotations

from typing import Any, Dict

from _thinksessions.sesh_metadata.__sesh_meta_dynamic_augmentation_by_apps import (
    SessionMetadataSurfaceRegistry,
)


FUNKT_M_CONFIG_KEY = "chainreactionTM_config"


FUNKT_M_SESSION_METADATA_POCKET_SCHEMA: Dict[str, Any] = {
    "kind": "session_metadata_pocket_schema_v1",
    "label": "chainreactionTM chain reaction config",
    "description": (
        "Global functional-fill chain-reaction policy. Per-role chainreaction configs "
        "live under session_metadata.roles[role].chainreactionTM_config."
    ),
    "allow_none": True,
    "fields": {
        "version": {
            "type": "string",
            "required": True,
            "default": "chainreaction1.0",
        },
        "roles_ordered": {
            "type": "array",
            "required": True,
            "items": {"type": "any"},
        },
        "expect_all_roles_chainreactioned": {
            "type": "boolean",
            "default": False,
        },
        "on_semantic_error": {
            "type": "string",
            "enum": ["retry_w_error_awareness", "raise"],
            "default": "retry_w_error_awareness",
        },
        "max_semantic_errors_in_a_row": {
            "type": "integer",
            "default": 2,
        },
        "max_fills_on_a_span": {
            "type": "integer",
            "default": 8,
        },
        "max_fills_e2e": {
            "type": "integer",
            "default": 64,
        },
        "history_tail_cap": {
            "type": "integer",
            "default": 4,
        },
        "history_size_cap": {
            "type": "integer",
            "default": 25000,
        },
        "events_queue_length": {
            "type": "integer",
            "default": 0,
        },
    },
    "additional_keys": False,
    "laws": [
        "None disables chainreactionTM._",
        "roles_ordered must flatten to exactly the session metadata role names.",
        "Each session role row must contain chainreactionTM_config, either None or a registered version config.",
        "Per-role chainreaction configs are declarative JSON-safe data.",
        "Global version currently supports chainreaction1.0 and is intentionally version-gated.",
        "events_queue_length=0 preserves legacy requests; positive values pass the latest role-projected event tail to FunkTMRequest.events.",
    ],
}


def register_chainreactiontm_session_metadata_pocket(
    *,
    replace: bool = False,
) -> Dict[str, Any]:
    return SessionMetadataSurfaceRegistry.register_pocket(
        key=FUNKT_M_CONFIG_KEY,
        schema=FUNKT_M_SESSION_METADATA_POCKET_SCHEMA,
        replace=replace,
    )