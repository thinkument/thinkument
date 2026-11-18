"""Canonical exception hierarchy for Thinkument SDK."""
from __future__ import annotations


class ThinkumentError(Exception):
    """Base exception for all Thinkument SDK errors."""
    pass


class CloudServiceRequiredError(ThinkumentError):
    """Raised when a cloud-only operation (e.g. storage, persistent catalog) is attempted on a local studio client."""
    def __init__(self, operation: str, message: str | None = None) -> None:
        msg = message or (
            f"Operation {operation!r} requires Thinkument Sovereign Cloud. "
            "Initialize client with ThinkClient.connect(api_key='...') to access cloud features."
        )
        super().__init__(msg)
        self.operation = operation


class ConcurrencyConflictError(ThinkumentError):
    """Raised when an optimistic concurrency version conflict occurs."""
    pass
