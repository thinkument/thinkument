"""Stateless cloud operations relay namespace for ThinkClient."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Mapping, Optional


class OpsNamespace:
    """Dispatches stateless vendor operations directly through Thinkument's relay seam."""

    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def execute(
        self,
        envelope_or_op: Mapping[str, Any] | str | None = None,
        args: Optional[Mapping[str, Any]] = None,
        *,
        operation: Optional[str] = None,
        fn: Optional[str] = None,
        modality: str = "general",
        call_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a single vendor/cognitive operation without persisting database session rows."""
        target_op = operation or fn or (envelope_or_op if isinstance(envelope_or_op, str) else None)
        if isinstance(envelope_or_op, Mapping):
            payload = dict(envelope_or_op)
            if "operation" not in payload and "fn" in payload:
                payload["operation"] = payload["fn"]
        else:
            payload = {
                "operation": str(target_op or "vendor_op"),
                "args": dict(args or {}),
                "modality": modality,
            }
            if call_key:
                payload["call_key"] = call_key

        url = f"{self.base_url}/api/v1/ops/execute/"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("error") or err_body
            except Exception:
                msg = err_body
            raise RuntimeError(f"HTTP {exc.code} on /api/v1/ops/execute/: {msg}") from exc
