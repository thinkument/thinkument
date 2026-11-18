"""The official unified ThinkClient for local and sovereign cloud Thinkument operations."""
from __future__ import annotations

import os
from typing import Optional

from thinkument.sdk.analytics import AnalyticsNamespace
from thinkument.sdk.blackbox import BlackBoxNamespace
from thinkument.sdk.catalogue import CatalogueNamespace
from thinkument.sdk.economics import EconomicsNamespace
from thinkument.sdk.errors import CloudServiceRequiredError, ConcurrencyConflictError, ThinkumentError
from thinkument.sdk.live import LiveNamespace
from thinkument.sdk.modules import ModulesNamespace
from thinkument.sdk.ops import OpsNamespace
from thinkument.sdk.storage import StorageNamespace


class ThinkClient:
    """Unified client for interacting with Thinkument Local Studio or Sovereign Cloud."""

    def __init__(self, endpoint: str, api_key: Optional[str] = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key

        self.live = LiveNamespace(self.endpoint, self.api_key)
        self.blackbox = BlackBoxNamespace(self.endpoint, self.api_key)
        self.ops = OpsNamespace(self.endpoint, self.api_key)
        self.modules = ModulesNamespace(self.endpoint, self.api_key)
        self.catalogue = CatalogueNamespace(self.endpoint, self.api_key)
        self.analytics = AnalyticsNamespace(self.endpoint, self.api_key)
        self.storage = StorageNamespace(self.endpoint, self.api_key)
        self.economics = EconomicsNamespace(self.endpoint, self.api_key)

    @classmethod
    def local(cls, port: int = 5052, host: str = "localhost") -> ThinkClient:
        """Connect to the local in-memory studio daemon on http://localhost:5052 ($0.00, 100% offline)."""
        return cls(endpoint=f"http://{host}:{port}")

    @classmethod
    def connect(cls, api_key: Optional[str] = None, endpoint: str = "https://api.thinkument.com") -> ThinkClient:
        """Connect to Thinkument Sovereign Cloud via API key."""
        key = api_key or os.environ.get("THINKUMENT_API_KEY", "").strip()
        if not key:
            raise ValueError(
                "THINKUMENT_API_KEY is required to connect to Thinkument Sovereign Cloud. "
                "Supply api_key='tk_live_...' or set export THINKUMENT_API_KEY=..."
            )
        return cls(endpoint=endpoint, api_key=key)
