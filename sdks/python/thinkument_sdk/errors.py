"""Canonical Thinkument SDK Errors."""
from __future__ import annotations


class ThinkumentError(Exception):
    """Base error for all Thinkument SDK operations."""
    pass


class CloudServiceRequiredError(ThinkumentError):
    """Raised when an operation requires Thinkument Sovereign Cloud credentials."""

    def __init__(self, message: str = "Operation requires Sovereign Cloud Thinkument service and an API key") -> None:
        super().__init__(message)


class ConcurrencyConflictError(ThinkumentError):
    """Raised when a dispatch is rejected due to concurrent state conflict or stale cursor."""

    def __init__(self, message: str = "Dispatch rejected due to concurrent state update or stale cursor") -> None:
        super().__init__(message)
