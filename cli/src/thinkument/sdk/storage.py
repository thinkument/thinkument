"""Storage namespace for uploading and resolving binary assets in Thinkument Storagics."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from thinkument.sdk.errors import CloudServiceRequiredError


class StorageNamespace:
    """Upload and retrieve durable binary assets backed by AWS S3 / Linode Object Storage."""

    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._is_local = "localhost" in self.base_url or "127.0.0.1" in self.base_url

    def _require_cloud(self, operation: str) -> None:
        if self._is_local and not self.api_key:
            raise CloudServiceRequiredError(operation)

    def upload(self, data: bytes | str, filename: Optional[str] = None) -> Dict[str, Any]:
        """Upload binary data and receive a durable Storagics descriptor (ref and url)."""
        self._require_cloud("storage.upload")
        payload = {
            "content": data.decode("latin1") if isinstance(data, bytes) else str(data),
            "filename": filename or "asset.bin",
        }
        url = f"{self.base_url}/api/v1/storage/upload/"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Storage upload failed: {exc.read().decode('utf-8')}") from exc

    def get_url(self, ref: str) -> str:
        """Resolve a storage reference into an authorized public CDN download URL."""
        return f"{self.base_url}/storage/{ref}/"
