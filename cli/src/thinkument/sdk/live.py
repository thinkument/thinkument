"""Live collaborative session namespace for ThinkClient."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from thinkument.sdk.session import ActiveSession


@dataclass(frozen=True)
class RoleHandle:
    role: str
    slug: str
    url: str
    path: str


@dataclass(frozen=True)
class LiveSessionHandle:
    session_id: str
    starter_id: str
    public_view_role: Optional[str]
    selected: RoleHandle
    handles: Dict[str, RoleHandle]
    analytics: Dict[str, str]
    launch_state: Dict[str, Any]
    _base_url: str
    _api_key: Optional[str] = None

    def connect(self, role: Optional[str] = None) -> ActiveSession:
        """Connect a programmatic poller-dispatcher to this live session."""
        effective_role = role or self.public_view_role or "default"
        slug = self.handles[effective_role].slug if effective_role in self.handles else self.selected.slug
        return ActiveSession(
            base_url=self._base_url,
            session_id=self.session_id,
            role=effective_role,
            slug=slug,
            api_key=self._api_key,
        )


@dataclass(frozen=True)
class EmbedHandle:
    session_id: str
    url: str
    snippet_html: str


class LiveNamespace:
    """Manages hosted live sessions, iframe embeds, and collaborative connections."""

    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

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
                msg = err_json.get("error") or err_body
            except Exception:
                msg = err_body
            raise RuntimeError(f"HTTP {exc.code} on {path}: {msg}") from exc

    def create(
        self,
        P: Mapping[str, Any],
        SM: Optional[Mapping[str, Any]] = None,
        C: Optional[Mapping[str, Any]] = None,
        *,
        roles: Optional[Mapping[str, Any]] = None,
        public_view_role: Optional[str] = None,
        opinionation_module: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> LiveSessionHandle:
        """Create a hosted live collaborative session with role-sealed URLs."""
        # Convenience: unpack if a combined PSMC dictionary is supplied
        if isinstance(P, Mapping) and "P" in P and SM is None and C is None:
            actual_P = P["P"]
            actual_SM = P.get("SM")
            actual_C = P.get("C")
        else:
            actual_P = P
            actual_SM = SM
            actual_C = C

        payload: Dict[str, Any] = {
            "P": dict(actual_P),
            "SM": dict(actual_SM or {}),
            "C": dict(actual_C or {}),
        }
        if roles:
            payload["roles"] = dict(roles)
        if public_view_role:
            payload["public_view_role"] = public_view_role
        if opinionation_module:
            payload["opinionation_module"] = opinionation_module
        if metadata:
            payload["metadata"] = dict(metadata)

        raw = self._request("POST", "/api/v1/sessions/", payload)

        sel = raw.get("selected") or {}
        selected_handle = RoleHandle(
            role=sel.get("role", "default"),
            slug=sel.get("slug", ""),
            url=sel.get("url", ""),
            path=sel.get("path", ""),
        )

        handles = {}
        for r_name, r_dict in (raw.get("handles") or {}).items():
            handles[r_name] = RoleHandle(
                role=r_dict.get("role", r_name),
                slug=r_dict.get("slug", ""),
                url=r_dict.get("url", ""),
                path=r_dict.get("path", ""),
            )

        return LiveSessionHandle(
            session_id=str(raw["session_id"]),
            starter_id=str(raw.get("starter_id", "")),
            public_view_role=raw.get("public_view_role"),
            selected=selected_handle,
            handles=handles,
            analytics=raw.get("analytics") or {},
            launch_state=raw.get("launch_state") or {},
            _base_url=self.base_url,
            _api_key=self.api_key,
        )

    def create_embed(
        self,
        P: Mapping[str, Any],
        SM: Optional[Mapping[str, Any]] = None,
        C: Optional[Mapping[str, Any]] = None,
        *,
        allowed_origins: Optional[List[str]] = None,
        theme: str = "light",
        public_view_role: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> EmbedHandle:
        """Create a responsive enterprise iframe embed for an interactive session."""
        meta = dict(metadata or {})
        meta["embed"] = {
            "allowed_origins": allowed_origins or ["*"],
            "theme": theme,
        }
        handle = self.create(
            P=P,
            SM=SM,
            C=C,
            public_view_role=public_view_role,
            metadata=meta,
        )
        embed_url = f"{handle.selected.url}&embed=1&theme={theme}"
        snippet = (
            f'<iframe src="{embed_url}" width="100%" height="600" '
            f'frameborder="0" allow="clipboard-write" allowfullscreen></iframe>'
        )
        return EmbedHandle(
            session_id=handle.session_id,
            url=embed_url,
            snippet_html=snippet,
        )

    def connect(self, slug: str, role: Optional[str] = None) -> ActiveSession:
        """Connect directly to an existing session via its role slug."""
        return ActiveSession(
            base_url=self.base_url,
            session_id=slug.split("_")[0] if "_" in slug else slug,
            role=role,
            slug=slug,
            api_key=self.api_key,
        )
