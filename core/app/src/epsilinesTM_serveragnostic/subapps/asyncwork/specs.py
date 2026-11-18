from __future__ import annotations

"""Payload validators and channel specifications for the `asyncwork` subapp."""

from copy import deepcopy
from typing import Any, Dict, Mapping

from _thinkprogram._iomicrosTM.tiny_helpers import assert_dead_json

from ...core.registry import (
    EpsChannelSpecV1,
    EpsRegistryError,
    MODE_PERSISTENCE,
    RETENTION_DURABLE,
    RETENTION_TTL,
    VISIBILITY_OWNER_ONLY,
)
from .channels import (
    ALLOWED_OUTCOMES,
    ASYNCWORK_ANNOUNCE_CHANNEL,
    ASYNCWORK_ANNOUNCE_SCHEMA_V1,
    ASYNCWORK_APP,
    ASYNCWORK_DONE_CHANNEL,
    ASYNCWORK_DONE_SCHEMA_V1,
    ASYNCWORK_PROGRESS_CHANNEL,
    ASYNCWORK_PROGRESS_SCHEMA_V1,
    ASYNCWORK_PROGRESS_STATUSES,
    STATUS_IN_PROGRESS,
)


def validate_asyncwork_announce_payload_v1(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and normalize payload for `asyncwork.announce`."""
    if not isinstance(payload, Mapping):
        raise EpsRegistryError("asyncwork.announce payload must be a dict / mapping")
    raw = deepcopy(dict(payload))
    assert_dead_json(raw, path=f"eps[{ASYNCWORK_ANNOUNCE_CHANNEL}]")

    target = str(raw.get("target") or "").strip()
    if not target:
        raise EpsRegistryError("asyncwork.announce target string is required")
    raw["target"] = target

    kwargs = raw.get("kwargs")
    if kwargs is not None:
        if not isinstance(kwargs, Mapping):
            raise EpsRegistryError("asyncwork.announce 'kwargs' must be a mapping if provided")
        raw["kwargs"] = dict(kwargs)
    else:
        raw["kwargs"] = {}

    timeout_seconds = raw.get("timeout_seconds")
    if timeout_seconds is not None:
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise EpsRegistryError("asyncwork.announce timeout_seconds must be positive")
        raw["timeout_seconds"] = float(timeout_seconds)
    else:
        raw["timeout_seconds"] = None

    max_retries = raw.get("max_retries")
    if max_retries is not None:
        if not isinstance(max_retries, int) or max_retries < 0:
            raise EpsRegistryError("asyncwork.announce 'max_retries' must be a non-negative integer")
        raw["max_retries"] = int(max_retries)
    else:
        raw["max_retries"] = None

    priority = raw.get("priority")
    if priority is not None:
        raw["priority"] = int(priority)
    else:
        raw["priority"] = None

    return raw


def validate_asyncwork_progress_payload_v1(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and normalize payload for `asyncwork.progress`."""
    if not isinstance(payload, Mapping):
        raise EpsRegistryError("asyncwork.progress payload must be a dict / mapping")
    raw = deepcopy(dict(payload))
    assert_dead_json(raw, path=f"eps[{ASYNCWORK_PROGRESS_CHANNEL}]")

    target = str(raw.get("target") or "").strip()
    if not target:
        raise EpsRegistryError("asyncwork.progress target string is required")
    raw["target"] = target

    percent = raw.get("percent")
    if percent is None:
        percent = raw.get("pct")
    if percent is not None:
        if not isinstance(percent, (int, float)) or percent < 0.0 or percent > 100.0:
            raise EpsRegistryError("asyncwork.progress percent must be between 0 and 100")
        raw["percent"] = float(percent)
    else:
        raw["percent"] = None

    status = raw.get("status")
    if status is not None:
        status = str(status).strip()
        if status not in ASYNCWORK_PROGRESS_STATUSES:
            raise EpsRegistryError(
                f"asyncwork.progress status must be one of {sorted(ASYNCWORK_PROGRESS_STATUSES)}, got {status!r}"
            )
        raw["status"] = status
    else:
        raw["status"] = STATUS_IN_PROGRESS

    raw.setdefault("step_name", None)
    raw.setdefault("step_index", None)
    raw.setdefault("total_steps", None)
    raw.setdefault("details", {})

    return raw


def validate_asyncwork_done_payload_v1(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and normalize payload for `asyncwork.done`."""
    if not isinstance(payload, Mapping):
        raise EpsRegistryError("asyncwork.done payload must be a dict / mapping")
    raw = deepcopy(dict(payload))
    assert_dead_json(raw, path=f"eps[{ASYNCWORK_DONE_CHANNEL}]")

    target = str(raw.get("target") or "").strip()
    if not target:
        raise EpsRegistryError("asyncwork.done target string is required")
    raw["target"] = target

    outcome = str(raw.get("outcome") or "").strip()
    if outcome not in ALLOWED_OUTCOMES:
        raise EpsRegistryError(
            f"asyncwork.done outcome must be one of {sorted(ALLOWED_OUTCOMES)}, got {outcome!r}"
        )
    raw["outcome"] = outcome

    duration_ms = raw.get("duration_ms")
    if duration_ms is not None:
        if not isinstance(duration_ms, (int, float)) or duration_ms < 0:
            raise EpsRegistryError("asyncwork.done duration_ms must be non-negative")
        raw["duration_ms"] = float(duration_ms)
    else:
        raw["duration_ms"] = None

    raw.setdefault("result", None)
    raw.setdefault("error_message", None)

    return raw


# Backward-compatible and convenient aliases
validate_asyncwork_announce_payload = validate_asyncwork_announce_payload_v1
validate_asyncwork_progress_payload = validate_asyncwork_progress_payload_v1
validate_asyncwork_done_payload = validate_asyncwork_done_payload_v1


# -----------------------------------------------------------------------------
# Channel Specifications
# -----------------------------------------------------------------------------
ASYNCWORK_ANNOUNCE_SPEC_V1 = EpsChannelSpecV1(
    channel=ASYNCWORK_ANNOUNCE_CHANNEL,
    app=ASYNCWORK_APP,
    schema=ASYNCWORK_ANNOUNCE_SCHEMA_V1,
    event="announce",
    validator=validate_asyncwork_announce_payload_v1,
    visibility=VISIBILITY_OWNER_ONLY,
    mode=MODE_PERSISTENCE,
    retention=RETENTION_DURABLE,
    terminal=False,
)

ASYNCWORK_PROGRESS_SPEC_V1 = EpsChannelSpecV1(
    channel=ASYNCWORK_PROGRESS_CHANNEL,
    app=ASYNCWORK_APP,
    schema=ASYNCWORK_PROGRESS_SCHEMA_V1,
    event="progress",
    validator=validate_asyncwork_progress_payload_v1,
    visibility=VISIBILITY_OWNER_ONLY,
    mode=MODE_PERSISTENCE,
    retention=RETENTION_TTL,
    ttl_seconds=604800,
    terminal=False,
)

ASYNCWORK_DONE_SPEC_V1 = EpsChannelSpecV1(
    channel=ASYNCWORK_DONE_CHANNEL,
    app=ASYNCWORK_APP,
    schema=ASYNCWORK_DONE_SCHEMA_V1,
    event="done",
    validator=validate_asyncwork_done_payload_v1,
    visibility=VISIBILITY_OWNER_ONLY,
    mode=MODE_PERSISTENCE,
    retention=RETENTION_DURABLE,
    terminal=True,
)

ASYNCWORK_CHANNELS_V1 = (
    ASYNCWORK_ANNOUNCE_SPEC_V1,
    ASYNCWORK_PROGRESS_SPEC_V1,
    ASYNCWORK_DONE_SPEC_V1,
)

__all__ = [
    "ASYNCWORK_ANNOUNCE_SPEC_V1",
    "ASYNCWORK_CHANNELS_V1",
    "ASYNCWORK_DONE_SPEC_V1",
    "ASYNCWORK_PROGRESS_SPEC_V1",
    "validate_asyncwork_announce_payload",
    "validate_asyncwork_announce_payload_v1",
    "validate_asyncwork_done_payload",
    "validate_asyncwork_done_payload_v1",
    "validate_asyncwork_progress_payload",
    "validate_asyncwork_progress_payload_v1",
]
