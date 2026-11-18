"""Economics and wallet credits namespace for ThinkClient."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class WalletBalance:
    available_credits: int
    currency: str = "microcredits"


class EconomicsNamespace:
    """Queries prepaid wallet microcredit balances and billing reservations."""

    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def get_balance(self) -> WalletBalance:
        """Introspect current available prepaid microcredits."""
        url = f"{self.base_url}/api/v1/wallet/balance/"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return WalletBalance(
                    available_credits=data.get("available_credits", 0),
                    currency=data.get("currency", "microcredits"),
                )
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            raise RuntimeError(f"HTTP {exc.code} on wallet balance: {err_body}") from exc
