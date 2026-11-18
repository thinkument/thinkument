from __future__ import annotations

"""
Session args policy surface
===========================
For pedagogy, see tests/integration/complexity/

Policy normalization helpers for canonical session metadata.

This module owns:
  - manual IO policy sanitation
  - durable/live session storage policy sanitation

These helpers intentionally return dead JSON-compatible dictionaries.
"""

from typing import Any, Dict, Mapping


def sanitize_manual_io_policy(raw: Any | None) -> Dict[str, Any]:
    manual_io = dict(raw or {}) if isinstance(raw, Mapping) else {}

    persistence = str(manual_io.get("persistence") or "boundary").strip().lower()
    if persistence not in {"eager", "boundary", "disabled"}:
        persistence = "boundary"

    def _bool(key: str, default: bool) -> bool:
        return bool(manual_io.get(key, default))

    def _cap_int(key: str, default: int) -> int:
        raw_v = manual_io.get(key, default)
        if raw_v is None:
            return 0
        try:
            iv = int(raw_v)
        except Exception:
            iv = int(default)
        return max(0, iv)

    return {
        "persistence": persistence,
        "profile": _bool("profile", False),
        "include_full_multiframespec_in_ctx": _bool(
            "include_full_multiframespec_in_ctx",
            True,
        ),
        "include_global_fill_keys_in_ctx": _bool(
            "include_global_fill_keys_in_ctx",
            False,
        ),
        "include_field_value_keys_in_ctx": _bool(
            "include_field_value_keys_in_ctx",
            False,
        ),
        "include_forms_emitted_order_in_ctx": _bool(
            "include_forms_emitted_order_in_ctx",
            True,
        ),
        "max_fields_per_submit": _cap_int("max_fields_per_submit", 1024),
        "max_payload_chars": _cap_int("max_payload_chars", 2_000_000),
    }


def sanitize_session_storage_policy(raw: Any | None) -> Dict[str, Any]:
    """
    Durable/live session-weight policy.

    These knobs are intentionally about shedding duplicate data, not about
    compressing and re-inflating payloads.
    """
    storage = dict(raw or {}) if isinstance(raw, Mapping) else {}

    def _cap_int(key: str, default: int) -> int:
        raw_v = storage.get(key, default)
        if raw_v is None:
            return 0
        try:
            iv = int(raw_v)
        except Exception:
            iv = int(default)
        return max(0, iv)

    return {
        # Number of most-recent canonical source events retained durably.
        # 0 disables queue retention while callback delivery remains live.
        "events_snapshot_window": _cap_int(
            "events_snapshot_window",
            16,
        ),
        # Number of most-recent emitted multiframespecs to keep in durable snapshots.
        # 0 means keep only the currently pending form if needed.
        "forms_emitted_snapshot_window": _cap_int(
            "forms_emitted_snapshot_window",
            16,
        ),
        # Redo stack is useful, but should never become an unbounded value log.
        "redo_max_depth": _cap_int(
            "redo_max_depth", 
            16,
        ),

        "redo_action_max_payload_chars": _cap_int(
            "redo_action_max_payload_chars",
            200_000,
        ),
    }


__all__ = [
    "sanitize_manual_io_policy",
    "sanitize_session_storage_policy",
]