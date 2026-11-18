"""Idiomatic typed Python client generated from Thinkument OpenAPI 3.1 specification."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Union
import requests

from .errors import CloudServiceRequiredError, ConcurrencyConflictError, ThinkumentError
from .types import (
    DispatchPayload,
    DispatchResponse,
    HealthzResponse,
    ModulePublishPayload,
    ModuleRecord,
    ModuleSummary,
    RelayPayload,
    RelayResponse,
    RetireReceipt,
    RunAnalytics,
    SessionCreatePayload,
    SessionCreateResponse,
    StorageDescriptor,
    TapeEvent,
)


class SessionNamespace:
    def __init__(self, client: ThinkClient) -> None:
        self._c = client

    def create(self, payload: Union[SessionCreatePayload, Dict[str, Any]]) -> SessionCreateResponse:
        data = payload if isinstance(payload, dict) else payload.__dict__
        clean = {k: v for k, v in data.items() if v is not None}
        res = self._c._post("/sessions/", clean)
        return SessionCreateResponse(
            session_id=res.get("session_id", res.get("id", "")),
            url=res.get("url", ""),
            status=res.get("status", "created"),
            roles=res.get("roles", []),
        )

    def dispatch(self, session_id: str, payload: Union[DispatchPayload, Dict[str, Any]]) -> DispatchResponse:
        data = payload if isinstance(payload, dict) else payload.__dict__
        clean = {k: v for k, v in data.items() if v is not None}
        res = self._c._post(f"/sessions/{session_id}/dispatch/", clean)
        return DispatchResponse(
            status=res.get("status", "ok"),
            applied_seq=res.get("applied_seq"),
            latest_seq=res.get("latest_seq"),
            error=res.get("error"),
        )

    def get(self, session_id: str) -> Dict[str, Any]:
        return self._c._get(f"/sessions/{session_id}/")


class OpsNamespace:
    def __init__(self, client: ThinkClient) -> None:
        self._c = client

    def execute(self, payload: Union[RelayPayload, Dict[str, Any]]) -> RelayResponse:
        data = payload if isinstance(payload, dict) else payload.__dict__
        clean = {k: v for k, v in data.items() if v is not None}
        res = self._c._post("/ops/execute/", clean)
        return RelayResponse(
            status=res.get("status", "ok"),
            text=res.get("text"),
            embeddings=res.get("embeddings"),
            usage=res.get("usage", {}),
            mocked=res.get("mocked", False),
        )


class ModulesNamespace:
    def __init__(self, client: ThinkClient) -> None:
        self._c = client

    def publish(self, payload: Union[ModulePublishPayload, Dict[str, Any]]) -> ModuleRecord:
        data = payload if isinstance(payload, dict) else payload.__dict__
        clean = {k: v for k, v in data.items() if v is not None}
        res = self._c._post("/modules/", clean)
        return ModuleRecord(
            id=res.get("id", ""),
            status=res.get("status", "published"),
            version_id=res.get("version_id"),
            source_manifest=res.get("source_manifest"),
            template_version=res.get("template_version"),
        )

    def list(self) -> List[ModuleSummary]:
        res = self._c._get("/modules/")
        items = res if isinstance(res, list) else res.get("items", [])
        return [
            ModuleSummary(
                id=item.get("id", ""),
                name=item.get("name", ""),
                version=item.get("version", ""),
                status=item.get("status", "active"),
            )
            for item in items
        ]

    def get(self, module_id: str) -> ModuleRecord:
        res = self._c._get(f"/modules/{module_id}/")
        return ModuleRecord(
            id=res.get("id", module_id),
            status=res.get("status", "active"),
            version_id=res.get("version_id"),
            source_manifest=res.get("source_manifest"),
            template_version=res.get("template_version"),
        )

    def retire(self, module_id: str, version_id: str) -> RetireReceipt:
        res = self._c._post(f"/modules/{module_id}/versions/{version_id}/retire/", {})
        return RetireReceipt(
            module_id=module_id,
            version_id=version_id,
            retired=res.get("retired", True),
        )


class AnalyticsNamespace:
    def __init__(self, client: ThinkClient) -> None:
        self._c = client

    def get_run(self, run_id: str) -> RunAnalytics:
        self._c._require_cloud("analytics.get_run")
        res = self._c._get(f"/api/v1/analytics/runs/{run_id}/")
        return RunAnalytics(
            run_id=res.get("run_id", run_id),
            total_steps=res.get("total_steps", 0),
            duration_ms=res.get("duration_ms", 0.0),
            credits_used=res.get("credits_used", 0.0),
            audit_events=res.get("audit_events", []),
        )


class StorageNamespace:
    def __init__(self, client: ThinkClient) -> None:
        self._c = client

    def upload(self, content: str, filename: str = "asset") -> StorageDescriptor:
        self._c._require_cloud("storage.upload")
        res = self._c._post("/api/v1/storage/upload/", {"content": content, "filename": filename})
        return StorageDescriptor(
            ref=res.get("ref", ""),
            url=res.get("url"),
            filename=res.get("filename"),
        )

    def get_url(self, ref: str) -> StorageDescriptor:
        self._c._require_cloud("storage.get_url")
        res = self._c._get(f"/api/v1/storage/{ref}/")
        return StorageDescriptor(
            ref=res.get("ref", ref),
            url=res.get("url"),
            filename=res.get("filename"),
        )


class ThinkClient:
    """Unified Python client for Thinkument Local Studio ($0.00) or Sovereign Cloud."""

    def __init__(self, endpoint: Optional[str] = None, api_key: Optional[str] = None) -> None:
        if endpoint is None:
            endpoint = os.environ.get("THINKUMENT_BASE_URL", "http://localhost:5052")
        if api_key is None:
            api_key = os.environ.get("THINKUMENT_API_KEY")
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.session = SessionNamespace(self)
        self.ops = OpsNamespace(self)
        self.modules = ModulesNamespace(self)
        self.analytics = AnalyticsNamespace(self)
        self.storage = StorageNamespace(self)

    @classmethod
    def local(cls, port: int = 5052, host: str = "localhost") -> ThinkClient:
        return cls(endpoint=f"http://{host}:{port}")

    @classmethod
    def connect(cls, api_key: Optional[str] = None, endpoint: str = "https://api.thinkument.com") -> ThinkClient:
        key = api_key or os.environ.get("THINKUMENT_API_KEY", "").strip()
        if not key:
            raise ValueError(
                "THINKUMENT_API_KEY is required to connect to Thinkument Sovereign Cloud. "
                "Supply api_key='tk_live_...' or set export THINKUMENT_API_KEY=..."
            )
        return cls(endpoint=endpoint, api_key=key)

    def _require_cloud(self, op: str) -> None:
        if not self.api_key:
            raise CloudServiceRequiredError(f"{op} requires Thinkument Sovereign Cloud credentials")

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get(self, path: str) -> Any:
        url = f"{self.endpoint}{path}"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if resp.status_code >= 400:
            if resp.status_code == 409:
                raise ConcurrencyConflictError(resp.text)
            raise ThinkumentError(f"HTTP {resp.status_code}: {resp.text}")
        return resp.json()

    def _post(self, path: str, json_data: Dict[str, Any]) -> Any:
        url = f"{self.endpoint}{path}"
        resp = requests.post(url, json=json_data, headers=self._headers(), timeout=30)
        if resp.status_code >= 400:
            if resp.status_code == 409:
                raise ConcurrencyConflictError(resp.text)
            raise ThinkumentError(f"HTTP {resp.status_code}: {resp.text}")
        return resp.json()

    def healthz(self) -> HealthzResponse:
        res = self._get("/healthz")
        return HealthzResponse(
            status=res.get("status", "ok"),
            version=res.get("version", "1.0.0"),
        )
