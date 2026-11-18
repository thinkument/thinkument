"""Thinkument Open Coordination Framework SDK & CLI."""
from __future__ import annotations

from thinkument.client import (
    CloudServiceRequiredError,
    ConcurrencyConflictError,
    ThinkClient,
    ThinkumentError,
)
from thinkument.daemon.interceptor import (
    VendorInvocation,
    create_ollama_interceptor,
    create_webhook_interceptor,
    default_mock_interceptor,
)
from thinkument.sdk.blackbox import BatchJob, BlackBoxJob, RunResult
from thinkument.sdk.catalogue import ValidationReport
from thinkument.sdk.economics import WalletBalance
from thinkument.sdk.live import EmbedHandle, LiveSessionHandle, RoleHandle
from thinkument.sdk.session import ActiveSession, DispatchOutcome, ThetaEvent, TridentTape

__version__ = "0.1.0"

__all__ = [
    "ThinkClient",
    "VendorInvocation",
    "default_mock_interceptor",
    "create_ollama_interceptor",
    "create_webhook_interceptor",
    "LiveSessionHandle",
    "RoleHandle",
    "EmbedHandle",
    "ActiveSession",
    "ThetaEvent",
    "DispatchOutcome",
    "TridentTape",
    "RunResult",
    "BlackBoxJob",
    "BatchJob",
    "ValidationReport",
    "WalletBalance",
]
