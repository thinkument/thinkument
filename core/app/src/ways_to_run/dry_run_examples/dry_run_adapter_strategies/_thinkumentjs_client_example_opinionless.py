from __future__ import annotations

"""Reusable opinionless ThinkumentJS frontend for dry-run server strategies.

Task-F performance law
----------------------
The standard dry-run language remains P / SM / C / A / E and every dry-run
case still owns a fresh backend session plus a fresh role-client set.

The expensive JavaScript *kernel host* is strategy-scoped rather than
case-scoped:

    one strategy instance
        -> one Node process
        -> one ThinkumentJS module graph import
        -> many sequential dry-run cases

For every case the host opens a fresh client set, and ``close_run_v1`` stops and
forgets those clients before the backend session is released. Nothing from Q,
X, identities, portals, pollers, womb observations, or canonical cursors is
reused across cases.

Task F also keeps the Python/Node protocol narrow and removes redundant proof
traffic:

* Node retains the real client state locally;
* one canonical bootstrap head is shared across the fresh role-client set;
* proof progress sleeps before its first in-flight GET;
* terminal progress never triggers a redundant read-after-terminal GET;
* a short nonterminal page returns to cadence instead of immediately busy
  polling again;
* successful dispatches return only the facts consumed by the standard proof.

Server-side dispatch failures have one additional observation rule. When an
action has no generic live-event sink but the real JS dispatch returns an HTTP
5xx-class failure, Python performs one terminal privileged progress drain. This
recovers the authoritative typed remote exception without restoring full
progress history to Node stdout.

Production ThinkumentJS remains unchanged by this module. Product polling,
dispatch progress, canonical catch-up, role sealing, and womb behavior continue
to run through the real ThinkumentJS modules.
"""

import builtins
import json
import queue
import shutil
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from urllib.error import HTTPError as UrlHTTPError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from live_vial._js.static_assets import STATIC_ROOT as THINKUMENTJS_STATIC_ROOT

from ways_to_run.dry_run_examples.dry_run_adapter_strategies.BASE_CLASS import (
    BaseDryRunStrategy,
    DryRunLiveEventSinkV1,
    DryRunRunHandleV1,
)
from ways_to_run.dry_run_examples.dry_run_standard_lingo.protocol_v1 import (
    assert_standard_event_v1,
)


DEFAULT_NODE_BINARY = "node"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_PROGRESS_POLL_SECONDS = 0.025

# Production-scale background cadence. Dry-run synchronization is explicit,
# so the background loop stays real without becoming a test busy-loop.
DEFAULT_NODE_BASE_POLL_MS = 30_000
DEFAULT_NODE_DISPATCH_POLL_MS = 5_000
DEFAULT_NODE_REMOTE_ACTIVITY_POLL_MS = 15_000

# 25 ms is still a very sharp proof observer (40 Hz), while avoiding the
# 100-Hz request pressure of the earlier 10 ms setting against persistence-
# backed Django. Fast dispatches are captured by the terminal drain anyway.
DEFAULT_NODE_PROGRESS_POLL_MS = 25
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
class ThinkumentJSFrontendEndpointSetV1:
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
    ) -> "ThinkumentJSFrontendEndpointSetV1":
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
                "ThinkumentJS frontend endpoint set is missing endpoint(s): "
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

    def absolute_v1(self, base_url: str) -> Dict[str, str]:
        base = f"{str(base_url).rstrip('/')}/"

        def absolute(value: str) -> str:
            parsed = urlsplit(str(value))
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return str(value)
            return urljoin(base, str(value).lstrip("/"))

        return {
            "context": absolute(self.context),
            "latestEventSeq": absolute(self.latest_event_seq),
            "events": absolute(self.events),
            "eps": absolute(self.dispatch_progress),
            "dispatchProgress": absolute(self.dispatch_progress),
            "dispatch": absolute(self.dispatch),
            "dispatchFunked": absolute(self.dispatch_funked),
        }


@dataclass(slots=True)
class ThinkumentJSFrontendBackendRunV1:
    base_url: str
    session_id: str
    endpoints_by_role: Dict[Optional[str], ThinkumentJSFrontendEndpointSetV1]
    proof_obweb_RESTful: ThinkumentJSFrontendEndpointSetV1
    host_resource: Any = None


@dataclass(frozen=True, slots=True)
class ThinkumentJSDispatchObservationV1:
    request_id: str
    role: Optional[str]
    identity_id: str
    node: Mapping[str, Any]
    proof_progress_state: str
    proof_progress_error: Optional[str]


@dataclass(slots=True)
class ThinkumentJSFrontendRunV1:
    backend: ThinkumentJSFrontendBackendRunV1
    frontend: "ThinkumentJSFrontendSessionV1"


def _normalized_role(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def targets_from_standard_A_v1(A: Mapping[str, Any]) -> list[str]:
    out: list[str] = []

    fill = A.get("user_fill")
    if isinstance(fill, Mapping):
        out.extend(str(key).split(".", 1)[0] for key in fill)

    signal = A.get("user_signal")
    if isinstance(signal, Mapping) and signal.get("datum_id"):
        out.append(str(signal["datum_id"]))

    return list(dict.fromkeys(value for value in out if value))


def raise_thinkumentjs_station_guard_exception_v1(
    *,
    A: Mapping[str, Any],
    error: Mapping[str, Any],
) -> None:
    code = str(error.get("code") or "")
    message = str(
        error.get("message") or "ThinkumentJS preflight rejected A"
    )
    receipt = error.get("receipt")
    receipt_errors = (
        list(receipt.get("errors") or [])
        if isinstance(receipt, Mapping)
        else []
    )
    permission_denied = (
        code == "write_role_denied"
        or any(
            isinstance(row, Mapping)
            and row.get("code") == "write_role_denied"
            for row in receipt_errors
        )
    )

    if permission_denied:
        targets = targets_from_standard_A_v1(A)
        raise PermissionError(
            "permission denied for "
            + (", ".join(targets) or message)
        )

    raise TypeError(message)


def _without_event_seq_v1(event: Mapping[str, Any]) -> Dict[str, Any]:
    out = deepcopy(dict(event))
    out.pop("event_seq", None)
    return out


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
            "target_count": len(targets_from_standard_A_v1(A)),
        },
    }


def normalize_harmonized_server_receipt_v1(
    packet: Mapping[str, Any],
) -> Dict[str, Any]:
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
        normalized["guarding"] = "per_session_serialized_highest_facade"
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


class _NodeRuntimeHostV1:
    """One persistent Node kernel host reused by sequential dry-run cases."""

    def __init__(
        self,
        *,
        node_binary: str,
        request_timeout_seconds: float,
    ) -> None:
        binary = shutil.which(str(node_binary))
        if binary is None:
            raise RuntimeError(
                f"Node.js executable {node_binary!r} is required for the "
                "ThinkumentJS dry-run strategy"
            )

        runner = Path(__file__).with_name(
            "_thinkumentjs_client_example_opinionless.mjs"
        )
        if not runner.is_file():
            raise FileNotFoundError(
                "ThinkumentJS dry-run Node harness is missing: "
                f"{runner}"
            )

        thinkument_js_root = Path(THINKUMENTJS_STATIC_ROOT).resolve()
        if not thinkument_js_root.is_dir():
            raise FileNotFoundError(
                f"installed ThinkumentJS root is missing: {thinkument_js_root}"
            )

        self._thinkument_js_root = thinkument_js_root
        self._lock = threading.Lock()
        self._next_id = 1
        self._stderr_lines: deque[str] = deque(maxlen=100)
        self._closed = False
        self._run_open = False

        self._command_timeout_seconds = max(
            10.0,
            float(request_timeout_seconds) + 10.0,
        )
        self._stdout_queue: queue.Queue[Optional[str]] = queue.Queue()
        self._process = subprocess.Popen(
            [binary, str(runner)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        assert self._process.stdin is not None
        assert self._process.stdout is not None
        assert self._process.stderr is not None

        self._stdout_thread = threading.Thread(
            target=self._drain_stdout_v1,
            name="thinkumentjs-dry-run-stdout",
            daemon=True,
        )
        self._stdout_thread.start()

        self._stderr_thread = threading.Thread(
            target=self._drain_stderr_v1,
            name="thinkumentjs-dry-run-stderr",
            daemon=True,
        )
        self._stderr_thread.start()

    @property
    def run_open(self) -> bool:
        return self._run_open

    def _drain_stdout_v1(self) -> None:
        stream = self._process.stdout
        if stream is None:
            self._stdout_queue.put(None)
            return

        try:
            for line in stream:
                self._stdout_queue.put(line)
        finally:
            self._stdout_queue.put(None)

    def _drain_stderr_v1(self) -> None:
        stream = self._process.stderr
        if stream is None:
            return

        for line in stream:
            self._stderr_lines.append(line.rstrip())

    def _failure_context_v1(self) -> str:
        stderr = "\n".join(self._stderr_lines)
        return f"\nNode stderr:\n{stderr}" if stderr else ""

    def command_v1(
        self,
        command: str,
        *,
        timeout_seconds: Optional[float] = None,
        **payload: Any,
    ) -> Dict[str, Any]:
        if self._closed:
            raise RuntimeError("ThinkumentJS Node runtime is closed")

        timeout = (
            self._command_timeout_seconds
            if timeout_seconds is None
            else max(0.001, float(timeout_seconds))
        )

        with self._lock:
            message_id = self._next_id
            self._next_id += 1
            message = {
                "id": message_id,
                "command": str(command),
                **payload,
            }

            if self._process.poll() is not None:
                raise RuntimeError(
                    "ThinkumentJS Node runtime exited unexpectedly"
                    + self._failure_context_v1()
                )

            stdin = self._process.stdin
            if stdin is None:
                raise RuntimeError("ThinkumentJS Node runtime stdin is closed")

            stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            stdin.flush()

            try:
                line = self._stdout_queue.get(timeout=timeout)
            except queue.Empty as exc:
                self._terminate_process_v1()
                raise TimeoutError(
                    "ThinkumentJS Node command timed out instead of replying: "
                    f"command={command!r}, timeout_seconds={timeout:g}"
                    + self._failure_context_v1()
                ) from exc

            if line is None:
                raise RuntimeError(
                    "ThinkumentJS Node runtime closed before replying to "
                    f"command={command!r}"
                    + self._failure_context_v1()
                )

            try:
                response = json.loads(line)
            except Exception as exc:
                raise RuntimeError(
                    "ThinkumentJS Node runtime emitted non-JSON stdout: "
                    f"{line!r}{self._failure_context_v1()}"
                ) from exc

            if response.get("id") != message_id:
                raise RuntimeError(
                    "ThinkumentJS Node runtime response id mismatch: "
                    f"expected={message_id}, response={response!r}"
                )
            if response.get("ok") is not True:
                error = response.get("error") or {}
                detail = json.dumps(error, sort_keys=True, default=str)
                raise RuntimeError(
                    "ThinkumentJS Node command failed: "
                    f"{error.get('name')}: {error.get('message')}; "
                    f"detail={detail}"
                    + self._failure_context_v1()
                )

            result = response.get("result")
            if not isinstance(result, Mapping):
                raise RuntimeError(
                    "ThinkumentJS Node command returned a non-object result: "
                    f"{result!r}"
                )
            return deepcopy(dict(result))

    def open_run_v1(
        self,
        *,
        backend: ThinkumentJSFrontendBackendRunV1,
        identities_by_role: Mapping[Optional[str], str],
        request_timeout_seconds: float,
    ) -> None:
        if self._run_open:
            raise RuntimeError(
                "persistent ThinkumentJS Node host already owns an open run"
            )

        clients = []
        for role, identity_id in identities_by_role.items():
            endpoints = backend.endpoints_by_role[role].absolute_v1(
                backend.base_url
            )
            clients.append(
                {
                    "role": role,
                    "identityId": str(identity_id),
                    "endpoints": endpoints,
                }
            )

        boot = self.command_v1(
            "open_run",
            config={
                "thinkumentJsRoot": str(self._thinkument_js_root),
                "backendSessionId": str(backend.session_id),
                "clients": clients,
                "polling": {
                    "eventPageSize": DEFAULT_EVENT_PAGE_SIZE,
                    "progressPageSize": DEFAULT_PROGRESS_PAGE_SIZE,
                    "basePeriodMs": DEFAULT_NODE_BASE_POLL_MS,
                    "dispatchPeriodMs": DEFAULT_NODE_DISPATCH_POLL_MS,
                    "remoteActivityPeriodMs": (
                        DEFAULT_NODE_REMOTE_ACTIVITY_POLL_MS
                    ),
                    "progressPollPeriodMs": (
                        DEFAULT_NODE_PROGRESS_POLL_MS
                    ),
                    "requestTimeoutMs": int(
                        float(request_timeout_seconds) * 1000
                    ),
                },
            },
        )

        returned = {
            (_normalized_role(row.get("role")), str(row.get("identity_id")))
            for row in list(boot.get("clients") or [])
            if isinstance(row, Mapping)
        }
        expected = {
            (_normalized_role(role), str(identity_id))
            for role, identity_id in identities_by_role.items()
        }
        if returned != expected:
            try:
                self.command_v1("close_run", timeout_seconds=2.0)
            finally:
                self._run_open = False
            raise AssertionError(
                "Node runtime did not boot exactly one stable ThinkumentJS "
                f"client per role: expected={expected!r}, actual={returned!r}"
            )

        self._run_open = True

    def release_run_v1(self) -> None:
        if not self._run_open or self._closed:
            self._run_open = False
            return

        try:
            self.command_v1("close_run", timeout_seconds=2.0)
        finally:
            self._run_open = False

    def _terminate_process_v1(self) -> None:
        process = self._process
        if process.poll() is not None:
            return

        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)

    def close_v1(self, *, force: bool = False) -> None:
        if self._closed:
            return

        process = self._process
        if force:
            self._closed = True
            self._run_open = False
            self._terminate_process_v1()
        else:
            try:
                if process.poll() is None:
                    self.command_v1(
                        "close_runtime",
                        timeout_seconds=2.0,
                    )
            except Exception:
                pass
            finally:
                self._closed = True
                self._run_open = False

            if process.poll() is None:
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self._terminate_process_v1()

        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream and stream.close()
            except Exception:
                pass


class _ProofObserverHTTPPortV1:
    def __init__(
        self,
        *,
        backend: ThinkumentJSFrontendBackendRunV1,
        request_timeout_seconds: float,
    ) -> None:
        self.backend = backend
        self.request_timeout_seconds = float(request_timeout_seconds)

    def _http_json_v1(
        self,
        path: str,
        *,
        query: Mapping[str, Any],
    ) -> Dict[str, Any]:
        base = f"{self.backend.base_url.rstrip('/')}/"
        parsed = urlsplit(str(path))
        url = (
            str(path)
            if parsed.scheme in {"http", "https"} and parsed.netloc
            else urljoin(base, str(path).lstrip("/"))
        )
        url = f"{url}?{urlencode(dict(query), doseq=True)}"

        request = Request(
            url,
            headers={"Accept": "application/json"},
            method="GET",
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
            packet = json.loads(text) if text else {}
        except Exception:
            packet = {"raw_text": text}

        if status != 200 or not isinstance(packet, Mapping):
            raise AssertionError(
                "ThinkumentJS proof-observer progress read failed: "
                f"status={status}, packet={packet!r}"
            )
        return deepcopy(dict(packet))

    def read_progress_v1(
        self,
        *,
        identity_id: str,
        request_id: str,
        after: int,
    ) -> Dict[str, Any]:
        return self._http_json_v1(
            self.backend.proof_obweb_RESTful.dispatch_progress,
            query={
                "identity_id": str(identity_id),
                "request_id": str(request_id),
                "after_seq": int(after),
                "after_eps_seq": int(after),
                "after_provisional_seq": int(after),
                "limit": DEFAULT_PROGRESS_PAGE_SIZE,
            },
        )


class ThinkumentJSFrontendSessionV1:
    def __init__(
        self,
        *,
        backend: ThinkumentJSFrontendBackendRunV1,
        node_runtime: _NodeRuntimeHostV1,
        request_timeout_seconds: float,
        progress_poll_seconds: float,
    ) -> None:
        self.backend = backend
        self.node = node_runtime
        self.progress_poll_seconds = max(
            0.001,
            float(progress_poll_seconds),
        )
        self._closed = False
        self._dispatch_command_pool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="thinkumentjs-dry-run-dispatch",
        )

        nonce = uuid4().hex[:12]
        self.identities_by_role: Dict[Optional[str], str] = {}
        for index, role in enumerate(backend.endpoints_by_role):
            normalized = _normalized_role(role)
            self.identities_by_role[normalized] = (
                f"thinkumentjs-front-{nonce}-{index}"
            )

        if None not in self.identities_by_role:
            raise ValueError(
                "ThinkumentJS dry run requires a role=None client capability "
                "for canonical proof reads"
            )
        if len(set(self.identities_by_role.values())) != len(
            self.identities_by_role
        ):
            raise AssertionError(
                "distinct ThinkumentJS roles must receive distinct client ids"
            )

        self.proof_observer = _ProofObserverHTTPPortV1(
            backend=backend,
            request_timeout_seconds=request_timeout_seconds,
        )

        self.node.open_run_v1(
            backend=backend,
            identities_by_role=self.identities_by_role,
            request_timeout_seconds=request_timeout_seconds,
        )

    def close_v1(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._dispatch_command_pool.shutdown(
                wait=True,
                cancel_futures=True,
            )
        finally:
            self.node.release_run_v1()

    def identity_for_role_v1(self, role: Optional[str]) -> str:
        key = _normalized_role(role)
        try:
            return self.identities_by_role[key]
        except KeyError as exc:
            raise KeyError(
                f"no ThinkumentJS client for role {key!r}"
            ) from exc

    def sync_cursor_v1(self, *, role: Optional[str]) -> int:
        result = self.node.command_v1(
            "sync_cursor",
            role=_normalized_role(role),
        )
        return int(result["cursor"])

    def read_context_v1(
        self,
        *,
        role: Optional[str],
    ) -> Mapping[str, Any]:
        result = self.node.command_v1(
            "read_context",
            role=_normalized_role(role),
        )
        U = result.get("U")
        if not isinstance(U, Mapping):
            raise AssertionError(
                "ThinkumentJS client-local Q does not contain a current U: "
                f"role={_normalized_role(role)!r}, result={result!r}"
            )
        return deepcopy(dict(U))

    def poll_local_v1(
        self,
        *,
        role: Optional[str],
        after_event_seq: int,
        limit: Optional[int],
    ) -> Dict[str, Any]:
        return self.node.command_v1(
            "poll_local",
            role=_normalized_role(role),
            afterEventSeq=int(after_event_seq),
            limit=limit,
        )

    def _drain_proof_progress_v1(
        self,
        *,
        identity_id: str,
        request_id: str,
        after: int,
        sink: DryRunLiveEventSinkV1,
    ) -> tuple[int, str, Optional[str]]:
        cursor = int(after)
        last_state = ""
        last_error: Optional[str] = None

        while True:
            page = self.proof_observer.read_progress_v1(
                identity_id=identity_id,
                request_id=request_id,
                after=cursor,
            )
            last_state = str(page.get("state") or "")
            last_error = (
                None if page.get("error") is None else str(page.get("error"))
            )

            rows = [
                row
                for row in list(page.get("rows") or page.get("events") or [])
                if isinstance(row, Mapping)
            ]
            next_cursor = cursor
            for row in rows:
                sink(deepcopy(dict(row)))

                next_cursor = max(
                    next_cursor,
                    int(row.get("eps_seq") or row.get("provisional_seq") or 0),
                )

            if next_cursor > cursor:
                cursor = next_cursor

            # A full page can have more retained rows even when the store is
            # terminal. Continue only for that backlog case. A short page has
            # drained what is currently available, so return to the caller's
            # cadence (or finish immediately when the state is terminal).
            if len(rows) < DEFAULT_PROGRESS_PAGE_SIZE:
                return cursor, last_state, last_error

    def dispatch_v1(
        self,
        *,
        A: Mapping[str, Any],
        funked: bool,
        live_event_sink: Optional[DryRunLiveEventSinkV1],
    ) -> ThinkumentJSDispatchObservationV1:
        if self._closed:
            raise RuntimeError("ThinkumentJS frontend session is closed")
        role = _normalized_role(A.get("role"))
        identity_id = self.identity_for_role_v1(role)
        request_id = f"thinkumentjs-dry-run-{uuid4().hex}"

        cursor = A.get("my_current_event_seq_number")
        cursor_override_present = cursor is not None

        command_kwargs = {
            "role": role,
            "A": deepcopy(dict(A)),
            "funked": bool(funked),
            "requestId": request_id,
            "cursorOverridePresent": cursor_override_present,
            "cursorOverride": deepcopy(cursor),
        }

        proof_state = ""
        proof_error: Optional[str] = None

        if live_event_sink is None:
            node_result = self.node.command_v1(
                "dispatch",
                **command_kwargs,
            )

            # Most actions need no privileged progress read. A server-side 5xx
            # is the exception because Django exposes the authoritative typed
            # worker/preflight error on the progress surface.
            dispatch_error = node_result.get("dispatch_error")
            if isinstance(dispatch_error, Mapping):
                status = dispatch_error.get("status")
                if (
                    isinstance(status, int)
                    and not isinstance(status, bool)
                    and status >= 500
                ):
                    _, proof_state, proof_error = (
                        self._drain_proof_progress_v1(
                            identity_id=identity_id,
                            request_id=request_id,
                            after=0,
                            sink=lambda _event: None,
                        )
                    )
        else:
            future = self._dispatch_command_pool.submit(
                self.node.command_v1,
                "dispatch",
                **command_kwargs,
            )
            after = 0

            # Sleep first. Fast dispatches are cheaper as one terminal drain
            # than as an eager empty GET plus a final GET.
            if not future.done():
                time.sleep(self.progress_poll_seconds)

            while not future.done():
                after, proof_state, proof_error = (
                    self._drain_proof_progress_v1(
                        identity_id=identity_id,
                        request_id=request_id,
                        after=after,
                        sink=live_event_sink,
                    )
                )
                if proof_state in _TERMINAL_PROGRESS_STATES:
                    break
                if not future.done():
                    time.sleep(self.progress_poll_seconds)

            node_result = future.result()

            # Only drain after transport completion if the observer has not
            # already consumed a terminal page.
            if proof_state not in _TERMINAL_PROGRESS_STATES:
                after, proof_state, proof_error = (
                    self._drain_proof_progress_v1(
                        identity_id=identity_id,
                        request_id=request_id,
                        after=after,
                        sink=live_event_sink,
                    )
                )

        return ThinkumentJSDispatchObservationV1(
            request_id=request_id,
            role=role,
            identity_id=identity_id,
            node=node_result,
            proof_progress_state=proof_state,
            proof_progress_error=proof_error,
        )


class ThinkumentJSOpinionlessFrontendDryRunStrategy(
    BaseDryRunStrategy,
    ABC,
):
    """Base strategy for a role-sealed server + real ThinkumentJS frontend."""

    def __init__(
        self,
        *,
        node_binary: str = DEFAULT_NODE_BINARY,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        progress_poll_seconds: float = DEFAULT_PROGRESS_POLL_SECONDS,
    ) -> None:
        timeout = float(request_timeout_seconds)
        if timeout <= 0:
            raise ValueError("request_timeout_seconds must be > 0")

        self._node_binary = str(node_binary)
        self._request_timeout_seconds = timeout
        self._progress_poll_seconds = max(
            0.001,
            float(progress_poll_seconds),
        )
        self._node_runtime: Optional[_NodeRuntimeHostV1] = None

    @abstractmethod
    def _start_backend_v1(
        self,
        *,
        program: Mapping[str, Any],
        session_metadata: Mapping[str, Any],
        initial_parameter_overrides: Mapping[str, Any],
    ) -> ThinkumentJSFrontendBackendRunV1:
        raise NotImplementedError

    @abstractmethod
    def _close_backend_v1(
        self,
        *,
        backend: ThinkumentJSFrontendBackendRunV1,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def _normalize_dispatch_observation_v1(
        self,
        *,
        backend: ThinkumentJSFrontendBackendRunV1,
        A: Mapping[str, Any],
        observation: ThinkumentJSDispatchObservationV1,
    ) -> Mapping[str, Any]:
        raise NotImplementedError

    def _node_runtime_v1(self) -> _NodeRuntimeHostV1:
        runtime = self._node_runtime
        if runtime is None:
            runtime = _NodeRuntimeHostV1(
                node_binary=self._node_binary,
                request_timeout_seconds=self._request_timeout_seconds,
            )
            self._node_runtime = runtime
        return runtime

    def close_strategy_v1(self) -> None:
        """Release the strategy-scoped Node kernel host."""
        runtime = self._node_runtime
        self._node_runtime = None
        if runtime is not None:
            runtime.close_v1()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        self.close_strategy_v1()
        return False

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
        frontend: Optional[ThinkumentJSFrontendSessionV1] = None

        try:
            frontend = ThinkumentJSFrontendSessionV1(
                backend=backend,
                node_runtime=self._node_runtime_v1(),
                request_timeout_seconds=self._request_timeout_seconds,
                progress_poll_seconds=self._progress_poll_seconds,
            )
            run = ThinkumentJSFrontendRunV1(
                backend=backend,
                frontend=frontend,
            )
            self.latest_committed_event_seq_v1(run=run)
            return run
        except Exception:
            try:
                if frontend is not None:
                    frontend.close_v1()
                elif self._node_runtime is not None:
                    self._node_runtime.release_run_v1()
            finally:
                self._close_backend_v1(backend=backend)
            raise

    @staticmethod
    def _run_v1(run: DryRunRunHandleV1) -> ThinkumentJSFrontendRunV1:
        if not isinstance(run, ThinkumentJSFrontendRunV1):
            raise TypeError(
                "wrong run handle for ThinkumentJS frontend dry-run strategy"
            )
        return run

    def close_run_v1(self, *, run: DryRunRunHandleV1) -> None:
        value = self._run_v1(run)
        try:
            value.frontend.close_v1()
        finally:
            self._close_backend_v1(backend=value.backend)

    @staticmethod
    def _assert_wire_identity_v1(
        *,
        A: Mapping[str, Any],
        observation: ThinkumentJSDispatchObservationV1,
    ) -> None:
        node = observation.node
        packet = node.get("wire_dispatch_packet")
        if not isinstance(packet, Mapping):
            return

        if str(packet.get("identity_id") or "") != observation.identity_id:
            raise AssertionError(
                "ThinkumentJS wire dispatch did not use the stable role client "
                f"identity: expected={observation.identity_id!r}, "
                f"packet={dict(packet)!r}"
            )
        if _normalized_role(packet.get("role")) != observation.role:
            raise AssertionError(
                "ThinkumentJS wire dispatch role diverged from the sealed "
                f"client role: expected={observation.role!r}, "
                f"packet={dict(packet)!r}"
            )
        if str(packet.get("request_id") or "") != observation.request_id:
            raise AssertionError(
                "ThinkumentJS wire dispatch request id diverged from the "
                "client request"
            )

        supplied_cursor = A.get("my_current_event_seq_number")
        expected_cursor = (
            supplied_cursor
            if supplied_cursor is not None
            else int(node.get("before_cursor") or 0)
        )
        if packet.get("my_current_event_seq_number") != expected_cursor:
            raise AssertionError(
                "ThinkumentJS wire cursor did not follow the sealed-Q / "
                "explicit-test-fixture law: "
                f"expected={expected_cursor!r}, "
                f"actual={packet.get('my_current_event_seq_number')!r}"
            )

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
                    "server did not observe the stable ThinkumentJS client id: "
                    f"role={role!r}; expected={expected!r}; actual={actual!r}"
                )
            return

        if actual == expected:
            return

        prefix = "funkedauto-"
        suffix = f"-{expected}"
        if not actual.startswith(prefix) or not actual.endswith(suffix):
            raise AssertionError(
                "funked dispatcher identity is not rooted in the stable "
                "ThinkumentJS client identity: "
                f"role={role!r}; client={expected!r}; actual={actual!r}"
            )

        actor = actual[len(prefix) : -len(suffix)]
        if not actor:
            raise AssertionError(
                "funked dispatcher identity contains no generated actor"
            )

    @staticmethod
    def _assert_womb_epsilon_theta_v1(
        *,
        role: Optional[str],
        observation: ThinkumentJSDispatchObservationV1,
    ) -> None:
        node = observation.node
        epsilon = [
            deepcopy(dict(event))
            for event in list(node.get("epsilon_events") or [])
            if isinstance(event, Mapping)
        ]
        theta = [
            deepcopy(dict(event))
            for event in list(node.get("theta_events") or [])
            if isinstance(event, Mapping)
        ]

        for event in epsilon:
            if "event_seq" in event:
                raise AssertionError(
                    "ThinkumentJS womb epsilon event illegally carried "
                    f"canonical event_seq: {event!r}"
                )
        for event in theta:
            if not isinstance(event.get("event_seq"), int):
                raise AssertionError(
                    "ThinkumentJS womb theta event lacks canonical event_seq: "
                    f"{event!r}"
                )

        for epsilon_index, provisional in enumerate(epsilon):
            if "event_seq" in provisional:
                raise AssertionError(
                    "ThinkumentJS womb epsilon illegally carried canonical "
                    f"event_seq: {provisional!r}"
                )

    def _dispatch_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        A: Mapping[str, Any],
        funked: bool,
        live_event_sink: Optional[DryRunLiveEventSinkV1],
    ) -> Mapping[str, Any]:
        value = self._run_v1(run)
        observation = value.frontend.dispatch_v1(
            A=A,
            funked=funked,
            live_event_sink=live_event_sink,
        )

        packet = dict(
            self._normalize_dispatch_observation_v1(
                backend=value.backend,
                A=A,
                observation=observation,
            )
            or {}
        )

        self._assert_wire_identity_v1(
            A=A,
            observation=observation,
        )

        if packet.get("rejected") is True:
            return packet

        self._assert_dispatcher_identity_v1(
            role=observation.role,
            funked=funked,
            process_identity_id=observation.identity_id,
            dispatcher_identity_id=packet.get("dispatcher_identity_id"),
        )
        self._assert_womb_epsilon_theta_v1(
            role=observation.role,
            observation=observation,
        )
        return packet

    def dispatch_action_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        A: Mapping[str, Any],
        live_event_sink: Optional[DryRunLiveEventSinkV1] = None,
    ) -> Mapping[str, Any]:
        return self._dispatch_v1(
            run=run,
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
        return self._dispatch_v1(
            run=run,
            A=A,
            funked=True,
            live_event_sink=live_event_sink,
        )

    def latest_committed_event_seq_v1(
        self,
        *,
        run: DryRunRunHandleV1,
    ) -> int:
        value = self._run_v1(run)
        return value.frontend.sync_cursor_v1(role=None)

    def committed_events_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> list[Mapping[str, Any]]:
        page = self._run_v1(run).frontend.poll_local_v1(
            role=role,
            after_event_seq=0,
            limit=None,
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
        return self._run_v1(run).frontend.poll_local_v1(
            role=role,
            after_event_seq=int(after_event_seq),
            limit=limit,
        )

    def read_context_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> Mapping[str, Any]:
        return self._run_v1(run).frontend.read_context_v1(
            role=role,
        )


__all__ = [
    "DEFAULT_EVENT_PAGE_SIZE",
    "DEFAULT_NODE_BASE_POLL_MS",
    "DEFAULT_NODE_BINARY",
    "DEFAULT_NODE_DISPATCH_POLL_MS",
    "DEFAULT_NODE_PROGRESS_POLL_MS",
    "DEFAULT_NODE_REMOTE_ACTIVITY_POLL_MS",
    "DEFAULT_PROGRESS_PAGE_SIZE",
    "DEFAULT_PROGRESS_POLL_SECONDS",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "ThinkumentJSDispatchObservationV1",
    "ThinkumentJSFrontendBackendRunV1",
    "ThinkumentJSFrontendEndpointSetV1",
    "ThinkumentJSFrontendRunV1",
    "ThinkumentJSFrontendSessionV1",
    "ThinkumentJSOpinionlessFrontendDryRunStrategy",
    "invalid_event_cursor_packet_v1",
    "normalize_harmonized_server_receipt_v1",
    "raise_remote_exception_packet_v1",
    "raise_remote_exception_text_v1",
    "raise_thinkumentjs_station_guard_exception_v1",
    "remote_exception_type_v1",
    "targets_from_standard_A_v1",
]
