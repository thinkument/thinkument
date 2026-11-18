from __future__ import annotations

"""
Program session-metadata surface.

This is the highest authored-session metadata declaration. It composes the
engine-owned SessionArgs surface with the chainreactionTM app pocket and gives
future authoring layers one explicit pattern for registering additional
top-level metadata pockets.
"""

from typing import Any, Dict, Mapping

from _thinkprogram._iomicrosTM.tiny_helpers import assert_dead_json
from _thinksessions.sesh_metadata.__sesh_meta_dynamic_augmentation_by_apps import (
    SessionMetadataSurfaceRegistry,
)
from _thinksessions.sesh_metadata.sesh_metadata_surface import (
    coerce_session_metadata,
    session_args_metadata_surface_sheet_v1,
)
from _thinksessions.sesh_metadata.__sesh_meta_chainreactionTM_config_surface import (
    FUNKT_M_CONFIG_KEY,
    register_chainreactiontm_session_metadata_pocket,
)


PROGRAM_DEMO_POCKET_KEY = "thinkument_app_demo"


PROGRAM_DEMO_POCKET_SCHEMA: Dict[str, Any] = {
    "kind": "session_metadata_pocket_schema_v1",
    "label": "Thinkument app demo metadata",
    "description": (
        "Inert app-owned metadata used by the E2E sheet."
    ),
    "allow_none": False,
    "fields": {
        "scenario": {
            "type": "string",
            "required": True,
        },
        "surface_version": {
            "type": "string",
            "required": True,
            "default": "v1",
        },
        "app_args": {
            "type": "object",
            "required": True,
            "additional_keys": True,
        },
    },
    "additional_keys": False,
    "laws": [
        "This pocket is dead JSON only.",
        "Executable behavior is registered by version name elsewhere.",
        "App-owned metadata never changes the engine-owned core key set.",
    ],
}


def register_program_sesh_metadata_pockets_v1(
    *,
    replace: bool = True,
) -> Dict[str, Any]:
    """Register every app-owned pocket required by the demo/test surface."""
    chain = register_chainreactiontm_session_metadata_pocket(
        replace=replace,
    )
    demo = SessionMetadataSurfaceRegistry.register_pocket(
        key=PROGRAM_DEMO_POCKET_KEY,
        schema=PROGRAM_DEMO_POCKET_SCHEMA,
        replace=replace,
    )
    return {
        "kind": "program_sesh_metadata_registration_receipt_v1",
        "registered": {
            FUNKT_M_CONFIG_KEY: chain,
            PROGRAM_DEMO_POCKET_KEY: demo,
        },
    }


def program_sesh_metadata_surface_v1() -> Dict[str, Any]:
    register_program_sesh_metadata_pockets_v1(replace=True)
    out = {
        "kind": "program_sesh_metadata_surface_v1",
        "v": 1,
        "base": session_args_metadata_surface_sheet_v1(),
        "required_demo_pockets": [
            FUNKT_M_CONFIG_KEY,
            PROGRAM_DEMO_POCKET_KEY,
        ],
        "augmentation_protocol": {
            "register": (
                "SessionMetadataSurfaceRegistry.register_pocket("
                "key=..., schema=..., replace=...)"
            ),
            "schema_kind": "session_metadata_pocket_schema_v1",
            "behavior": (
                "Schemas and values are inert dead JSON. Runtime behavior is "
                "selected by registered version names stored in metadata."
            ),
        },
        "laws": [
            "roles and role_mismatch_policy remain engine-owned core keys.",
            "manual_io and session_storage remain engine-owned core keys.",
            "chainreactionTM_config is an app-owned registered pocket.",
            "Per-role chainreactionTM_config lives under roles[role].",
            (
                "chainreactionTM_config.events_queue_length controls "
                "FunkTMRequest.events and defaults to 0."
            ),
            "Unknown full-create metadata stays pass-through for backcompat.",
            "Partial updates accept only core keys and registered pockets.",
            (
                "Highest-façade dispatches may provide "
                "my_current_event_seq_number for O(|T|) optimistic "
                "staleness prevention."
            ),
            (
                "The canonical session event queue remains the sole event "
                "sequence authority; the staleness layer never assigns "
                "event_seq."
            ),
            (
                "Cross-process dispatch serialization requires the hosting "
                "service to provide one distributed per-session write "
                "boundary."
            ),
            (
                "Process restart or session migration additionally requires "
                "the hosting service to preserve the scope/target last-changed "
                "index atomically with session mutation."
            ),
        ],
    }
    assert_dead_json(out, path="program_sesh_metadata_surface_v1")
    return out


def build_demo_program_sesh_metadata_v1(
    *,
    chainreaction_enabled: bool = True,
    maker_funk_version: str = "demo.semantic_shell_funk.v1",
    reviewer_funk_version: str | None = None,
    release_funk_version: str = "demo.semantic_shell_funk.v1",
    events_queue_length: int = 0,
) -> Dict[str, Any]:
    register_program_sesh_metadata_pockets_v1(replace=True)

    meta: Dict[str, Any] = {
        "roles": {
            "maker": {
                "label": "Maker",
                "read_roles": [],
                "chainreactionTM_config": (
                    {
                        "version": maker_funk_version,
                        "args": {},
                    }
                    if maker_funk_version
                    else None
                ),
            },
            "reviewer": {
                "label": "Reviewer",
                "read_roles": ["maker"],
                "chainreactionTM_config": (
                    {
                        "version": reviewer_funk_version,
                        "args": {},
                    }
                    if reviewer_funk_version
                    else None
                ),
            },
            "release_ai": {
                "label": "Release AI",
                "read_roles": ["maker", "reviewer"],
                "chainreactionTM_config": (
                    {
                        "version": release_funk_version,
                        "args": {},
                    }
                    if release_funk_version
                    else None
                ),
            },
            "auditor": {
                "label": "Auditor",
                "read_roles": [],
                "chainreactionTM_config": None,
            },
        },
        "role_mismatch_policy": {
            "default": "redacted",
            "role_modes": {
                "maker": "redacted",
                "reviewer": "redacted",
                "release_ai": "redacted",
                "auditor": "redacted",
            },
        },
        "manual_io": {
            "persistence": "disabled",
            "include_forms_emitted_order_in_ctx": True,
        },
        "session_storage": {
            "forms_emitted_snapshot_window": 32,
            "redo_max_depth": 64,
            "redo_action_max_payload_chars": 200_000,
        },
        PROGRAM_DEMO_POCKET_KEY: {
            "scenario": "app_demo_pocket",
            "surface_version": "v1",
            "app_args": {
                "downstream": "pythonic-role-viewers",
                "purpose": "e2e-surface-proof",
            },
        },
    }

    meta[FUNKT_M_CONFIG_KEY] = (
        {
            "version": "chainreaction1.0",
            "roles_ordered": [
                "maker",
                "reviewer",
                "release_ai",
                "auditor",
            ],
            "expect_all_roles_chainreactioned": False,
            "on_semantic_error": "retry_w_error_awareness",
            "max_semantic_errors_in_a_row": 2,
            "max_fills_on_a_span": 12,
            "max_fills_e2e": 32,
            "history_tail_cap": 4,
            "history_size_cap": 25_000,
            "events_queue_length": int(events_queue_length),
        }
        if chainreaction_enabled
        else None
    )

    return coerce_session_metadata(meta)


__all__ = [
    "PROGRAM_DEMO_POCKET_KEY",
    "PROGRAM_DEMO_POCKET_SCHEMA",
    "build_demo_program_sesh_metadata_v1",
    "program_sesh_metadata_surface_v1",
    "register_program_sesh_metadata_pockets_v1",
]