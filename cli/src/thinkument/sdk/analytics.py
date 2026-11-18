"""Analytics namespace for querying historical runs and durable epsilon/theta event streams."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from thinkument.sdk.errors import CloudServiceRequiredError


class AnalyticsNamespace:
    """Access durable audit trails and historical run analytics in Thinkument Sovereign Cloud."""

    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._is_local = "localhost" in self.base_url or "127.0.0.1" in self.base_url

    def _require_cloud(self, operation: str) -> None:
        if self._is_local and not self.api_key:
            raise CloudServiceRequiredError(operation)

    def _request(self, method: str, path: str) -> Any:
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            raise RuntimeError(f"HTTP {exc.code} on {path}: {err_body}") from exc

    def list_runs(self, limit: int = 25) -> List[Dict[str, Any]]:
        """List historical run records across the caller's account."""
        self._require_cloud("analytics.list_runs")
        resp = self._request("GET", f"/api/v1/analytics/runs/?limit={limit}")
        return resp.get("results", []) if isinstance(resp, dict) else resp

    def get_messages(self, run_id: str, after_seq: int = 0) -> List[Dict[str, Any]]:
        """Query durable audit and telemetry messages for a specific run."""
        self._require_cloud("analytics.get_messages")
        resp = self._request("GET", f"/api/v1/analytics/?run_id={run_id}&after_seq={after_seq}")
        return resp.get("messages", []) if isinstance(resp, dict) else resp
