from __future__ import annotations

"""Tier-1 Framework Central Epsilon Channel Specification & Growth Dashboard (`EPS_CHANNEL_SHEET_V1`).

This is the single front-facing declaration dashboard for all epsilon channels across the
Thinkument platform, Analytica, FormreactTM, Widget-Mouth, and HAI App-Packs.
Every platform channel and applied subapp channel is declared here and registered
into `core.registry` at import time.
"""

from copy import deepcopy
from typing import Any, Callable, Dict, Mapping

from _thinkprogram._iomicrosTM.tiny_helpers import assert_dead_json

from .core.registry import (
    ALLOWED_EPS_VISIBILITIES,
    AnalyticaProtocolError,
    EpsAppSpecV1,
    EpsChannelSpecV1,
    EpsRegistryError,
    UnregisteredEpsChannelError,
    VISIBILITY_ALL_NO_MODULATION,
    VISIBILITY_ALL_WITH_MODULATION,
    VISIBILITY_OWNER_ONLY,
    get_registered_eps_channel_v1,
    register_dynamic_channel_resolver_v1,
    register_eps_app_v1,
    registered_eps_channels_v1,
    require_registered_eps_channel_v1,
)

# -----------------------------------------------------------------------------
# Channel Names & Schemas: Analytica (Audit / Telemetry Subapp)
# -----------------------------------------------------------------------------
ANALYTICA_PROTOCOL_V1 = "thinkument.analytica.v1"

AUDIT_INS_CHANNEL = "audit-ins"
AUDIT_OUTS_CHANNEL = "audit-outs"
AUDIT_ERROR_CHANNEL = "audit-error"
AUDIT_VENDOR_USAGE_CHANNEL = "audit-vendor-usage"
AUDIT_VENDOR_COST_RECONCILIATION_CHANNEL = "audit-vendor-cost-reconciliation"
AUDIT_STORAGE_USAGE_CHANNEL = "audit-storage-usage"
AUDIT_STORAGE_USAGE_SCHEMA_V1 = "thinkwidget.storage-usage.v1"
AUDIT_WARNING_CHANNEL = "audit-warning"

AUDIT_INS_SCHEMA_V1 = "thinkument.analytica.audit-ins.v1"
AUDIT_OUTS_SCHEMA_V1 = "thinkument.analytica.audit-outs.v1"
AUDIT_ERROR_SCHEMA_V1 = "thinkument.analytica.audit-error.v1"
AUDIT_VENDOR_USAGE_SCHEMA_V1 = "thinkument.analytica.audit-vendor-usage.v1"
AUDIT_VENDOR_COST_RECONCILIATION_SCHEMA_V1 = "thinkument.analytica.audit-vendor-cost-reconciliation.v1"
AUDIT_WARNING_SCHEMA_V1 = "thinkument.analytica.audit-warning.v1"

_BUILTIN_CHANNELS = {
    AUDIT_STORAGE_USAGE_CHANNEL: {
        "schema": AUDIT_STORAGE_USAGE_SCHEMA_V1,
        "event": "storage-usage",
    },
    AUDIT_INS_CHANNEL: {
        "schema": AUDIT_INS_SCHEMA_V1,
        "event": "input",
    },
    AUDIT_OUTS_CHANNEL: {
        "schema": AUDIT_OUTS_SCHEMA_V1,
        "event": "output",
    },
    AUDIT_ERROR_CHANNEL: {
        "schema": AUDIT_ERROR_SCHEMA_V1,
        "event": "error",
    },
    AUDIT_VENDOR_USAGE_CHANNEL: {
        "schema": AUDIT_VENDOR_USAGE_SCHEMA_V1,
        "event": "vendor_usage",
    },
    AUDIT_VENDOR_COST_RECONCILIATION_CHANNEL: {
        "schema": AUDIT_VENDOR_COST_RECONCILIATION_SCHEMA_V1,
        "event": "vendor_cost_reconciliation",
    },
    AUDIT_WARNING_CHANNEL: {
        "schema": AUDIT_WARNING_SCHEMA_V1,
        "event": "warning",
    },
}

_TERMINAL_CHANNELS = frozenset({AUDIT_OUTS_CHANNEL, AUDIT_ERROR_CHANNEL})

_ENVELOPE_KEYS = frozenset(
    {
        "protocol",
        "schema",
        "channel",
        "event",
        "operation_id",
        "event_index",
        "widget_class",
        "body",
    }
)
_PUBLISHED_WIDGET_ENVELOPE_KEYS = frozenset(
    {"published_widget_version_id", "publisher_user_id"}
)

# -----------------------------------------------------------------------------
# Channel Names & Schemas: Platform & Foundation Channels
# -----------------------------------------------------------------------------
DATUM_MESSAGE_CHANNEL = "datum.message"
DATUM_MESSAGE_SCHEMA_V1 = "thinkument.eps.datum_message.v1"

SEMANTIC_VALIDATION_OBSERVED_CHANNEL = "semantic_validation.lifecycle_observed"
WIRING_PROOF_CHANNEL = "wiring.proof"
COMPLETENESS_PROOF_CHANNEL = "completeness.proof"
PROGRAM_SESSIONS_PROOF_CHANNEL = "program_sessions.proof"
UI_EPS_FIXTURE_CHANNEL = "ui.eps_fixture"
WIDGET_PROOF_SCHEMA_V1 = "thinkument.eps.widget_proof.v1"

FORMREACT_WIDGET_EXPLOSION_CHANNEL = "formreactTM.widget_explosion"
FORMREACT_WIDGET_EXPLOSION_SCHEMA_V1 = "thinkument.eps.formreact_explosion.v1"

EXAMPLE_NOTES_SAVED_CHANNEL = "example_notes.saved"
CREATIVITY_SANDBOX_PROBE_MESSAGE_CHANNEL = "creativity_sandbox.probe.message"
CREATIVITY_SANDBOX_AUDIT_PROBE_CHANNEL = "audit-app-pack-probe"
CREATIVITY_SANDBOX_AUDIT_PROBE_SCHEMA_V1 = "creativity_sandbox.probe.v1"
PACKITO_WIDGET_NOTICE_CHANNEL = "packito.widget_notice"
PACKITO_GLOBAL_NOTICE_CHANNEL = "packito.global_notice"
PACKITO_SILENT_METRIC_CHANNEL = "packito.silent_metric"
PACKITO_CUSTOM_NOTICE_CHANNEL = "packito.custom_notice"
APP_PACK_NOTICE_SCHEMA_V1 = "thinkument.eps.app_pack_notice.v1"


# -----------------------------------------------------------------------------
# Validation Helpers
# -----------------------------------------------------------------------------
def _nonempty_string(
    value: Any,
    *,
    path: str,
    maximum: int | None = None,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnalyticaProtocolError(f"{path} must be a non-empty string")
    out = value.strip()
    if maximum is not None and len(out) > maximum:
        raise AnalyticaProtocolError(f"{path} must be <= {maximum} characters")
    return out


def _mapping(
    value: Any,
    *,
    path: str,
) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AnalyticaProtocolError(f"{path} must be a mapping")
    return deepcopy(dict(value))


def _exact_keys(
    value: Mapping[str, Any],
    *,
    expected: set[str] | frozenset[str],
    path: str,
) -> None:
    keys = set(value)
    missing = sorted(set(expected) - keys)
    unknown = sorted(keys - set(expected))
    if missing or unknown:
        raise AnalyticaProtocolError(
            f"{path} has the wrong keys",
            details={
                "missing": missing,
                "unknown": unknown,
            },
        )


import re

_ANALYTICA_CHANNEL_RE = re.compile(r"^audit-[a-z0-9][a-z0-9._-]*$")


def is_analytica_channel_v1(value: Any) -> bool:
    """Whether a transport message name belongs to Analytica."""
    if not isinstance(value, str):
        return False
    channel = value.strip()
    if bool(channel and len(channel) <= 200 and _ANALYTICA_CHANNEL_RE.fullmatch(channel)):
        return True
    spec = get_registered_eps_channel_v1(channel)
    return spec is not None and spec.app == "analytica"


def _validate_builtin_body_v1(
    channel: str,
    body: Mapping[str, Any],
) -> None:
    if channel == AUDIT_STORAGE_USAGE_CHANNEL:
        _nonempty_string(body.get("kind"), path="body.kind")
        return
    if channel == AUDIT_INS_CHANNEL:
        _exact_keys(
            body,
            expected={
                "trigger",
                "authored_args",
                "history_wires",
                "current_fills",
                "signal",
            },
            path="body",
        )
        _nonempty_string(
            body["trigger"],
            path="body.trigger",
        )
        _mapping(
            body["authored_args"],
            path="body.authored_args",
        )
        _mapping(
            body["history_wires"],
            path="body.history_wires",
        )
        _mapping(
            body["current_fills"],
            path="body.current_fills",
        )
        if (
            body["signal"] is not None
            and not isinstance(body["signal"], Mapping)
        ):
            raise AnalyticaProtocolError(
                "body.signal must be a mapping or null"
            )
        return

    if channel == AUDIT_OUTS_CHANNEL:
        _exact_keys(
            body,
            expected={
                "outcome",
                "state_writes",
                "state_deleted",
            },
            path="body",
        )
        _mapping(body["outcome"], path="body.outcome")
        _mapping(
            body["state_writes"],
            path="body.state_writes",
        )
        if not isinstance(body["state_deleted"], list):
            raise AnalyticaProtocolError(
                "body.state_deleted must be a list"
            )
        if not all(
            isinstance(value, str) and value
            for value in body["state_deleted"]
        ):
            raise AnalyticaProtocolError(
                "body.state_deleted must contain non-empty strings"
            )
        return

    if channel == AUDIT_ERROR_CHANNEL:
        _exact_keys(
            body,
            expected={
                "message",
                "exception_type",
                "details",
            },
            path="body",
        )
        _nonempty_string(
            body["message"],
            path="body.message",
        )
        _nonempty_string(
            body["exception_type"],
            path="body.exception_type",
        )
        return

    if channel == AUDIT_VENDOR_USAGE_CHANNEL:
        _exact_keys(
            body,
            expected={
                "vendor",
                "operation",
                "status",
                "elapsed_ms",
                "request",
                "usage",
                "attributes",
                "error",
            },
            path="body",
        )
        _nonempty_string(
            body["vendor"],
            path="body.vendor",
        )
        _nonempty_string(
            body["operation"],
            path="body.operation",
        )
        if body["status"] not in {"success", "error"}:
            raise AnalyticaProtocolError(
                "body.status must be success or error"
            )
        if (
            isinstance(body["elapsed_ms"], bool)
            or not isinstance(body["elapsed_ms"], (int, float))
            or body["elapsed_ms"] < 0
        ):
            raise AnalyticaProtocolError(
                "body.elapsed_ms must be a non-negative number"
            )
        for key in ("request", "usage", "attributes"):
            if (
                body[key] is not None
                and not isinstance(body[key], Mapping)
            ):
                raise AnalyticaProtocolError(
                    f"body.{key} must be a mapping or null"
                )
        if (
            body["error"] is not None
            and not isinstance(body["error"], Mapping)
        ):
            raise AnalyticaProtocolError(
                "body.error must be a mapping or null"
            )
        if (
            body["status"] == "success"
            and body["error"] is not None
        ):
            raise AnalyticaProtocolError(
                "successful vendor usage cannot carry body.error"
            )
        return

    if channel == AUDIT_VENDOR_COST_RECONCILIATION_CHANNEL:
        _exact_keys(
            body,
            expected={
                "vendor_call_id",
                "charge_id",
                "original_operation_id",
                "vendor",
                "operation",
                "settlement_status",
                "estimated_usd",
                "actual_usd",
                "estimated_microcredits",
                "calculated_microcredits",
                "charged_microcredits",
                "refunded_microcredits",
                "excess_microcredits",
                "usage",
                "reconciliation_details",
            },
            path="body",
        )
        if body["settlement_status"] not in {"reconciled", "breach_cap_retained"}:
            raise AnalyticaProtocolError(
                "body.settlement_status must be reconciled or breach_cap_retained"
            )
        for key in ("vendor_call_id", "charge_id", "vendor", "operation"):
            _nonempty_string(body[key], path=f"body.{key}")
        for key in (
            "estimated_microcredits",
            "charged_microcredits",
            "refunded_microcredits",
            "excess_microcredits",
        ):
            value = body[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise AnalyticaProtocolError(
                    f"body.{key} must be a non-negative integer"
                )
        calculated = body["calculated_microcredits"]
        if body["settlement_status"] == "reconciled":
            if isinstance(calculated, bool) or not isinstance(calculated, int) or calculated < 0:
                raise AnalyticaProtocolError(
                    "body.calculated_microcredits must be a non-negative integer when reconciled"
                )
        elif calculated is not None:
            raise AnalyticaProtocolError(
                "body.calculated_microcredits must be null when breach_cap_retained"
            )
        if body["settlement_status"] == "reconciled":
            if not isinstance(body["actual_usd"], str):
                raise AnalyticaProtocolError("body.actual_usd must be a string when reconciled")
        elif body["actual_usd"] is not None:
            raise AnalyticaProtocolError(
                "body.actual_usd must be null when breach_cap_retained"
            )
        for key in ("usage", "reconciliation_details"):
            if not isinstance(body[key], Mapping):
                raise AnalyticaProtocolError(f"body.{key} must be a mapping")
        return

    if channel == AUDIT_WARNING_CHANNEL:
        _exact_keys(
            body,
            expected={"message", "details"},
            path="body",
        )
        _nonempty_string(
            body["message"],
            path="body.message",
        )


def validate_analytica_envelope_v1(
    channel: str,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate and return a detached Analytica envelope."""
    transport_channel = _nonempty_string(
        channel,
        path="channel",
        maximum=200,
    )
    if not is_analytica_channel_v1(transport_channel):
        raise UnregisteredEpsChannelError(
            f"{transport_channel!r} is not an Analytica channel",
            details={"channel": transport_channel},
        )

    envelope = _mapping(
        payload,
        path="analytica envelope",
    )
    keys = frozenset(envelope)
    if keys not in {_ENVELOPE_KEYS, _ENVELOPE_KEYS | _PUBLISHED_WIDGET_ENVELOPE_KEYS}:
        _exact_keys(
            envelope,
            expected=_ENVELOPE_KEYS,
            path="analytica envelope",
        )

    assert_dead_json(
        envelope,
        path="analytica",
    )

    if envelope["protocol"] != ANALYTICA_PROTOCOL_V1:
        raise AnalyticaProtocolError(
            "unsupported Analytica protocol",
            details={
                "received": envelope["protocol"],
                "expected": ANALYTICA_PROTOCOL_V1,
            },
        )

    if envelope["channel"] != transport_channel:
        raise AnalyticaProtocolError(
            "envelope.channel must equal the epsilon transport channel"
        )

    schema = _nonempty_string(
        envelope["schema"],
        path="schema",
    )
    event = _nonempty_string(
        envelope["event"],
        path="event",
    )
    operation_id = _nonempty_string(
        envelope["operation_id"],
        path="operation_id",
        maximum=128,
    )
    widget_class = _nonempty_string(
        envelope["widget_class"],
        path="widget_class",
        maximum=300,
    )
    if _PUBLISHED_WIDGET_ENVELOPE_KEYS <= keys:
        _nonempty_string(
            envelope["published_widget_version_id"],
            path="published_widget_version_id",
            maximum=200,
        )
        _nonempty_string(
            envelope["publisher_user_id"],
            path="publisher_user_id",
            maximum=128,
        )

    index = envelope["event_index"]
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or index < 0
    ):
        raise AnalyticaProtocolError(
            "event_index must be a non-negative integer"
        )

    body = _mapping(
        envelope["body"],
        path="body",
    )

    builtin = _BUILTIN_CHANNELS.get(transport_channel)
    if builtin is not None:
        if schema != builtin["schema"]:
            raise AnalyticaProtocolError(
                f"{transport_channel} requires schema "
                f"{builtin['schema']!r}"
            )
        if event != builtin["event"]:
            raise AnalyticaProtocolError(
                f"{transport_channel} requires event "
                f"{builtin['event']!r}"
            )
        _validate_builtin_body_v1(
            transport_channel,
            body,
        )
    else:
        if event in {"input", "output", "error"}:
            raise AnalyticaProtocolError(
                "custom audit-* channels may not impersonate "
                "input/output/error terminal semantics"
            )

    if transport_channel == AUDIT_INS_CHANNEL:
        if index != 0:
            raise AnalyticaProtocolError(
                "audit-ins must have event_index=0"
            )
    elif index == 0:
        raise AnalyticaProtocolError(
            "only audit-ins may have event_index=0"
        )

    return {
        **envelope,
        "operation_id": operation_id,
        "widget_class": widget_class,
        "schema": schema,
        "event": event,
        "body": body,
    }


def _resolve_dynamic_analytica_channel_v1(channel: str) -> EpsChannelSpecV1 | None:
    """Dynamically resolve any pattern-compliant Analytica custom audit channel."""
    if bool(channel and len(channel) <= 200 and _ANALYTICA_CHANNEL_RE.fullmatch(channel)):
        return EpsChannelSpecV1(
            channel=channel,
            app="analytica",
            schema=f"thinkument.analytica.{channel}.v1",
            event="audit",
            validator=validate_analytica_envelope_v1,
            visibility=VISIBILITY_OWNER_ONLY,
            mode="persistence",
            retention="durable",
        )
    return None


register_dynamic_channel_resolver_v1(_resolve_dynamic_analytica_channel_v1)



def analytica_envelope_v1(
    *,
    channel: str,
    schema: str,
    event: str,
    operation_id: str,
    event_index: int,
    widget_class: str | None = None,
    caller_identity: str | None = None,
    body: Mapping[str, Any],
    published_widget_version_id: str | None = None,
    publisher_user_id: str | None = None,
) -> Dict[str, Any]:
    """Construct and validate a canonical Analytica envelope."""
    identity = caller_identity or widget_class
    if not identity:
        raise AnalyticaProtocolError("caller_identity or widget_class is required")
    envelope = {
        "protocol": ANALYTICA_PROTOCOL_V1,
        "schema": str(schema),
        "channel": str(channel),
        "event": str(event),
        "operation_id": str(operation_id),
        "event_index": int(event_index),
        "widget_class": str(identity),
        "body": deepcopy(dict(body)),
    }
    if published_widget_version_id is not None or publisher_user_id is not None:
        if published_widget_version_id is None or publisher_user_id is None:
            raise AnalyticaProtocolError(
                "published widget version and publisher identity must be supplied together"
            )
        envelope["published_widget_version_id"] = str(published_widget_version_id)
        envelope["publisher_user_id"] = str(publisher_user_id)
    return validate_analytica_envelope_v1(
        str(channel),
        envelope,
    )


class AnalyticaOperationStreamValidatorV1:
    """Validate correlation/order laws across received Analytica events."""

    def __init__(self) -> None:
        self._next_index: dict[str, int] = {}
        self._closed: set[str] = set()

    def accept_v1(
        self,
        channel: str,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        envelope = validate_analytica_envelope_v1(
            channel,
            payload,
        )
        operation_id = envelope["operation_id"]
        index = envelope["event_index"]

        if operation_id in self._closed:
            raise AnalyticaProtocolError(
                "Analytica event appeared after operation terminal",
                details={
                    "operation_id": operation_id,
                    "event_index": index,
                },
            )

        if channel == AUDIT_INS_CHANNEL:
            if operation_id in self._next_index:
                raise AnalyticaProtocolError(
                    "second audit-ins for one operation is illegal",
                    details={"operation_id": operation_id},
                )
            self._next_index[operation_id] = 1
            return envelope

        if operation_id not in self._next_index:
            raise AnalyticaProtocolError(
                "Analytica non-input event has no preceding audit-ins",
                details={
                    "operation_id": operation_id,
                    "channel": channel,
                },
            )

        expected = self._next_index[operation_id]
        if index != expected:
            raise AnalyticaProtocolError(
                "noncontiguous Analytica event_index",
                details={
                    "operation_id": operation_id,
                    "expected": expected,
                    "received": index,
                },
            )

        if channel in _TERMINAL_CHANNELS:
            del self._next_index[operation_id]
            self._closed.add(operation_id)
        else:
            self._next_index[operation_id] = expected + 1

        return envelope

    def assert_closed_v1(self) -> None:
        if self._next_index:
            raise AnalyticaProtocolError(
                f"Analytica stream ended with unterminated operations: {sorted(self._next_index)}",
                details={
                    "open_operation_ids": sorted(
                        self._next_index
                    )
                },
            )

    def reset_v1(self) -> None:
        self._next_index.clear()
        self._closed.clear()


# -----------------------------------------------------------------------------
# Platform Channel Validators
# -----------------------------------------------------------------------------
def validate_datum_message_eps_v1(
    channel: str,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate a widget-mouth / datum.message epsilon payload."""
    if not isinstance(payload, Mapping):
        raise EpsRegistryError(f"{channel!r} payload must be a mapping")
    out = deepcopy(dict(payload))
    assert_dead_json(out, path=f"eps[{channel}]")
    return out


def validate_formreact_eps_payload_v1(
    channel: str,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate a FormreactTM widget explosion epsilon payload."""
    if not isinstance(payload, Mapping):
        raise EpsRegistryError(f"{channel!r} payload must be a mapping")
    out = deepcopy(dict(payload))
    assert_dead_json(out, path=f"eps[{channel}]")
    return out


def validate_app_pack_eps_payload_v1(
    channel: str,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate a HAI app-pack live notification epsilon payload."""
    if not isinstance(payload, Mapping):
        raise EpsRegistryError(f"{channel!r} payload must be a mapping")
    out = deepcopy(dict(payload))
    assert_dead_json(out, path=f"eps[{channel}]")
    return out


# -----------------------------------------------------------------------------
# Declarative Channel Specifications
# -----------------------------------------------------------------------------
_ANALYTICA_CHANNELS_V1: tuple[EpsChannelSpecV1, ...] = (
    EpsChannelSpecV1(
        AUDIT_INS_CHANNEL,
        "analytica",
        AUDIT_INS_SCHEMA_V1,
        "input",
        validate_analytica_envelope_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="durable",
        terminal=False,
    ),
    EpsChannelSpecV1(
        AUDIT_OUTS_CHANNEL,
        "analytica",
        AUDIT_OUTS_SCHEMA_V1,
        "output",
        validate_analytica_envelope_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="durable",
        terminal=True,
    ),
    EpsChannelSpecV1(
        AUDIT_ERROR_CHANNEL,
        "analytica",
        AUDIT_ERROR_SCHEMA_V1,
        "error",
        validate_analytica_envelope_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="durable",
        terminal=True,
    ),
    EpsChannelSpecV1(
        AUDIT_WARNING_CHANNEL,
        "analytica",
        AUDIT_WARNING_SCHEMA_V1,
        "warning",
        validate_analytica_envelope_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="durable",
        terminal=False,
    ),
    EpsChannelSpecV1(
        AUDIT_VENDOR_USAGE_CHANNEL,
        "analytica",
        AUDIT_VENDOR_USAGE_SCHEMA_V1,
        "vendor_usage",
        validate_analytica_envelope_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="durable",
        terminal=False,
    ),
    EpsChannelSpecV1(
        AUDIT_VENDOR_COST_RECONCILIATION_CHANNEL,
        "analytica",
        AUDIT_VENDOR_COST_RECONCILIATION_SCHEMA_V1,
        "vendor_cost_reconciliation",
        validate_analytica_envelope_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="durable",
        terminal=False,
    ),
    EpsChannelSpecV1(
        AUDIT_STORAGE_USAGE_CHANNEL,
        "analytica",
        AUDIT_STORAGE_USAGE_SCHEMA_V1,
        "storage-usage",
        validate_analytica_envelope_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="durable",
        terminal=False,
    ),
    EpsChannelSpecV1(
        CREATIVITY_SANDBOX_AUDIT_PROBE_CHANNEL,
        "analytica",
        CREATIVITY_SANDBOX_AUDIT_PROBE_SCHEMA_V1,
        "value_accepted",
        validate_analytica_envelope_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="durable",
        terminal=False,
    ),
)

_PLATFORM_CHANNELS_V1: tuple[EpsChannelSpecV1, ...] = (
    EpsChannelSpecV1(
        DATUM_MESSAGE_CHANNEL,
        "platform",
        DATUM_MESSAGE_SCHEMA_V1,
        "datum_event",
        validate_datum_message_eps_v1,
        VISIBILITY_ALL_WITH_MODULATION,
        mode="persistence",
        retention="durable",
        terminal=False,
    ),
    EpsChannelSpecV1(
        SEMANTIC_VALIDATION_OBSERVED_CHANNEL,
        "platform",
        WIDGET_PROOF_SCHEMA_V1,
        "lifecycle_observed",
        validate_datum_message_eps_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="ttl",
        ttl_seconds=3600,
        terminal=False,
    ),
    EpsChannelSpecV1(
        WIRING_PROOF_CHANNEL,
        "platform",
        WIDGET_PROOF_SCHEMA_V1,
        "proof",
        validate_datum_message_eps_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="ttl",
        ttl_seconds=3600,
        terminal=False,
    ),
    EpsChannelSpecV1(
        COMPLETENESS_PROOF_CHANNEL,
        "platform",
        WIDGET_PROOF_SCHEMA_V1,
        "proof",
        validate_datum_message_eps_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="ttl",
        ttl_seconds=3600,
        terminal=False,
    ),
    EpsChannelSpecV1(
        PROGRAM_SESSIONS_PROOF_CHANNEL,
        "platform",
        WIDGET_PROOF_SCHEMA_V1,
        "proof",
        validate_datum_message_eps_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="ttl",
        ttl_seconds=3600,
        terminal=False,
    ),
    EpsChannelSpecV1(
        UI_EPS_FIXTURE_CHANNEL,
        "platform",
        WIDGET_PROOF_SCHEMA_V1,
        "ui_fixture",
        validate_datum_message_eps_v1,
        VISIBILITY_ALL_WITH_MODULATION,
        mode="persistence",
        retention="ttl",
        ttl_seconds=3600,
        terminal=False,
    ),
)

_FORMREACT_CHANNELS_V1: tuple[EpsChannelSpecV1, ...] = (
    EpsChannelSpecV1(
        FORMREACT_WIDGET_EXPLOSION_CHANNEL,
        "formreactTM",
        FORMREACT_WIDGET_EXPLOSION_SCHEMA_V1,
        "widget_explosion",
        validate_formreact_eps_payload_v1,
        VISIBILITY_ALL_WITH_MODULATION,
        mode="none",
        retention="none",
        terminal=False,
    ),
)

_CREATIVITY_SANDBOX_CHANNELS_V1: tuple[EpsChannelSpecV1, ...] = (
    EpsChannelSpecV1(
        EXAMPLE_NOTES_SAVED_CHANNEL,
        "creativity_sandbox",
        APP_PACK_NOTICE_SCHEMA_V1,
        "notes_saved",
        validate_app_pack_eps_payload_v1,
        VISIBILITY_ALL_WITH_MODULATION,
        mode="persistence",
        retention="durable",
        terminal=False,
    ),
    EpsChannelSpecV1(
        CREATIVITY_SANDBOX_PROBE_MESSAGE_CHANNEL,
        "creativity_sandbox",
        APP_PACK_NOTICE_SCHEMA_V1,
        "probe_message",
        validate_app_pack_eps_payload_v1,
        VISIBILITY_ALL_NO_MODULATION,
        mode="persistence",
        retention="durable",
        terminal=False,
    ),
)

_PACKITO_CHANNELS_V1: tuple[EpsChannelSpecV1, ...] = (
    EpsChannelSpecV1(
        PACKITO_WIDGET_NOTICE_CHANNEL,
        "packito",
        APP_PACK_NOTICE_SCHEMA_V1,
        "widget_notice",
        validate_app_pack_eps_payload_v1,
        VISIBILITY_ALL_WITH_MODULATION,
        mode="persistence",
        retention="ttl",
        ttl_seconds=3600,
        terminal=False,
    ),
    EpsChannelSpecV1(
        PACKITO_GLOBAL_NOTICE_CHANNEL,
        "packito",
        APP_PACK_NOTICE_SCHEMA_V1,
        "global_notice",
        validate_app_pack_eps_payload_v1,
        VISIBILITY_ALL_NO_MODULATION,
        mode="persistence",
        retention="ttl",
        ttl_seconds=3600,
        terminal=False,
    ),
    EpsChannelSpecV1(
        PACKITO_SILENT_METRIC_CHANNEL,
        "packito",
        APP_PACK_NOTICE_SCHEMA_V1,
        "silent_metric",
        validate_app_pack_eps_payload_v1,
        VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="ttl",
        ttl_seconds=3600,
        terminal=False,
    ),
    EpsChannelSpecV1(
        PACKITO_CUSTOM_NOTICE_CHANNEL,
        "packito",
        APP_PACK_NOTICE_SCHEMA_V1,
        "custom_notice",
        validate_app_pack_eps_payload_v1,
        VISIBILITY_ALL_WITH_MODULATION,
        mode="persistence",
        retention="ttl",
        ttl_seconds=3600,
        terminal=False,
    ),
)

# -----------------------------------------------------------------------------
# Channel Names & Schemas: AsyncWork (Asynchronous Execution Subapp)
# -----------------------------------------------------------------------------
ASYNCWORK_APP = "asyncwork"

ASYNCWORK_ANNOUNCE_CHANNEL = "asyncwork.announce"
ASYNCWORK_PROGRESS_CHANNEL = "asyncwork.progress"
ASYNCWORK_DONE_CHANNEL = "asyncwork.done"

ASYNCWORK_ANNOUNCE_SCHEMA_V1 = "thinkument.asyncwork.announce.v1"
ASYNCWORK_PROGRESS_SCHEMA_V1 = "thinkument.asyncwork.progress.v1"
ASYNCWORK_DONE_SCHEMA_V1 = "thinkument.asyncwork.done.v1"

ASYNCWORK_ANNOUNCE_EVENT = "announce"
ASYNCWORK_PROGRESS_EVENT = "progress"
ASYNCWORK_DONE_EVENT = "done"

# Terminal outcomes
OUTCOME_SUCCESS = "success"
OUTCOME_ERROR = "error"
OUTCOME_TIMEOUT = "timeout"
ASYNCWORK_OUTCOMES = frozenset({OUTCOME_SUCCESS, OUTCOME_ERROR, OUTCOME_TIMEOUT})

# Intermediate progress statuses
STATUS_RUNNING = "running"
STATUS_IN_PROGRESS = "in_progress"
STATUS_WAITING = "waiting"
STATUS_CHECKPOINT = "checkpoint"
STATUS_WARNING = "warning"
STATUS_DONE = "done"
ASYNCWORK_PROGRESS_STATUSES = frozenset(
    {
        STATUS_RUNNING,
        STATUS_IN_PROGRESS,
        STATUS_WAITING,
        STATUS_CHECKPOINT,
        STATUS_WARNING,
        STATUS_DONE,
    }
)


def validate_asyncwork_announce_payload_v1(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and normalize payload for `asyncwork.announce`."""
    if not isinstance(payload, Mapping):
        raise EpsRegistryError("asyncwork.announce payload must be a dict / mapping")
    raw = deepcopy(dict(payload))
    assert_dead_json(raw, path=f"eps[{ASYNCWORK_ANNOUNCE_CHANNEL}]")

    target = str(raw.get("target") or "").strip()
    if not target:
        raise EpsRegistryError("asyncwork.announce requires a non-empty 'target' string")
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
            raise EpsRegistryError("asyncwork.announce 'timeout_seconds' must be positive")
        raw["timeout_seconds"] = float(timeout_seconds)

    max_retries = raw.get("max_retries")
    if max_retries is not None:
        if not isinstance(max_retries, int) or max_retries < 0:
            raise EpsRegistryError("asyncwork.announce 'max_retries' must be a non-negative integer")

    return raw


def validate_asyncwork_progress_payload_v1(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and normalize payload for `asyncwork.progress`."""
    if not isinstance(payload, Mapping):
        raise EpsRegistryError("asyncwork.progress payload must be a dict / mapping")
    raw = deepcopy(dict(payload))
    assert_dead_json(raw, path=f"eps[{ASYNCWORK_PROGRESS_CHANNEL}]")

    target = str(raw.get("target") or "").strip()
    if not target:
        raise EpsRegistryError("asyncwork.progress requires a non-empty 'target' string")
    raw["target"] = target

    percent = raw.get("percent")
    if percent is None:
        percent = raw.get("pct")
    if percent is not None:
        if not isinstance(percent, (int, float)) or percent < 0.0 or percent > 100.0:
            raise EpsRegistryError("asyncwork.progress 'percent' must be between 0 and 100")
        raw["percent"] = float(percent)

    status = raw.get("status")
    if status is not None:
        status = str(status).strip()
        if status not in ASYNCWORK_PROGRESS_STATUSES:
            raise EpsRegistryError(
                f"asyncwork.progress 'status' must be one of {sorted(ASYNCWORK_PROGRESS_STATUSES)}, got {status!r}"
            )
        raw["status"] = status
    else:
        raw["status"] = STATUS_IN_PROGRESS

    return raw


def validate_asyncwork_done_payload_v1(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and normalize payload for `asyncwork.done`."""
    if not isinstance(payload, Mapping):
        raise EpsRegistryError("asyncwork.done payload must be a dict / mapping")
    raw = deepcopy(dict(payload))
    assert_dead_json(raw, path=f"eps[{ASYNCWORK_DONE_CHANNEL}]")

    target = str(raw.get("target") or "").strip()
    if not target:
        raise EpsRegistryError("asyncwork.done requires a non-empty 'target' string")
    raw["target"] = target

    outcome = str(raw.get("outcome") or "").strip()
    if outcome not in ASYNCWORK_OUTCOMES:
        raise EpsRegistryError(
            f"asyncwork.done 'outcome' must be one of {sorted(ASYNCWORK_OUTCOMES)}, got {outcome!r}"
        )
    raw["outcome"] = outcome

    duration_ms = raw.get("duration_ms")
    if duration_ms is not None:
        if not isinstance(duration_ms, (int, float)) or duration_ms < 0:
            raise EpsRegistryError("asyncwork.done 'duration_ms' must be non-negative")
        raw["duration_ms"] = float(duration_ms)

    return raw


_ASYNCWORK_CHANNELS_V1: tuple[EpsChannelSpecV1, ...] = (
    EpsChannelSpecV1(
        channel=ASYNCWORK_ANNOUNCE_CHANNEL,
        app=ASYNCWORK_APP,
        schema=ASYNCWORK_ANNOUNCE_SCHEMA_V1,
        event=ASYNCWORK_ANNOUNCE_EVENT,
        validator=validate_asyncwork_announce_payload_v1,
        visibility=VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="durable",
        terminal=False,
    ),
    EpsChannelSpecV1(
        channel=ASYNCWORK_PROGRESS_CHANNEL,
        app=ASYNCWORK_APP,
        schema=ASYNCWORK_PROGRESS_SCHEMA_V1,
        event=ASYNCWORK_PROGRESS_EVENT,
        validator=validate_asyncwork_progress_payload_v1,
        visibility=VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="ttl",
        ttl_seconds=604800,
        terminal=False,
    ),
    EpsChannelSpecV1(
        channel=ASYNCWORK_DONE_CHANNEL,
        app=ASYNCWORK_APP,
        schema=ASYNCWORK_DONE_SCHEMA_V1,
        event=ASYNCWORK_DONE_EVENT,
        validator=validate_asyncwork_done_payload_v1,
        visibility=VISIBILITY_OWNER_ONLY,
        mode="persistence",
        retention="durable",
        terminal=True,
    ),
)

# -----------------------------------------------------------------------------
# Master Declarative Channel Sheet
# -----------------------------------------------------------------------------
EPS_CHANNEL_SHEET_V1: tuple[EpsAppSpecV1, ...] = (
    EpsAppSpecV1(
        "platform",
        _PLATFORM_CHANNELS_V1,
    ),
    EpsAppSpecV1(
        "analytica",
        _ANALYTICA_CHANNELS_V1,
        stream_validator_factory=AnalyticaOperationStreamValidatorV1,
    ),
    EpsAppSpecV1(
        "formreactTM",
        _FORMREACT_CHANNELS_V1,
    ),
    EpsAppSpecV1(
        "creativity_sandbox",
        _CREATIVITY_SANDBOX_CHANNELS_V1,
    ),
    EpsAppSpecV1(
        "packito",
        _PACKITO_CHANNELS_V1,
    ),
    EpsAppSpecV1(
        ASYNCWORK_APP,
        _ASYNCWORK_CHANNELS_V1,
    ),
)

EPS_APP_SHEET_V1: tuple[str, ...] = tuple(app.name for app in EPS_CHANNEL_SHEET_V1)

for _app_spec in EPS_CHANNEL_SHEET_V1:
    register_eps_app_v1(_app_spec)

def assert_eps_channel_sheet_invariants_v1() -> None:
    """Verify structural invariants of `EPS_CHANNEL_SHEET_V1` (D27, D35)."""
    seen_channels: set[str] = set()
    for app_spec in EPS_CHANNEL_SHEET_V1:
        for spec in app_spec.channels:
            if spec.channel in seen_channels:
                raise EpsRegistryError(f"duplicate channel in EPS_CHANNEL_SHEET_V1: {spec.channel!r}")
            seen_channels.add(spec.channel)
            if spec.visibility not in ALLOWED_EPS_VISIBILITIES:
                raise EpsRegistryError(f"invalid visibility on {spec.channel!r}: {spec.visibility!r}")
            if not callable(spec.validator):
                raise EpsRegistryError(f"validator on {spec.channel!r} must be callable")
            if spec.app == "analytica" and spec.visibility != VISIBILITY_OWNER_ONLY:
                raise EpsRegistryError(
                    f"analytica channel {spec.channel!r} must be owner-only (D9/D37)"
                )
    registered = registered_eps_channels_v1()
    missing = seen_channels - set(registered)
    if missing:
        raise EpsRegistryError(f"sheet channels missing from runtime registry: {sorted(missing)}")


assert_eps_channel_sheet_invariants_v1()

__all__ = [
    "ANALYTICA_PROTOCOL_V1",
    "APP_PACK_NOTICE_SCHEMA_V1",
    "AUDIT_ERROR_CHANNEL",
    "AUDIT_ERROR_SCHEMA_V1",
    "AUDIT_INS_CHANNEL",
    "AUDIT_INS_SCHEMA_V1",
    "AUDIT_OUTS_CHANNEL",
    "AUDIT_OUTS_SCHEMA_V1",
    "AUDIT_STORAGE_USAGE_CHANNEL",
    "AUDIT_STORAGE_USAGE_SCHEMA_V1",
    "AUDIT_VENDOR_COST_RECONCILIATION_CHANNEL",
    "AUDIT_VENDOR_COST_RECONCILIATION_SCHEMA_V1",
    "AUDIT_VENDOR_USAGE_CHANNEL",
    "AUDIT_VENDOR_USAGE_SCHEMA_V1",
    "AUDIT_WARNING_CHANNEL",
    "AUDIT_WARNING_SCHEMA_V1",
    "AnalyticaOperationStreamValidatorV1",
    "AnalyticaProtocolError",
    "COMPLETENESS_PROOF_CHANNEL",
    "CREATIVITY_SANDBOX_AUDIT_PROBE_CHANNEL",
    "CREATIVITY_SANDBOX_AUDIT_PROBE_SCHEMA_V1",
    "CREATIVITY_SANDBOX_PROBE_MESSAGE_CHANNEL",
    "DATUM_MESSAGE_CHANNEL",
    "DATUM_MESSAGE_SCHEMA_V1",
    "EPS_APP_SHEET_V1",
    "EPS_CHANNEL_SHEET_V1",
    "EXAMPLE_NOTES_SAVED_CHANNEL",
    "FORMREACT_WIDGET_EXPLOSION_CHANNEL",
    "FORMREACT_WIDGET_EXPLOSION_SCHEMA_V1",
    "PACKITO_CUSTOM_NOTICE_CHANNEL",
    "PACKITO_GLOBAL_NOTICE_CHANNEL",
    "PACKITO_SILENT_METRIC_CHANNEL",
    "PACKITO_WIDGET_NOTICE_CHANNEL",
    "PROGRAM_SESSIONS_PROOF_CHANNEL",
    "SEMANTIC_VALIDATION_OBSERVED_CHANNEL",
    "UI_EPS_FIXTURE_CHANNEL",
    "WIDGET_PROOF_SCHEMA_V1",
    "WIRING_PROOF_CHANNEL",
    "analytica_envelope_v1",
    "assert_eps_channel_sheet_invariants_v1",
    "is_analytica_channel_v1",
    "validate_analytica_envelope_v1",
    "validate_app_pack_eps_payload_v1",
    "validate_datum_message_eps_v1",
    "validate_formreact_eps_payload_v1",
]
