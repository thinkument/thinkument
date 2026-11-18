"""Modules namespace for publishing, discovering, and retiring Thinkument Modules (think_module_v1)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Optional

from thinkument.sdk.errors import CloudServiceRequiredError
from thinkument.sdk.session import ActiveSession


class ModulesNamespace:
    """Manage published (P x C) modules across local in-memory catalog or Sovereign Cloud."""

    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._is_local = "localhost" in self.base_url or "127.0.0.1" in self.base_url

    def _require_cloud(self, operation: str) -> None:
        if self._is_local and not self.api_key:
            raise CloudServiceRequiredError(operation)

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("error") or err_json.get("detail") or err_body
            except Exception:
                msg = err_body
            raise RuntimeError(f"HTTP {exc.code} on {path}: {msg}") from exc

    def publish(self, manifest: Mapping[str, Any], idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """Publish a think_module_v1 manifest to the cloud catalog."""
        self._require_cloud("modules.publish")
        payload = {"manifest": dict(manifest), "authoring_template_version": "v1"}
        return self._request("POST", "/api/v1/modules/", payload)

    def get(self, module_id: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve a published module by ID and optional version."""
        path = f"/api/v1/modules/{module_id}/"
        if version:
            path += f"versions/{version}/"
        return self._request("GET", path)

    def list(self, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """List published modules from the catalog."""
        path = "/api/v1/module-catalog/"
        if query:
            path += f"?search={urllib.request.quote(query)}"
        resp = self._request("GET", path)
        return resp.get("results", []) if isinstance(resp, dict) else resp

    def retire(self, module_id: str, version: str, reason: str = "") -> Dict[str, Any]:
        """Retire a published module version."""
        self._require_cloud("modules.retire")
        path = f"/api/v1/modules/{module_id}/versions/{version}/retire/"
        return self._request("POST", path, {"reason": reason})

    def launch(
        self,
        module_id: str,
        parameters: Optional[Mapping[str, Any]] = None,
        session_metadata: Optional[Mapping[str, Any]] = None,
    ) -> ActiveSession:
        """Launch a live collaborative session from a published module."""
        payload = {
            "module_id": module_id,
            "C": dict(parameters or {}),
            "SM": dict(session_metadata or {}),
        }
        resp = self._request("POST", "/api/v1/sessions/", payload)
        session_id = resp.get("session_id", "")
        return ActiveSession(
            base_url=self.base_url,
            session_id=session_id,
            role="default",
            api_key=self.api_key,
        )
