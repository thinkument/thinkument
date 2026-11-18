from __future__ import annotations

"""Reusable stateful Python frontend for dry-run server strategies.

This module is deliberately *not* a Flask strategy and not a Django strategy.
It models the client-side half that both server strategies share.

The standard dry-run language remains P / SM / C / A / E. A concrete
``BaseDryRunStrategy`` still owns lambda/gamma/gamma_f/epsilon/theta/Q/U/omega.
This module simply provides a reusable implementation of those spaces for the
case where the chosen execution lens contains a stateful frontend process in
front of a role-sealed JSON/HTTP server.

Task-F client law
-----------------
A ``PythonFrontendProcessV1`` is a logical frontend process, not an operating
system subprocess. The server-observable process identity is the stable
``identity_id`` bound to one role.

For one frontend session:

* every distinct role has exactly one stable process identity;
* role=None has its own privileged process when the host exposes that lens;
* the session remembers the greatest canonical high-water it has observed;
* a role client performs theta HTTP work only when its local cursor is behind
  that known high-water;
* canonical controller theta updates the client's local projected U, so a
  successful dispatch does not immediately re-fetch `/context`;
* `/context` remains the bootstrap/fallback path before canonical U exists;
* epsilon polling sleeps before the first in-flight GET, so a fast dispatch
  usually costs one terminal drain rather than an eager empty read plus a
  final read;
* a terminal progress page is final, and a short nonterminal page returns to
  cadence rather than immediately busy-polling again;
* after an admitted dispatch, every roleful epsilon event must reconcile
  exactly, in order, with role-projected canonical theta after removing only
  canonical ``event_seq``;
* the dry-run proof observer, when configured, remains a separate privileged
  observation lens for P13's stronger unmodulated epsilon proof.

The known-high-water optimization is deterministic for these dry-run sheets:
all mutations are initiated by the same frontend session, and their receipts or
pages reveal the resulting canonical head. A real independently-running client
would additionally maintain background polling or a push transport.
"""

import builtins
import json
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Dict, Mapping, Optional
from urllib.error import HTTPError as UrlHTTPError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from ways_to_run.dry_run_examples.dry_run_adapter_strategies.BASE_CLASS import (
    BaseDryRunStrategy,
    DryRunLiveEventSinkV1,
    DryRunRunHandleV1,
)
from ways_to_run.dry_run_examples.dry_run_standard_lingo.protocol_v1 import (
    assert_standard_event_v1,
)


DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_PROGRESS_POLL_SECONDS = 0.025
DEFAULT_EVENT_PAGE_SIZE = 500
DEFAULT_PROGRESS_PAGE_SIZE = 500

_SERVER_ONLY_TOP_LEVEL_RECEIPT_KEYS = frozenset({"request_id"})
_SERVER_ONLY_CONCURRENCY_KEYS = frozenset(
    {
        "coordination_layer",
        "reason",
        "request_id",
    }
)
_TERMINAL_PROGRESS_STATES = frozenset({"committed", "aborted"})


@dataclass(frozen=True, slots=True)
class PythonFrontendEndpointSetV1:
    context: str
    latest_event_seq: str
    events: str
    dispatch_progress: str
    dispatch: str
    dispatch_funked: str

    @classmethod
    def from_mapping_v1(
        cls,
        value: Mapping[str, Any],
    ) -> "PythonFrontendEndpointSetV1":
        required = {
            "context",
            "latestEventSeq",
            "events",
            "dispatch",
            "dispatchFunked",
        }
        eps_key = "eps" if "eps" in value else ("dispatchProgress" if "dispatchProgress" in value else None)
        if not eps_key:
            required.add("eps")
        missing = required - set(value)
        if missing:
            raise ValueError(
                "frontend endpoint set is missing required endpoint(s): "
                f"{sorted(missing)}"
            )

        return cls(
            context=str(value["context"]),
            latest_event_seq=str(value["latestEventSeq"]),
            events=str(value["events"]),
            dispatch_progress=str(value[eps_key]),
            dispatch=str(value["dispatch"]),
            dispatch_funked=str(value["dispatchFunked"]),
        )


@dataclass(slots=True)
class PythonFrontendBackendRunV1:
    """Server-hosted run information required by the reusable frontend."""

    base_url: str
    session_id: str
    endpoints_by_role: Dict[Optional[str], PythonFrontendEndpointSetV1]
    proof_obweb_RESTful: PythonFrontendEndpointSetV1
    host_resource: Any = None


@dataclass(frozen=True, slots=True)
class PythonFrontendHTTPResultV1:
    status: int
    packet: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class PythonFrontendDispatchObservationV1:
    request_id: str
    role: Optional[str]
    identity_id: str
    response: PythonFrontendHTTPResultV1
    role_epsilon: tuple[Mapping[str, Any], ...]
    proof_epsilon: tuple[Mapping[str, Any], ...]
    role_progress_state: str
    role_progress_error: Optional[str]
    proof_progress_state: str
    proof_progress_error: Optional[str]


@dataclass(slots=True)
class PythonFrontendRunV1:
    backend: PythonFrontendBackendRunV1
    frontend: "PythonFrontendSessionV1"


def _normalized_role(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _without_event_seq_v1(event: Mapping[str, Any]) -> Dict[str, Any]:
    out = deepcopy(dict(event))
    out.pop("event_seq", None)
    return out


def _targets_v1(A: Mapping[str, Any]) -> list[str]:
    out: list[str] = []

    fill = A.get("user_fill")
    if isinstance(fill, Mapping):
        out.extend(str(key).split(".", 1)[0] for key in fill)

    signal = A.get("user_signal")
    if isinstance(signal, Mapping) and signal.get("datum_id"):
        out.append(str(signal["datum_id"]))

    return list(dict.fromkeys(target for target in out if target))


def invalid_event_cursor_packet_v1(
    *,
    session_id: str,
    observed_event_seq: int,
    A: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "kind": "live_session_dispatch_rejected_v1",
        "ok": False,
        "applied": False,
        "rejected": True,
        "rejection_kind": "invalid_event_cursor",
        "dispatch_outcome": "stale_rejected",
        "write_committed": False,
        "events_only": False,
        "session_id": str(session_id),
        "dispatch_staleness": {
            "kind": "live_session_dispatch_staleness_receipt_v1",
            "checked": True,
            "outcome": "rejected",
            "reason": "invalid_event_cursor",
            "supplied_event_seq": None,
            "observed_event_seq": int(observed_event_seq),
            "scope_last_changed_seq": 0,
            "target_last_changed_seq": 0,
            "target_count": len(_targets_v1(A)),
        },
    }


def normalize_harmonized_server_receipt_v1(
    packet: Mapping[str, Any],
) -> Dict[str, Any]:
    """Remove hosting-only receipt facts from the standard dry-run surface."""
    out = deepcopy(dict(packet))

    for key in _SERVER_ONLY_TOP_LEVEL_RECEIPT_KEYS:
        out.pop(key, None)

    rejected = out.get("rejected") is True
    out["kind"] = (
        "live_session_dispatch_rejected_v1"
        if rejected
        else "live_session_dispatch_result_v1"
    )
    out["events_only"] = False

    if rejected:
        out.pop("dispatch_concurrency", None)
        return out

    concurrency = out.get("dispatch_concurrency")
    if isinstance(concurrency, Mapping):
        normalized = deepcopy(dict(concurrency))
        for key in _SERVER_ONLY_CONCURRENCY_KEYS:
            normalized.pop(key, None)
        normalized["guarding"] = (
            "per_session_serialized_highest_facade"
        )
        out["dispatch_concurrency"] = normalized

    return out


def remote_exception_type_v1(name: str) -> type[Exception]:
    candidate = getattr(builtins, str(name), None)
    if isinstance(candidate, type) and issubclass(candidate, Exception):
        return candidate

    for module_name in ("__exceptions.engine", "__exceptions"):
        try:
            candidate = getattr(import_module(module_name), str(name), None)
        except Exception:
            continue
        if isinstance(candidate, type) and issubclass(candidate, Exception):
            return candidate

    return type(str(name or "RemoteDryRunError"), (RuntimeError,), {})


def raise_remote_exception_text_v1(raw_error: str) -> None:
    text = str(raw_error or "").strip()
    if not text:
        raise RuntimeError("remote dispatch failed")

    if ":" in text:
        name, message = text.split(":", 1)
        name = name.strip()
        message = message.strip()
    else:
        name = "RemoteDryRunError"
        message = text

    exc_type = remote_exception_type_v1(name)
    try:
        exc = exc_type(message)
    except Exception:
        exc = type(name, (RuntimeError,), {})(message)
    raise exc


def raise_remote_exception_packet_v1(
    packet: Mapping[str, Any],
    *,
    default_name: str = "RemoteDryRunError",
) -> None:
    name = str(packet.get("exception_type") or default_name)
    message = str(packet.get("message") or "remote dispatch failed")
    exc_type = remote_exception_type_v1(name)
    try:
        exc = exc_type(message)
    except Exception:
        exc = type(name, (RuntimeError,), {})(message)
    raise exc


class RoleSealedJsonHTTPPortV1(ABC):
    """Reusable client-side port for role-sealed Thinkument HTTP surfaces."""

    def __init__(
        self,
        *,
        backend: PythonFrontendBackendRunV1,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        parsed = urlsplit(str(backend.base_url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("backend.base_url must be an absolute HTTP URL")

        timeout = float(request_timeout_seconds)
        if timeout <= 0:
            raise ValueError("request_timeout_seconds must be > 0")

        self.backend = backend
        self.request_timeout_seconds = timeout

    def _http_v1(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
    ) -> PythonFrontendHTTPResultV1:
        url = urljoin(
            f"{self.backend.base_url.rstrip('/')}/",
            str(path).lstrip("/"),
        )
        if query:
            url = f"{url}?{urlencode(dict(query), doseq=True)}"

        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(
                dict(payload),
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(
                request,
                timeout=self.request_timeout_seconds,
            ) as response:
                status = int(response.status)
                raw = response.read()
        except UrlHTTPError as exc:
            status = int(exc.code)
            raw = exc.read()

        text = raw.decode("utf-8", errors="replace") if raw else ""
        try:
            parsed = json.loads(text) if text else {}
        except Exception:
            parsed = {"raw_text": text}

        return PythonFrontendHTTPResultV1(
            status=status,
            packet=(
                dict(parsed)
                if isinstance(parsed, Mapping)
                else {"value": parsed}
            ),
        )

    def _endpoints_v1(
        self,
        role: Optional[str],
    ) -> PythonFrontendEndpointSetV1:
        key = _normalized_role(role)
        try:
            return self.backend.endpoints_by_role[key]
        except KeyError as exc:
            raise KeyError(
                f"no frontend server capability for role {key!r}"
            ) from exc

    @abstractmethod
    def latest_event_seq_from_packet_v1(
        self,
        packet: Mapping[str, Any],
    ) -> int:
        raise NotImplementedError

    def latest_event_seq_v1(self) -> int:
        result = self._http_v1(
            self.backend.proof_obweb_RESTful.latest_event_seq,
        )
        if result.status != 200:
            raise AssertionError(
                "frontend latest-event read failed: "
                f"{result.status} {result.packet!r}"
            )
        return int(self.latest_event_seq_from_packet_v1(result.packet))

    def read_context_v1(
        self,
        *,
        role: Optional[str],
    ) -> Mapping[str, Any]:
        result = self._http_v1(
            self._endpoints_v1(role).context,
        )
        if (
            result.status != 200
            or not isinstance(result.packet.get("ctx"), Mapping)
        ):
            raise AssertionError(
                "frontend context read failed: "
                f"{result.status} {result.packet!r}"
            )
        return deepcopy(dict(result.packet["ctx"]))

    @staticmethod
    def _merge_ranges_v1(
        rows: list[Mapping[str, Any]],
    ) -> list[Dict[str, int]]:
        if not rows:
            return []

        pairs = sorted(
            (
                int(row["from_event_seq"]),
                int(row["to_event_seq"]),
            )
            for row in rows
        )
        merged: list[list[int]] = []
        for start, end in pairs:
            if not merged or start > merged[-1][1] + 1:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)

        return [
            {"from_event_seq": start, "to_event_seq": end}
            for start, end in merged
        ]

    def poll_committed_events_v1(
        self,
        *,
        role: Optional[str],
        identity_id: str,
        after_event_seq: int,
        limit: Optional[int],
    ) -> Dict[str, Any]:
        endpoints = self._endpoints_v1(role)
        start = cursor = int(after_event_seq)

        if limit is None:
            remaining: Optional[int] = None
        else:
            if isinstance(limit, bool):
                raise TypeError("limit must be an integer, not bool")
            remaining = int(limit)
            if remaining < 0:
                raise ValueError("limit must be >= 0")

        zero_limit = remaining == 0
        pages: list[Dict[str, Any]] = []
        visible: list[Dict[str, Any]] = []
        hidden: list[Mapping[str, Any]] = []

        while True:
            request_limit = (
                1
                if zero_limit
                else min(
                    DEFAULT_EVENT_PAGE_SIZE,
                    remaining or DEFAULT_EVENT_PAGE_SIZE,
                )
            )
            result = self._http_v1(
                endpoints.events,
                query={
                    "identity_id": str(identity_id),
                    "after_event_seq": cursor,
                    "limit": request_limit,
                },
            )
            if result.status != 200:
                raise AssertionError(
                    "frontend events read failed: "
                    f"{result.status} {result.packet!r}"
                )

            page = deepcopy(result.packet)
            pages.append(page)

            if not zero_limit:
                rows = [
                    dict(event)
                    for event in list(page.get("events") or [])
                    if isinstance(event, Mapping)
                ]
                if remaining is not None:
                    rows = rows[:remaining]
                    remaining -= len(rows)
                visible.extend(rows)

                receipt = page.get("visibility_receipt")
                if isinstance(receipt, Mapping):
                    hidden.extend(
                        dict(row)
                        for row in list(
                            receipt.get("hidden_event_seq_ranges") or []
                        )
                        if isinstance(row, Mapping)
                    )

            next_cursor = int(
                page.get("next_after_event_seq") or cursor
            )
            latest = int(
                page.get("session_latest_event_seq") or next_cursor
            )

            if zero_limit:
                cursor = start
                break
            if remaining is not None and remaining <= 0:
                cursor = next_cursor
                break
            if next_cursor <= cursor or next_cursor >= latest:
                cursor = next_cursor
                break

            cursor = next_cursor

        if not pages:
            raise AssertionError("events polling produced no page")

        out = deepcopy(pages[0])
        out["events"] = visible
        out["after_event_seq"] = start
        out["scanned_through_event_seq"] = cursor
        out["next_after_event_seq"] = cursor
        out["session_latest_event_seq"] = int(
            pages[-1].get("session_latest_event_seq") or cursor
        )

        ranges = self._merge_ranges_v1(hidden)
        hidden_count = sum(
            row["to_event_seq"] - row["from_event_seq"] + 1
            for row in ranges
        )
        out["visibility_receipt"] = {
            "kind": "live_session_event_visibility_receipt_v1",
            "role": _normalized_role(role),
            "scanned_from_event_seq_exclusive": start,
            "scanned_through_event_seq": cursor,
            "hidden_event_count": hidden_count,
            "hidden_event_seq_ranges": ranges,
            "reason": "role_projection" if hidden_count else "none",
        }
        return out

    def read_dispatch_progress_v1(
        self,
        *,
        role: Optional[str],
        identity_id: str,
        request_id: str,
        after_provisional_seq: int,
        proof_observer: bool,
    ) -> Dict[str, Any]:
        endpoints = (
            self.backend.proof_obweb_RESTful
            if proof_observer
            else self._endpoints_v1(role)
        )
        result = self._http_v1(
            endpoints.dispatch_progress,
            query={
                "request_id": str(request_id),
                "identity_id": str(identity_id),
                "after_seq": int(after_provisional_seq),
                "after_eps_seq": int(after_provisional_seq),
                "after_provisional_seq": int(after_provisional_seq),
                "limit": DEFAULT_PROGRESS_PAGE_SIZE,
            },
        )
        if result.status != 200:
            raise AssertionError(
                "frontend dispatch-progress read failed: "
                f"{result.status} {result.packet!r}"
            )
        return deepcopy(result.packet)

    def include_role_in_dispatch_payload_v1(self) -> bool:
        return False

    def supports_per_dispatch_chain_config_v1(self) -> bool:
        return False

    def dispatch_query_v1(self) -> Mapping[str, Any]:
        return {}

    def submit_dispatch_v1(
        self,
        *,
        role: Optional[str],
        identity_id: str,
        request_id: str,
        A: Mapping[str, Any],
        funked: bool,
    ) -> PythonFrontendHTTPResultV1:
        endpoints = self._endpoints_v1(role)
        payload: Dict[str, Any] = {
            "action": A.get("action", "STEP"),
            "identity_id": str(identity_id),
            "request_id": str(request_id),
            "my_current_event_seq_number": A.get(
                "my_current_event_seq_number"
            ),
            "user_fill": deepcopy(A.get("user_fill")),
            "user_signal": deepcopy(A.get("user_signal")),
        }

        if self.include_role_in_dispatch_payload_v1():
            payload["role"] = _normalized_role(role)

        if funked and "chainreactionTM_config" in A:
            if not self.supports_per_dispatch_chain_config_v1():
                raise NotImplementedError(
                    "this public server transport does not accept a "
                    "per-dispatch chainreactionTM_config override"
                )
            payload["chainreactionTM_config"] = deepcopy(
                A["chainreactionTM_config"]
            )

        return self._http_v1(
            endpoints.dispatch_funked if funked else endpoints.dispatch,
            method="POST",
            payload=payload,
            query=self.dispatch_query_v1(),
        )

    @abstractmethod
    def normalize_dispatch_response_v1(
        self,
        *,
        A: Mapping[str, Any],
        observation: PythonFrontendDispatchObservationV1,
    ) -> Mapping[str, Any]:
        """Translate one server response back to the standard dry-run receipt."""
        raise NotImplementedError


@dataclass(slots=True)
class PythonFrontendProcessV1:
    role: Optional[str]
    identity_id: str
    port: RoleSealedJsonHTTPPortV1
    theta_cursor: int = 0
    theta_pages: list[Dict[str, Any]] = field(default_factory=list)
    epsilon_by_request: Dict[str, list[Dict[str, Any]]] = field(
        default_factory=dict
    )
    context: Optional[Dict[str, Any]] = None
    last_dispatch_receipt: Optional[Dict[str, Any]] = None

    def _remember_context_from_theta_v1(
        self,
        page: Mapping[str, Any],
    ) -> None:
        # Controller events carry the role-projected U that a stateful frontend
        # should treat as its local current context. Walk newest-first.
        for event in reversed(list(page.get("events") or [])):
            if not isinstance(event, Mapping):
                continue
            if str(event.get("kind") or "") != "controller_loop_event_v1":
                continue
            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                continue
            U = payload.get("U")
            if isinstance(U, Mapping):
                self.context = deepcopy(dict(U))
                return

    def poll_theta_v1(
        self,
        *,
        after_event_seq: int,
        limit: Optional[int],
    ) -> Dict[str, Any]:
        page = self.port.poll_committed_events_v1(
            role=self.role,
            identity_id=self.identity_id,
            after_event_seq=int(after_event_seq),
            limit=limit,
        )
        self.theta_pages.append(deepcopy(page))
        previous_cursor = int(self.theta_cursor)
        page_cursor = int(page.get("next_after_event_seq") or 0)
        self.theta_cursor = max(previous_cursor, page_cursor)
        # A generic proof caller may request an old limited page after this
        # process is already current. Such a historical read must not regress
        # the frontend's local U.
        if page_cursor > previous_cursor:
            self._remember_context_from_theta_v1(page)
        return deepcopy(page)

    def sync_theta_v1(self) -> Dict[str, Any]:
        return self.poll_theta_v1(
            after_event_seq=int(self.theta_cursor),
            limit=None,
        )

    def refresh_context_v1(self) -> Dict[str, Any]:
        self.context = deepcopy(
            dict(self.port.read_context_v1(role=self.role))
        )
        return deepcopy(self.context)

    def local_context_v1(self) -> Dict[str, Any]:
        if self.context is None:
            return self.refresh_context_v1()
        return deepcopy(self.context)

    def _drain_progress_once_v1(
        self,
        *,
        request_id: str,
        after: int,
        proof_observer: bool,
        sink: Optional[DryRunLiveEventSinkV1],
    ) -> tuple[int, str, Optional[str], list[Dict[str, Any]], int]:
        page = self.port.read_dispatch_progress_v1(
            role=self.role,
            identity_id=self.identity_id,
            request_id=request_id,
            after_provisional_seq=int(after),
            proof_observer=proof_observer,
        )

        cursor = int(after)
        emitted: list[Dict[str, Any]] = []
        rows = [
            row
            for row in list(page.get("rows") or page.get("events") or [])
            if isinstance(row, Mapping)
        ]
        for row in rows:
            row_dict = deepcopy(dict(row))
            emitted.append(row_dict)
            if sink is not None:
                sink(deepcopy(row_dict))

            cursor = max(
                cursor,
                int(row.get("eps_seq") or row.get("provisional_seq") or 0),
            )

        return (
            cursor,
            str(page.get("state") or ""),
            None if page.get("error") is None else str(page.get("error")),
            emitted,
            len(rows),
        )

    def drain_progress_v1(
        self,
        *,
        request_id: str,
        after: int,
        proof_observer: bool,
        sink: Optional[DryRunLiveEventSinkV1],
    ) -> tuple[int, str, Optional[str], list[Dict[str, Any]]]:
        cursor = int(after)
        state = ""
        error: Optional[str] = None
        all_events: list[Dict[str, Any]] = []

        while True:
            next_cursor, state, error, emitted, row_count = (
                self._drain_progress_once_v1(
                    request_id=request_id,
                    after=cursor,
                    proof_observer=proof_observer,
                    sink=sink,
                )
            )
            all_events.extend(emitted)
            if next_cursor > cursor:
                cursor = next_cursor

            # A full page may have more retained rows even after the store is
            # terminal. Continue only for that backlog case. Any short page
            # has drained what is currently available; terminal or open, the
            # caller can now either finish or return to cadence.
            if row_count < DEFAULT_PROGRESS_PAGE_SIZE:
                break

        if not proof_observer and all_events:
            self.epsilon_by_request.setdefault(request_id, []).extend(
                deepcopy(all_events)
            )

        return cursor, state, error, all_events


class PythonFrontendSessionV1:
    """One stateful client session spanning all role-bound front processes."""

    def __init__(
        self,
        *,
        port: RoleSealedJsonHTTPPortV1,
        progress_poll_seconds: float = DEFAULT_PROGRESS_POLL_SECONDS,
    ) -> None:
        self.port = port
        self.progress_poll_seconds = max(
            0.001,
            float(progress_poll_seconds),
        )
        self.known_canonical_high_water = 0
        self._closed = False
        self._dispatch_pool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="python-frontend-dispatch",
        )
        nonce = uuid4().hex[:12]

        self.processes: Dict[Optional[str], PythonFrontendProcessV1] = {}
        for role in port.backend.endpoints_by_role:
            normalized = _normalized_role(role)
            role_label = "unmodulated" if normalized is None else normalized
            self.processes[normalized] = PythonFrontendProcessV1(
                role=normalized,
                identity_id=(
                    f"python-front-{nonce}-{role_label}"
                ),
                port=port,
            )

        if None not in self.processes:
            raise ValueError(
                "pythonic frontend dry-run requires a role=None capability "
                "for canonical theta/Q proof"
            )

        identities = [
            process.identity_id
            for process in self.processes.values()
        ]
        if len(identities) != len(set(identities)):
            raise AssertionError(
                "distinct frontend roles must receive distinct process ids"
            )

    def close_v1(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._dispatch_pool.shutdown(wait=True, cancel_futures=True)

    def note_high_water_v1(self, value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return
        self.known_canonical_high_water = max(
            int(self.known_canonical_high_water),
            int(value),
        )

    def process_for_role_v1(
        self,
        role: Optional[str],
    ) -> PythonFrontendProcessV1:
        key = _normalized_role(role)
        try:
            return self.processes[key]
        except KeyError as exc:
            raise KeyError(
                f"no pythonic frontend process for role {key!r}"
            ) from exc

    def sync_process_to_known_v1(
        self,
        process: PythonFrontendProcessV1,
    ) -> Optional[Dict[str, Any]]:
        if int(process.theta_cursor) >= int(self.known_canonical_high_water):
            return None
        page = process.poll_theta_v1(
            after_event_seq=int(process.theta_cursor),
            limit=None,
        )
        self.note_high_water_v1(
            int(page.get("session_latest_event_seq") or 0)
        )
        return page

    @staticmethod
    def _assert_dispatcher_identity_v1(
        *,
        role: Optional[str],
        funked: bool,
        process_identity_id: str,
        dispatcher_identity_id: Any,
    ) -> None:
        if dispatcher_identity_id is None:
            return

        expected = str(process_identity_id)
        actual = str(dispatcher_identity_id)

        if not funked:
            if actual != expected:
                raise AssertionError(
                    "server did not observe the stable frontend process id: "
                    f"role={role!r}; expected={expected!r}; "
                    f"actual={actual!r}"
                )
            return

        if actual == expected:
            return

        prefix = "funkedauto-"
        suffix = f"-{expected}"

        if not actual.startswith(prefix) or not actual.endswith(suffix):
            raise AssertionError(
                "funked server dispatcher identity is not rooted in the "
                "stable frontend process id: "
                f"role={role!r}; "
                f"frontend_identity={expected!r}; "
                f"actual={actual!r}"
            )

        actor = actual[len(prefix) : -len(suffix)]
        if not actor:
            raise AssertionError(
                "funked server dispatcher identity has no generated actor: "
                f"role={role!r}; "
                f"frontend_identity={expected!r}; "
                f"actual={actual!r}"
            )

    @staticmethod
    def _assert_role_epsilon_theta_consistency_v1(
        *,
        role: Optional[str],
        epsilon: list[Mapping[str, Any]],
        theta_page: Mapping[str, Any],
    ) -> None:
        for provisional_event in epsilon:
            if "event_seq" in provisional_event:
                raise AssertionError(
                    "pythonic frontend epsilon event illegally has event_seq: "
                    f"{provisional_event!r}"
                )

    def dispatch_v1(
        self,
        *,
        A: Mapping[str, Any],
        funked: bool,
        live_event_sink: Optional[DryRunLiveEventSinkV1],
    ) -> Mapping[str, Any]:
        if self._closed:
            raise RuntimeError("pythonic frontend session is closed")
        role = _normalized_role(A.get("role"))
        process = self.process_for_role_v1(role)

        # Do not issue an empty theta request merely because an action is about
        # to occur. Synchronize only when this role is behind a canonical head
        # already observed by the frontend session.
        self.sync_process_to_known_v1(process)
        theta_before = int(process.theta_cursor)

        wire_A = deepcopy(dict(A))
        wire_A["identity_id"] = process.identity_id
        if wire_A.get("my_current_event_seq_number") is None:
            wire_A["my_current_event_seq_number"] = theta_before

        request_id = f"python-front-{uuid4().hex}"
        role_after = 0
        proof_after = 0
        role_events: list[Dict[str, Any]] = []
        proof_events: list[Dict[str, Any]] = []
        role_state = ""
        proof_state = ""
        role_error: Optional[str] = None
        proof_error: Optional[str] = None

        future = self._dispatch_pool.submit(
            self.port.submit_dispatch_v1,
            role=role,
            identity_id=process.identity_id,
            request_id=request_id,
            A=wire_A,
            funked=funked,
        )

        # Sleep first. Fast local dispatches usually have no useful progress
        # page at t=0 and are captured by the terminal drain.
        if not future.done():
            time.sleep(self.progress_poll_seconds)

        while not future.done():
            if role_state not in _TERMINAL_PROGRESS_STATES:
                (
                    role_after,
                    role_state,
                    role_error,
                    emitted,
                ) = process.drain_progress_v1(
                    request_id=request_id,
                    after=role_after,
                    proof_observer=False,
                    sink=None,
                )
                role_events.extend(emitted)

            if (
                live_event_sink is not None
                and proof_state not in _TERMINAL_PROGRESS_STATES
            ):
                (
                    proof_after,
                    proof_state,
                    proof_error,
                    emitted_proof,
                ) = process.drain_progress_v1(
                    request_id=request_id,
                    after=proof_after,
                    proof_observer=True,
                    sink=live_event_sink,
                )
                proof_events.extend(emitted_proof)

            if (
                role_state in _TERMINAL_PROGRESS_STATES
                and (
                    live_event_sink is None
                    or proof_state in _TERMINAL_PROGRESS_STATES
                )
            ):
                break

            if not future.done():
                time.sleep(self.progress_poll_seconds)

        response = future.result()

        if role_state not in _TERMINAL_PROGRESS_STATES:
            (
                role_after,
                role_state,
                role_error,
                emitted,
            ) = process.drain_progress_v1(
                request_id=request_id,
                after=role_after,
                proof_observer=False,
                sink=None,
            )
            role_events.extend(emitted)

        if (
            live_event_sink is not None
            and proof_state not in _TERMINAL_PROGRESS_STATES
        ):
            (
                proof_after,
                proof_state,
                proof_error,
                emitted_proof,
            ) = process.drain_progress_v1(
                request_id=request_id,
                after=proof_after,
                proof_observer=True,
                sink=live_event_sink,
            )
            proof_events.extend(emitted_proof)

        observation = PythonFrontendDispatchObservationV1(
            request_id=request_id,
            role=role,
            identity_id=process.identity_id,
            response=response,
            role_epsilon=tuple(deepcopy(role_events)),
            proof_epsilon=tuple(deepcopy(proof_events)),
            role_progress_state=role_state,
            role_progress_error=role_error,
            proof_progress_state=proof_state,
            proof_progress_error=proof_error,
        )

        packet = dict(
            self.port.normalize_dispatch_response_v1(
                A=wire_A,
                observation=observation,
            )
            or {}
        )

        if packet.get("rejected") is True:
            if role_events:
                raise AssertionError(
                    "eventless frontend preflight rejection unexpectedly "
                    f"published epsilon: {role_events!r}"
                )
            process.last_dispatch_receipt = deepcopy(packet)
            return packet

        self._assert_dispatcher_identity_v1(
            role=role,
            funked=funked,
            process_identity_id=process.identity_id,
            dispatcher_identity_id=packet.get("dispatcher_identity_id"),
        )

        concurrency = packet.get("dispatch_concurrency")
        if isinstance(concurrency, Mapping):
            self.note_high_water_v1(concurrency.get("after_event_seq"))

        role_theta = process.poll_theta_v1(
            after_event_seq=theta_before,
            limit=None,
        )
        self.note_high_water_v1(
            int(role_theta.get("session_latest_event_seq") or 0)
        )
        self._assert_role_epsilon_theta_consistency_v1(
            role=role,
            epsilon=role_events,
            theta_page=role_theta,
        )

        # Canonical controller theta normally supplied current projected U. If
        # this unusual action emitted no controller U, preserve correctness via
        # the bootstrap/fallback context endpoint rather than doing it always.
        if process.context is None:
            process.refresh_context_v1()

        process.last_dispatch_receipt = deepcopy(packet)
        return packet


class PythonFrontendExampleDryRunStrategy(BaseDryRunStrategy, ABC):
    """Base strategy for any role-sealed server + stateful Python frontend."""

    def __init__(
        self,
        *,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        progress_poll_seconds: float = DEFAULT_PROGRESS_POLL_SECONDS,
    ) -> None:
        timeout = float(request_timeout_seconds)
        if timeout <= 0:
            raise ValueError("request_timeout_seconds must be > 0")
        self._request_timeout_seconds = timeout
        self._progress_poll_seconds = max(
            0.001,
            float(progress_poll_seconds),
        )

    @abstractmethod
    def _start_backend_v1(
        self,
        *,
        program: Mapping[str, Any],
        session_metadata: Mapping[str, Any],
        initial_parameter_overrides: Mapping[str, Any],
    ) -> PythonFrontendBackendRunV1:
        raise NotImplementedError

    @abstractmethod
    def _close_backend_v1(
        self,
        *,
        backend: PythonFrontendBackendRunV1,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def _build_port_v1(
        self,
        *,
        backend: PythonFrontendBackendRunV1,
    ) -> RoleSealedJsonHTTPPortV1:
        raise NotImplementedError

    def start_run_v1(
        self,
        *,
        program: Mapping[str, Any],
        session_metadata: Mapping[str, Any],
        initial_parameter_overrides: Mapping[str, Any],
    ) -> DryRunRunHandleV1:
        backend = self._start_backend_v1(
            program=program,
            session_metadata=session_metadata,
            initial_parameter_overrides=initial_parameter_overrides,
        )
        frontend: Optional[PythonFrontendSessionV1] = None
        try:
            port = self._build_port_v1(backend=backend)
            frontend = PythonFrontendSessionV1(
                port=port,
                progress_poll_seconds=self._progress_poll_seconds,
            )
            run = PythonFrontendRunV1(
                backend=backend,
                frontend=frontend,
            )
            # One real frontend transport read is the readiness check and the
            # initial known canonical head for all role clients.
            latest = int(frontend.port.latest_event_seq_v1())
            frontend.note_high_water_v1(latest)
            return run
        except Exception:
            try:
                if frontend is not None:
                    frontend.close_v1()
            finally:
                self._close_backend_v1(backend=backend)
            raise

    @staticmethod
    def _run_v1(run: DryRunRunHandleV1) -> PythonFrontendRunV1:
        if not isinstance(run, PythonFrontendRunV1):
            raise TypeError("wrong run handle for pythonic frontend strategy")
        return run

    def close_run_v1(self, *, run: DryRunRunHandleV1) -> None:
        value = self._run_v1(run)
        try:
            value.frontend.close_v1()
        finally:
            self._close_backend_v1(backend=value.backend)

    def dispatch_action_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        A: Mapping[str, Any],
        live_event_sink: Optional[DryRunLiveEventSinkV1] = None,
    ) -> Mapping[str, Any]:
        return self._run_v1(run).frontend.dispatch_v1(
            A=A,
            funked=False,
            live_event_sink=live_event_sink,
        )

    def dispatch_action_with_chain_reaction_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        A: Mapping[str, Any],
        live_event_sink: Optional[DryRunLiveEventSinkV1] = None,
    ) -> Mapping[str, Any]:
        return self._run_v1(run).frontend.dispatch_v1(
            A=A,
            funked=True,
            live_event_sink=live_event_sink,
        )

    def latest_committed_event_seq_v1(
        self,
        *,
        run: DryRunRunHandleV1,
    ) -> int:
        frontend = self._run_v1(run).frontend
        latest = int(frontend.port.latest_event_seq_v1())
        frontend.note_high_water_v1(latest)
        return latest

    def committed_events_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> list[Mapping[str, Any]]:
        frontend = self._run_v1(run).frontend
        process = frontend.process_for_role_v1(role)
        page = process.poll_theta_v1(
            after_event_seq=0,
            limit=None,
        )
        frontend.note_high_water_v1(
            int(page.get("session_latest_event_seq") or 0)
        )
        return [
            dict(event)
            for event in list(page.get("events") or [])
            if isinstance(event, Mapping)
        ]

    def poll_committed_events_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
        after_event_seq: int,
        identity_id: str,
        limit: Optional[int],
    ) -> Mapping[str, Any]:
        del identity_id
        frontend = self._run_v1(run).frontend
        process = frontend.process_for_role_v1(role)
        page = process.poll_theta_v1(
            after_event_seq=int(after_event_seq),
            limit=limit,
        )
        frontend.note_high_water_v1(
            int(page.get("session_latest_event_seq") or 0)
        )
        return page

    def read_context_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> Mapping[str, Any]:
        frontend = self._run_v1(run).frontend
        process = frontend.process_for_role_v1(role)
        frontend.sync_process_to_known_v1(process)
        return process.local_context_v1()


__all__ = [
    "DEFAULT_EVENT_PAGE_SIZE",
    "DEFAULT_PROGRESS_PAGE_SIZE",
    "DEFAULT_PROGRESS_POLL_SECONDS",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "PythonFrontendBackendRunV1",
    "PythonFrontendDispatchObservationV1",
    "PythonFrontendEndpointSetV1",
    "PythonFrontendExampleDryRunStrategy",
    "PythonFrontendHTTPResultV1",
    "PythonFrontendProcessV1",
    "PythonFrontendRunV1",
    "PythonFrontendSessionV1",
    "RoleSealedJsonHTTPPortV1",
    "invalid_event_cursor_packet_v1",
    "normalize_harmonized_server_receipt_v1",
    "raise_remote_exception_packet_v1",
    "raise_remote_exception_text_v1",
    "remote_exception_type_v1",
]
