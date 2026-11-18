"""Canonical Types generated from Thinkument OpenAPI 3.1 specification."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SessionCreatePayload:
    P: Dict[str, Any]
    SM: Optional[Dict[str, Any]] = None
    C: Optional[Dict[str, Any]] = None
    slug: Optional[str] = None
    title: Optional[str] = None
    roles: Optional[List[str]] = None
    public_view_role: Optional[str] = None
    role_mismatch_policy: Optional[Dict[str, Any]] = None
    opinionation_module: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SessionCreateResponse:
    session_id: str
    url: str
    status: str
    roles: List[str] = field(default_factory=list)
    public_view_role: Optional[str] = None


@dataclass
class DispatchPayload:
    action: str
    user_fill: Optional[Dict[str, Any]] = None
    user_signal: Optional[Dict[str, Any]] = None
    cursor: Optional[int] = None
    role: Optional[str] = None
    identity_id: Optional[str] = None


@dataclass
class DispatchResponse:
    status: str
    applied_seq: Optional[int] = None
    latest_seq: Optional[int] = None
    error: Optional[str] = None
    session_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@dataclass
class TapeEvent:
    seq: int
    type: str = "event"
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    role: Optional[str] = None
    channel: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


@dataclass
class RelayPayload:
    operation: str
    args: Optional[Dict[str, Any]] = None
    modality: Optional[str] = None


@dataclass
class RelayResponse:
    status: str
    text: Optional[str] = None
    embeddings: Optional[Any] = None
    usage: Dict[str, int] = field(default_factory=dict)
    mocked: bool = False


@dataclass
class HealthzResponse:
    status: str
    version: str


@dataclass
class ModulePublishPayload:
    manifest: Dict[str, Any]
    authoring_template_version: Optional[str] = None


@dataclass
class ModuleRecord:
    id: str
    status: str
    version_id: Optional[str] = None
    source_manifest: Optional[Dict[str, Any]] = None
    template_version: Optional[str] = None


@dataclass
class ModuleSummary:
    id: str
    name: str
    version: str
    status: str


@dataclass
class RetireReceipt:
    module_id: str
    version_id: str
    retired: bool


@dataclass
class RunAnalytics:
    run_id: str
    total_steps: int
    duration_ms: float
    credits_used: float
    audit_events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class StorageDescriptor:
    ref: str
    url: Optional[str] = None
    filename: Optional[str] = None


# Ergonomic & Tour aliases
SessionLaunchResponse = SessionCreateResponse
SessionDispatchResponse = DispatchResponse
JobStatusResponse = Dict[str, Any]
