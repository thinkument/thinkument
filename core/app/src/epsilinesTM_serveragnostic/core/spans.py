from __future__ import annotations

"""Timing and telemetry span context managers for accounted operations."""

from copy import deepcopy
from time import perf_counter_ns
from typing import Any, Callable, Dict, Mapping
from uuid import uuid4

from ..epsiline_spec_and_growth_sheet import (
    AUDIT_VENDOR_USAGE_CHANNEL,
    AUDIT_VENDOR_USAGE_SCHEMA_V1,
    analytica_envelope_v1,
)


def _python_type_str(val: Any) -> str:
    cls = type(val)
    return f"{cls.__module__}.{cls.__qualname__}"


class VendorUsageSpan:
    """Measures elapsed time, captures vendor usage, and emits audit-vendor-usage."""

    def __init__(
        self,
        *,
        vendor: str,
        operation: str,
        request: Mapping[str, Any] | None = None,
        attributes: Mapping[str, Any] | None = None,
        emitter: Callable[[str, Mapping[str, Any]], Any] | None = None,
        caller_identity: str = "generic_caller",
        operation_id: str | None = None,
        event_index: int = 1,
    ) -> None:
        self._vendor = str(vendor).strip()
        self._operation = str(operation).strip()
        if not self._vendor:
            raise ValueError("vendor must be non-empty")
        if not self._operation:
            raise ValueError("operation must be non-empty")

        self._request = deepcopy(dict(request)) if request is not None else None
        self._attributes = deepcopy(dict(attributes)) if attributes is not None else None
        self._emitter = emitter
        self._caller_identity = str(caller_identity or "generic_caller")
        self._operation_id = str(operation_id or f"op-{uuid4()}")
        self._event_index = int(event_index)

        self._usage: Dict[str, Any] | None = None
        self._started_ns: int | None = None
        self.emitted_envelope: Dict[str, Any] | None = None

    def set_usage(self, usage: Mapping[str, Any] | None) -> None:
        self._usage = deepcopy(dict(usage)) if usage is not None else None

    def __enter__(self) -> "VendorUsageSpan":
        self._started_ns = perf_counter_ns()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        del tb
        started = self._started_ns if self._started_ns is not None else perf_counter_ns()
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000.0

        status = "success"
        error = None
        if exc is not None:
            status = "error"
            error = {
                "message": str(exc),
                "exception_type": (
                    f"{exc_type.__module__}.{exc_type.__qualname__}"
                    if exc_type is not None
                    else _python_type_str(exc)
                ),
            }

        body = {
            "vendor": self._vendor,
            "operation": self._operation,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "request": deepcopy(self._request),
            "usage": deepcopy(self._usage),
            "attributes": deepcopy(self._attributes),
            "error": error,
        }

        self.emitted_envelope = analytica_envelope_v1(
            channel=AUDIT_VENDOR_USAGE_CHANNEL,
            schema=AUDIT_VENDOR_USAGE_SCHEMA_V1,
            event="vendor_usage",
            operation_id=self._operation_id,
            event_index=self._event_index,
            caller_identity=self._caller_identity,
            body=body,
        )

        if self._emitter is not None:
            self._emitter(AUDIT_VENDOR_USAGE_CHANNEL, deepcopy(self.emitted_envelope))

        return False


__all__ = [
    "VendorUsageSpan",
]
