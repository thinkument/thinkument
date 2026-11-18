"""ActiveSession poller-dispatcher manager for programmatic session participation."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Generator, List, Mapping, Optional


@dataclass(frozen=True)
class ThetaEvent:
    event_seq: int
    name: str
    kind: str
    data: Dict[str, Any]

    @property
    def event_kind(self) -> str:
        return self.name or self.kind

    @property
    def is_step_done(self) -> bool:
        return "step" in self.event_kind.lower() or "done" in self.event_kind.lower()

    @property
    def step_index(self) -> Optional[int]:
        cursor = self.data.get("cursor") or (self.data.get("payload", {}).get("U", {}).get("cursor") or {})
        return cursor.get("index")


@dataclass(frozen=True)
class DispatchOutcome:
    ok: bool
    status: str
    step_index: Optional[int]
    receipt: Dict[str, Any]


@dataclass(frozen=True)
class TridentTape:
    session_id: str
    events: List[Dict[str, Any]]
    latest_event_seq: int


class ActiveSession:
    """Headless programmatic poller-dispatcher for interacting with an active Thinkument session."""

    def __init__(
        self,
        base_url: str,
        session_id: str,
        role: Optional[str] = None,
        slug: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id
        self.role = role
        self.slug = slug
        self.api_key = api_key
        self._latest_event_seq: int = 0
        self._last_poll_seq: int = 0

    @property
    def latest_event_seq(self) -> int:
        return self._latest_event_seq

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

    def dispatch(
        self,
        action: str = "STEP",
        user_fill: Optional[Mapping[str, Any]] = None,
        user_signal: Optional[Mapping[str, Any]] = None,
        cursor: Optional[int] = None,
        identity_id: Optional[str] = None,
        *,
        widget: Optional[str] = None,
        fill: Optional[Mapping[str, Any]] = None,
        signal: Optional[Mapping[str, Any]] = None,
    ) -> DispatchOutcome:
        """Dispatch action/fill/signal with optimistic concurrency cursor.
        
        Convenience: supply widget and fill (e.g. dispatch(widget='editor', fill={'text': 'Draft'}))
        """
        effective_cursor = self._latest_event_seq if cursor is None else cursor
        payload = {
            "action": action,
            "role": self.role,
            "cursor": effective_cursor,
            "my_current_event_seq_number": effective_cursor,
        }
        effective_fill = dict(user_fill or {})
        if fill is not None:
            if widget:
                effective_fill[widget] = dict(fill)
            else:
                effective_fill.update(fill)
        if effective_fill:
            payload["user_fill"] = effective_fill

        effective_signal = dict(user_signal or {})
        if signal is not None:
            if widget:
                effective_signal[widget] = dict(signal)
            else:
                effective_signal.update(signal)
        if effective_signal:
            payload["user_signal"] = effective_signal

        if identity_id:
            payload["identity_id"] = identity_id

        receipt = self._request("POST", f"/api/v1/sessions/{self.session_id}/dispatch/", payload)
        concurrency = receipt.get("dispatch_concurrency") or {}
        after_seq = concurrency.get("after_event_seq")
        if after_seq is not None:
            self._latest_event_seq = max(self._latest_event_seq, int(after_seq))

        ctx_report = receipt.get("ctx_report") or {}
        step_idx = (ctx_report.get("cursor") or {}).get("index")
        return DispatchOutcome(
            ok=bool(receipt.get("ok", True)),
            status=receipt.get("dispatch_outcome", "applied"),
            step_index=step_idx,
            receipt=receipt,
        )

    def get_state(self) -> Dict[str, Any]:
        """Fetch current rendered state for this session/role."""
        role_param = f"?role={self.role}" if self.role else ""
        return self._request("GET", f"/api/v1/sessions/{self.session_id}/{role_param}")

    @property
    def state(self) -> Dict[str, Any]:
        """Current rendered state for this active session."""
        return self.get_state()

    @property
    def events(self) -> List[ThetaEvent]:
        """All theta events emitted since session launch."""
        return self.get_events(after_seq=0)

    def display(self) -> Any:
        """Display interactive UI shell in Jupyter Notebook, or format neatly in terminal."""
        s = self.state
        try:
            import IPython.display as ipyd
            step_id = s.get("current_step_id", s.get("step_index", 0))
            html = f"""
            <div style="border: 1px solid #d0d7de; border-radius: 6px; padding: 14px; font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif; background: #f6f8fa;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-weight: 600; font-size: 14px;">⚡ ThinkSession: <code>{self.session_id}</code></span>
                    <span style="background: #0969da; color: #ffffff; padding: 2px 8px; border-radius: 12px; font-size: 11px;">Role: {self.role or 'default'}</span>
                </div>
                <div style="font-size: 12px; color: #57606a; margin-bottom: 10px;">
                    <strong>Step:</strong> <code>{step_id}</code> | <strong>Events:</strong> {self.latest_event_seq}
                </div>
                <pre style="background: #ffffff; padding: 10px; border-radius: 6px; border: 1px solid #d0d7de; max-height: 240px; overflow: auto; font-size: 11px; margin: 0;">{json.dumps(s, indent=2)}</pre>
            </div>
            """
            return ipyd.display(ipyd.HTML(html))
        except (ImportError, Exception):
            print(f"\n⚡ ThinkSession {self.session_id} (Role: {self.role or 'default'})")
            print(json.dumps(s, indent=2))
            return None

    def get_events(self, after_seq: Optional[int] = None) -> List[ThetaEvent]:
        """Fetch list of events emitted since after_seq."""
        effective_after = self._last_poll_seq if after_seq is None else after_seq
        role_param = f"&role={self.role}" if self.role else ""
        data = self._request("GET", f"/api/v1/sessions/{self.session_id}/events/?after_seq={effective_after}{role_param}")
        raw_events = data.get("events") or []
        parsed = []
        for ev in raw_events:
            seq = ev.get("event_seq", 0)
            self._latest_event_seq = max(self._latest_event_seq, seq)
            self._last_poll_seq = max(self._last_poll_seq, seq)
            parsed.append(ThetaEvent(
                event_seq=seq,
                name=ev.get("name") or ev.get("kind") or "event",
                kind=ev.get("kind") or "event",
                data=ev,
            ))
        return parsed

    def stream_events(self, poll_interval: float = 0.1) -> Generator[ThetaEvent, None, None]:
        """Poll and stream new theta events continuously."""
        while True:
            new_events = self.get_events()
            for ev in new_events:
                yield ev
                if ev.event_kind == "ATCOMPLETION":
                    return
            time.sleep(poll_interval)

    def get_tape(self) -> TridentTape:
        """Fetch complete immutable event ledger."""
        data = self._request("GET", f"/api/v1/sessions/{self.session_id}/events/?after_seq=0")
        events = data.get("events") or []
        return TridentTape(
            session_id=self.session_id,
            events=events,
            latest_event_seq=self._latest_event_seq,
        )

    def close(self) -> Dict[str, Any]:
        """Terminate and clean up session."""
        return self._request("DELETE", f"/api/v1/sessions/{self.session_id}/")
