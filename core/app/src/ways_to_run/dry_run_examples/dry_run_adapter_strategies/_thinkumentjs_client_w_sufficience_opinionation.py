from __future__ import annotations

"""Reusable real-browser sufficience frontend for dry-run server strategies.

The membrane is intentionally above the browser DOM:

* lambda boots real server pages in Chromium, one isolated page per role;
* gamma/gamma_f translate standard A into sufficience DOM edits + clicks;
* roleful epsilon is observed from rendered sufficience packets;
* theta/Q/U are reconstructed from the rendered client Q;
* successful dispatches cross a post-dispatch render barrier before E may read
  Q/U: the trusted role=None page establishes the committed high-water, then
  every role page is synchronized through that same high-water;
* the generic privileged live-event sink uses the existing trusted server-side
  provisional observer capability when a case asks for an unmodulated lens;
* omega disposes browser apps first, then lets the concrete server strategy
  release its backend capability rows.

The only test acceleration is polling cadence supplied in the page bootstrap.
P/SM/C, role capability, identity, action content, opinionation selection and
canonical state are never rewritten.
"""

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
DEFAULT_PROGRESS_TERMINAL_TIMEOUT_SECONDS = 5.0
DEFAULT_BROWSER_COMMAND_TIMEOUT_SECONDS = 45.0
DEFAULT_PROGRESS_PAGE_SIZE = 500
_TERMINAL_PROGRESS_STATES = frozenset({"committed", "aborted"})


class DryRunBrowserMembraneUnsupported(RuntimeError):
    """A standard fixture cannot be represented through the true browser UI."""


@dataclass(slots=True)
class SufficienceBrowserBackendRunV1:
    base_url: str
    session_id: str
    page_urls_by_role: Dict[Optional[str], str]
    proof_dispatch_progress_url: str
    host_resource: Any = None


@dataclass(frozen=True, slots=True)
class SufficienceBrowserDispatchObservationV1:
    request_id: str
    role: Optional[str]
    identity_id: str
    browser: Mapping[str, Any]
    proof_progress_state: str
    proof_progress_error: Optional[str]


@dataclass(slots=True)
class SufficienceBrowserRunV1:
    backend: SufficienceBrowserBackendRunV1
    frontend: "SufficienceBrowserSessionV1"


def _normalized_role(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _without_event_seq_v1(event: Mapping[str, Any]) -> Dict[str, Any]:
    out = deepcopy(dict(event))
    out.pop("event_seq", None)
    return out


def _frontend_package_root_v1() -> Path:
    # .../think-frontend/src/live_vial/_js/thinkumentJS
    root = Path(THINKUMENTJS_STATIC_ROOT).resolve().parents[3]
    package = root / "package.json"
    if not package.is_file():
        raise FileNotFoundError(
            "could not locate think-frontend/package.json from installed "
            f"ThinkumentJS static root: {THINKUMENTJS_STATIC_ROOT}"
        )
    return root


class _BrowserRuntimeHostV1:
    """One persistent Node/Playwright/Chromium host for sequential cases."""

    def __init__(
        self,
        *,
        node_binary: str,
        command_timeout_seconds: float,
    ) -> None:
        binary = shutil.which(str(node_binary))
        if binary is None:
            raise RuntimeError(
                f"Node.js executable {node_binary!r} is required for the "
                "sufficience browser dry-run strategy"
            )

        runner = Path(__file__).with_name(
            "_thinkumentjs_client_w_sufficience_opinionation.mjs"
        )
        if not runner.is_file():
            raise FileNotFoundError(
                "sufficience browser Node harness is missing: "
                f"{runner}"
            )

        self._frontend_root = _frontend_package_root_v1()
        self._lock = threading.Lock()
        self._next_id = 1
        self._stderr_lines: deque[str] = deque(maxlen=120)
        self._closed = False
        self._run_open = False
        self._command_timeout_seconds = max(
            10.0,
            float(command_timeout_seconds),
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
            name="sufficience-browser-dry-run-stdout",
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr_v1,
            name="sufficience-browser-dry-run-stderr",
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
        return f"\nBrowser-host stderr:\n{stderr}" if stderr else ""

    def command_v1(
        self,
        command: str,
        *,
        timeout_seconds: Optional[float] = None,
        **payload: Any,
    ) -> Dict[str, Any]:
        if self._closed:
            raise RuntimeError("sufficience browser runtime is closed")

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
                    "sufficience browser runtime exited unexpectedly"
                    + self._failure_context_v1()
                )

            stdin = self._process.stdin
            if stdin is None:
                raise RuntimeError("sufficience browser runtime stdin is closed")
            stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            stdin.flush()

            try:
                line = self._stdout_queue.get(timeout=timeout)
            except queue.Empty as exc:
                self._terminate_process_v1()
                raise TimeoutError(
                    "sufficience browser command timed out: "
                    f"command={command!r}, timeout_seconds={timeout:g}"
                    + self._failure_context_v1()
                ) from exc

            if line is None:
                raise RuntimeError(
                    "sufficience browser runtime closed before replying to "
                    f"command={command!r}"
                    + self._failure_context_v1()
                )

            try:
                response = json.loads(line)
            except Exception as exc:
                raise RuntimeError(
                    "sufficience browser runtime emitted non-JSON stdout: "
                    f"{line!r}{self._failure_context_v1()}"
                ) from exc

            if response.get("id") != message_id:
                raise RuntimeError(
                    "sufficience browser response id mismatch: "
                    f"expected={message_id}, response={response!r}"
                )
            if response.get("ok") is not True:
                error = response.get("error") or {}
                message_text = str(
                    error.get("message") or "browser command failed"
                )
                if (
                    "cannot forge ThinkumentJS-owned canonical wire cursors"
                    in message_text
                ):
                    raise DryRunBrowserMembraneUnsupported(message_text)
                raise RuntimeError(
                    "sufficience browser command failed: "
                    f"{error.get('name')}: {message_text}; "
                    f"detail={json.dumps(error, sort_keys=True, default=str)}"
                    + self._failure_context_v1()
                )

            result = response.get("result")
            if not isinstance(result, Mapping):
                raise RuntimeError(
                    "sufficience browser command returned a non-object result: "
                    f"{result!r}"
                )
            return deepcopy(dict(result))

    def open_run_v1(
        self,
        *,
        backend: SufficienceBrowserBackendRunV1,
        request_timeout_seconds: float,
    ) -> Dict[Optional[str], str]:
        if self._run_open:
            raise RuntimeError("persistent sufficience browser already owns a run")

        clients = [
            {
                "role": role,
                "pageUrl": str(page_url),
            }
            for role, page_url in backend.page_urls_by_role.items()
        ]
        result = self.command_v1(
            "open_run",
            timeout_seconds=max(60.0, request_timeout_seconds + 30.0),
            config={
                "frontendPackageRoot": str(self._frontend_root),
                "clients": clients,
                "timeoutMs": int(request_timeout_seconds * 1000),
            },
        )

        identities: Dict[Optional[str], str] = {}
        for row in list(result.get("clients") or []):
            if not isinstance(row, Mapping):
                continue
            role = _normalized_role(row.get("role"))
            identity = str(row.get("identity_id") or "").strip()
            if not identity:
                raise AssertionError(
                    f"browser client for role {role!r} omitted identity"
                )
            if role in identities:
                raise AssertionError(
                    f"browser host returned duplicate role {role!r}"
                )
            identities[role] = identity

        expected_roles = {
            _normalized_role(role)
            for role in backend.page_urls_by_role
        }
        if set(identities) != expected_roles:
            try:
                self.command_v1("close_run", timeout_seconds=5.0)
            finally:
                self._run_open = False
            raise AssertionError(
                "browser host did not boot exactly one page per role: "
                f"expected={expected_roles!r}, actual={set(identities)!r}"
            )
        if len(set(identities.values())) != len(identities):
            raise AssertionError(
                "distinct browser roles must receive distinct browser identities"
            )

        self._run_open = True
        return identities

    def release_run_v1(self) -> None:
        if not self._run_open or self._closed:
            self._run_open = False
            return
        try:
            self.command_v1("close_run", timeout_seconds=10.0)
        finally:
            self._run_open = False

    def _terminate_process_v1(self) -> None:
        process = self._process
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

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
                    self.command_v1("close_runtime", timeout_seconds=10.0)
            except Exception:
                pass
            finally:
                self._closed = True
                self._run_open = False
            if process.poll() is None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._terminate_process_v1()

        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream and stream.close()
            except Exception:
                pass


class _ProofProgressPortV1:
    def __init__(
        self,
        *,
        backend: SufficienceBrowserBackendRunV1,
        request_timeout_seconds: float,
    ) -> None:
        self.backend = backend
        self.request_timeout_seconds = float(request_timeout_seconds)

    def read_v1(
        self,
        *,
        identity_id: str,
        request_id: str,
        after: int,
    ) -> Dict[str, Any]:
        path = self.backend.proof_dispatch_progress_url
        parsed = urlsplit(str(path))
        url = (
            str(path)
            if parsed.scheme in {"http", "https"} and parsed.netloc
            else urljoin(
                f"{self.backend.base_url.rstrip('/')}/",
                str(path).lstrip("/"),
            )
        )
        url = f"{url}?{urlencode({
            'identity_id': str(identity_id),
            'request_id': str(request_id),
            'after_seq': int(after),
            'after_eps_seq': int(after),
            'after_provisional_seq': int(after),
            'limit': DEFAULT_PROGRESS_PAGE_SIZE,
        })}"

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
                "browser proof-progress read failed: "
                f"status={status}, packet={packet!r}"
            )
        return deepcopy(dict(packet))


class SufficienceBrowserSessionV1:
    def __init__(
        self,
        *,
        backend: SufficienceBrowserBackendRunV1,
        runtime: _BrowserRuntimeHostV1,
        request_timeout_seconds: float,
        progress_poll_seconds: float,
        progress_terminal_timeout_seconds: float,
    ) -> None:
        self.backend = backend
        self.runtime = runtime
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.progress_poll_seconds = max(0.001, float(progress_poll_seconds))
        self.progress_terminal_timeout_seconds = max(
            self.progress_poll_seconds,
            float(progress_terminal_timeout_seconds),
        )
        self._closed = False
        self._known_high_water = 0
        self._dispatch_pool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="sufficience-browser-dispatch",
        )
        self.identities_by_role = self.runtime.open_run_v1(
            backend=backend,
            request_timeout_seconds=self.request_timeout_seconds,
        )
        if None not in self.identities_by_role:
            raise ValueError(
                "real browser dry run requires a role=None proof page"
            )
        self.proof_progress = _ProofProgressPortV1(
            backend=backend,
            request_timeout_seconds=self.request_timeout_seconds,
        )

    def close_v1(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._dispatch_pool.shutdown(wait=True, cancel_futures=True)
        finally:
            self.runtime.release_run_v1()

    def _note_high_water_v1(self, value: Any) -> None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            self._known_high_water = max(self._known_high_water, value)

    def identity_for_role_v1(self, role: Optional[str]) -> str:
        key = _normalized_role(role)
        try:
            return self.identities_by_role[key]
        except KeyError as exc:
            raise KeyError(f"no sufficience browser page for role {key!r}") from exc

    def sync_cursor_v1(self, *, role: Optional[str]) -> int:
        result = self.runtime.command_v1(
            "sync_cursor",
            role=_normalized_role(role),
            knownHighWater=self._known_high_water,
            timeoutMs=int(self.request_timeout_seconds * 1000),
        )
        cursor = int(result["cursor"])
        self._note_high_water_v1(cursor)
        return cursor

    def sync_all_roles_v1(self) -> int:
        """Synchronize every rendered role page through one committed barrier.

        A dispatch result and server-side commit can become observable before
        every Chromium page has rendered the corresponding terminal controller
        event. Reading Q/U in that interval produces an impossible truncated
        action envelope: middle datum rows are present while controller-end is
        still absent.

        The trusted role=None page is synchronized first. Combined with the
        authoritative dispatch high-water already recorded by dispatch_v1(),
        that establishes one post-dispatch barrier. Every roleful page is then
        forced through at least that exact barrier before E may inspect
        rendered state.

        Do not replace this with a sleep. The requirement is causal:
        commit/high-water -> render-through-high-water -> expectation read.
        """

        if self._closed:
            raise RuntimeError("sufficience browser session is closed")

        # Synchronize the trusted unmodulated page first. dispatch_v1() has
        # already folded the dispatch receipt's authoritative after-event
        # sequence into _known_high_water when one was available.
        proof_cursor = self.sync_cursor_v1(role=None)
        target_high_water = max(
            int(proof_cursor),
            int(self._known_high_water),
        )

        # Freeze the barrier for this pass. One page being incidentally ahead
        # must not move the goalposts for pages synchronized later in the loop.
        for role in self.identities_by_role:
            normalized_role = _normalized_role(role)
            if normalized_role is None:
                continue

            result = self.runtime.command_v1(
                "sync_cursor",
                role=normalized_role,
                knownHighWater=target_high_water,
                timeoutMs=int(self.request_timeout_seconds * 1000),
            )
            cursor = int(result["cursor"])
            self._note_high_water_v1(cursor)

            if cursor < target_high_water:
                raise AssertionError(
                    "browser role page did not render through the committed "
                    "post-dispatch high-water: "
                    f"role={normalized_role!r}, "
                    f"cursor={cursor}, "
                    f"target_high_water={target_high_water}"
                )

        return target_high_water

    def read_context_v1(self, *, role: Optional[str]) -> Mapping[str, Any]:
        result = self.runtime.command_v1(
            "read_context",
            role=_normalized_role(role),
            knownHighWater=self._known_high_water,
            timeoutMs=int(self.request_timeout_seconds * 1000),
        )
        U = result.get("U")
        if not isinstance(U, Mapping):
            raise AssertionError(
                "rendered sufficience blanket does not contain current U: "
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
        page = self.runtime.command_v1(
            "poll_local",
            role=_normalized_role(role),
            afterEventSeq=int(after_event_seq),
            limit=limit,
            knownHighWater=self._known_high_water,
            timeoutMs=int(self.request_timeout_seconds * 1000),
        )
        self._note_high_water_v1(page.get("session_latest_event_seq"))
        return page

    def _drain_progress_once_v1(
        self,
        *,
        identity_id: str,
        request_id: str,
        after: int,
        sink: DryRunLiveEventSinkV1,
    ) -> tuple[int, str, Optional[str]]:
        cursor = int(after)

        while True:
            page = self.proof_progress.read_v1(
                identity_id=identity_id,
                request_id=request_id,
                after=cursor,
            )
            state = str(page.get("state") or "")
            error = (
                None
                if page.get("error") is None
                else str(page.get("error"))
            )
            rows = [
                row
                for row in list(page.get("rows") or page.get("events") or [])
                if isinstance(row, Mapping)
            ]
            before = cursor

            for row in rows:
                sink(deepcopy(dict(row)))

                provisional_seq = int(row.get("eps_seq") or row.get("provisional_seq") or 0)
                if provisional_seq <= cursor:
                    raise AssertionError(
                        "dispatch-progress repeated/regressed a provisional "
                        f"event: cursor={cursor}, row={dict(row)!r}"
                    )
                cursor = provisional_seq

            next_candidate = (
                page.get("next_after_eps_seq")
                if page.get("next_after_eps_seq") is not None
                else (
                    page.get("next_after_seq")
                    if page.get("next_after_seq") is not None
                    else page.get("next_after_provisional_seq")
                )
            )
            next_cursor = int(next_candidate if next_candidate is not None else cursor)
            if next_cursor < cursor:
                raise AssertionError(
                    "dispatch-progress page cursor regressed behind returned "
                    f"events: events_cursor={cursor}, page_cursor={next_cursor}"
                )
            cursor = next_cursor

            # Full pages may have retained backlog immediately behind them.
            # Drain that backlog without sleeping. A short page exhausted the
            # currently published rows; the caller decides whether to sleep,
            # finish on terminal, or continue waiting for terminal publication.
            if len(rows) < DEFAULT_PROGRESS_PAGE_SIZE:
                return cursor, state, error
            if cursor <= before:
                raise AssertionError(
                    "dispatch-progress full page made no provisional cursor "
                    "progress"
                )

    def _drain_progress_until_terminal_v1(
        self,
        *,
        identity_id: str,
        request_id: str,
        after: int,
        sink: DryRunLiveEventSinkV1,
        timeout_seconds: Optional[float] = None,
    ) -> tuple[int, str, Optional[str]]:
        """Drain all currently/live-published epsilon until channel terminal.

        The dispatch HTTP/job result and the provisional observer channel are
        distinct observable surfaces. A successful dispatch result can become
        visible a few milliseconds before the trusted mirror has published its
        final generated controller-end rows. One single "final" GET is
        therefore racy. This helper makes the proof Markovian: return only once
        the channel itself says committed/aborted, or fail on a small explicit
        proof-channel deadline.
        """

        deadline = time.monotonic() + (
            self.progress_terminal_timeout_seconds
            if timeout_seconds is None
            else max(self.progress_poll_seconds, float(timeout_seconds))
        )
        cursor = int(after)
        state = ""
        error: Optional[str] = None

        while True:
            cursor, state, error = self._drain_progress_once_v1(
                identity_id=identity_id,
                request_id=request_id,
                after=cursor,
                sink=sink,
            )
            if state in _TERMINAL_PROGRESS_STATES:
                return cursor, state, error

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "dispatch-progress channel did not reach terminal state: "
                    f"request_id={request_id!r}, identity_id={identity_id!r}, "
                    f"state={state!r}, after_provisional_seq={cursor}"
                )
            time.sleep(min(self.progress_poll_seconds, remaining))

    def _terminal_error_after_failure_v1(
        self,
        *,
        identity_id: str,
        request_id: str,
    ) -> tuple[str, Optional[str]]:
        try:
            _after, state, error = self._drain_progress_once_v1(
                identity_id=identity_id,
                request_id=request_id,
                after=0,
                sink=lambda _event: None,
            )
            return state, error
        except Exception:
            return "", None

    @staticmethod
    def _reached_transport_v1(result: Mapping[str, Any]) -> bool:
        receipt = result.get("local_receipt")
        if not isinstance(receipt, Mapping):
            return result.get("dispatch_result") is not None
        if receipt.get("kind") == "thinkument_outbound_dispatch_validation_v1":
            return receipt.get("ok") is True
        status = receipt.get("status")
        return isinstance(status, int) and not isinstance(status, bool)

    def dispatch_v1(
        self,
        *,
        A: Mapping[str, Any],
        funked: bool,
        live_event_sink: Optional[DryRunLiveEventSinkV1],
    ) -> SufficienceBrowserDispatchObservationV1:
        if self._closed:
            raise RuntimeError("sufficience browser session is closed")
        if A.get("my_current_event_seq_number") is not None:
            raise DryRunBrowserMembraneUnsupported(
                "real sufficience DOM cannot forge ThinkumentJS-owned "
                "my_current_event_seq_number; this is a transport-boundary "
                "fixture, not a browser-user action"
            )

        role = _normalized_role(A.get("role"))
        identity_id = self.identity_for_role_v1(role)
        request_id = f"sufficience-browser-dry-run-{uuid4().hex}"
        kwargs = {
            "role": role,
            "A": deepcopy(dict(A)),
            "funked": bool(funked),
            "requestId": request_id,
            "knownHighWater": self._known_high_water,
            "timeoutMs": int(self.request_timeout_seconds * 1000),
        }

        proof_state = ""
        proof_error: Optional[str] = None

        if live_event_sink is None:
            browser_result = self.runtime.command_v1("dispatch", **kwargs)
            receipt = browser_result.get("local_receipt")
            if (
                isinstance(receipt, Mapping)
                and isinstance(receipt.get("status"), int)
                and receipt.get("status") >= 500
            ):
                proof_state, proof_error = self._terminal_error_after_failure_v1(
                    identity_id=identity_id,
                    request_id=request_id,
                )
        else:
            future = self._dispatch_pool.submit(
                self.runtime.command_v1,
                "dispatch",
                **kwargs,
            )
            after = 0

            # Let the POST/worker open its provisional channel before the first
            # proof read. This avoids paying an eager not_found GET on the fast
            # path while preserving live epsilon for longer dispatches.
            if not future.done():
                time.sleep(self.progress_poll_seconds)

            while not future.done():
                after, proof_state, proof_error = self._drain_progress_once_v1(
                    identity_id=identity_id,
                    request_id=request_id,
                    after=after,
                    sink=live_event_sink,
                )
                if not future.done():
                    time.sleep(self.progress_poll_seconds)

            browser_result = future.result()

            # Drain any final eps events published as dispatch completed
            after, proof_state, proof_error = self._drain_progress_once_v1(
                identity_id=identity_id,
                request_id=request_id,
                after=after,
                sink=live_event_sink,
            )

        # Record every authoritative post-dispatch cursor exposed by the
        # browser/receipt before the strategy establishes its render barrier.
        #
        # after_cursor is the initiating page's rendered/dispatch cursor.
        # dispatch_concurrency.after_event_seq is the stronger server receipt
        # cursor when supplied by the transport.
        self._note_high_water_v1(browser_result.get("after_cursor"))
        dispatch_result = browser_result.get("dispatch_result")
        if isinstance(dispatch_result, Mapping):
            concurrency = dispatch_result.get("dispatch_concurrency")
            if isinstance(concurrency, Mapping):
                self._note_high_water_v1(concurrency.get("after_event_seq"))

        return SufficienceBrowserDispatchObservationV1(
            request_id=request_id,
            role=role,
            identity_id=identity_id,
            browser=browser_result,
            proof_progress_state=proof_state,
            proof_progress_error=proof_error,
        )


class ThinkumentJSSufficienceBrowserDryRunStrategy(BaseDryRunStrategy, ABC):
    """Base strategy for one server + real Chromium + sufficience DOM."""

    def __init__(
        self,
        *,
        node_binary: str = DEFAULT_NODE_BINARY,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        progress_poll_seconds: float = DEFAULT_PROGRESS_POLL_SECONDS,
        progress_terminal_timeout_seconds: float = (
            DEFAULT_PROGRESS_TERMINAL_TIMEOUT_SECONDS
        ),
        browser_command_timeout_seconds: float = (
            DEFAULT_BROWSER_COMMAND_TIMEOUT_SECONDS
        ),
    ) -> None:
        timeout = float(request_timeout_seconds)
        if timeout <= 0:
            raise ValueError("request_timeout_seconds must be > 0")
        self._node_binary = str(node_binary)
        self._request_timeout_seconds = timeout
        self._progress_poll_seconds = max(0.001, float(progress_poll_seconds))
        self._progress_terminal_timeout_seconds = max(
            self._progress_poll_seconds,
            float(progress_terminal_timeout_seconds),
        )
        self._browser_command_timeout_seconds = max(
            10.0,
            float(browser_command_timeout_seconds),
        )
        self._runtime: Optional[_BrowserRuntimeHostV1] = None

    @abstractmethod
    def _start_backend_v1(
        self,
        *,
        program: Mapping[str, Any],
        session_metadata: Mapping[str, Any],
        initial_parameter_overrides: Mapping[str, Any],
    ) -> SufficienceBrowserBackendRunV1:
        raise NotImplementedError

    @abstractmethod
    def _close_backend_v1(
        self,
        *,
        backend: SufficienceBrowserBackendRunV1,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def _normalize_dispatch_observation_v1(
        self,
        *,
        backend: SufficienceBrowserBackendRunV1,
        A: Mapping[str, Any],
        observation: SufficienceBrowserDispatchObservationV1,
    ) -> Mapping[str, Any]:
        raise NotImplementedError

    def _runtime_v1(self) -> _BrowserRuntimeHostV1:
        runtime = self._runtime
        if runtime is None:
            runtime = _BrowserRuntimeHostV1(
                node_binary=self._node_binary,
                command_timeout_seconds=self._browser_command_timeout_seconds,
            )
            self._runtime = runtime
        return runtime

    def close_strategy_v1(self) -> None:
        runtime = self._runtime
        self._runtime = None
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
        frontend: Optional[SufficienceBrowserSessionV1] = None
        try:
            frontend = SufficienceBrowserSessionV1(
                backend=backend,
                runtime=self._runtime_v1(),
                request_timeout_seconds=self._request_timeout_seconds,
                progress_poll_seconds=self._progress_poll_seconds,
                progress_terminal_timeout_seconds=(
                    self._progress_terminal_timeout_seconds
                ),
            )
            run = SufficienceBrowserRunV1(
                backend=backend,
                frontend=frontend,
            )
            self.latest_committed_event_seq_v1(run=run)
            return run
        except Exception:
            try:
                if frontend is not None:
                    frontend.close_v1()
                elif self._runtime is not None:
                    self._runtime.release_run_v1()
            finally:
                self._close_backend_v1(backend=backend)
            raise

    @staticmethod
    def _run_v1(run: DryRunRunHandleV1) -> SufficienceBrowserRunV1:
        if not isinstance(run, SufficienceBrowserRunV1):
            raise TypeError("wrong run handle for sufficience browser strategy")
        return run

    def close_run_v1(self, *, run: DryRunRunHandleV1) -> None:
        value = self._run_v1(run)
        try:
            value.frontend.close_v1()
        finally:
            self._close_backend_v1(backend=value.backend)

    @staticmethod
    def _assert_dom_epsilon_theta_v1(
        *,
        role: Optional[str],
        observation: SufficienceBrowserDispatchObservationV1,
    ) -> None:
        browser = observation.browser
        epsilon = [
            deepcopy(dict(event))
            for event in list(browser.get("epsilon_events") or [])
            if isinstance(event, Mapping)
        ]
        theta = [
            deepcopy(dict(event))
            for event in list(browser.get("theta_events") or [])
            if isinstance(event, Mapping)
        ]
        for event in epsilon:
            if "event_seq" in event:
                raise AssertionError(
                    "rendered sufficience epsilon illegally carried canonical "
                    f"event_seq: {event!r}"
                )

    @staticmethod
    def _assert_browser_identity_v1(
        *,
        funked: bool,
        observation: SufficienceBrowserDispatchObservationV1,
    ) -> None:
        request_id = observation.request_id
        expected = observation.identity_id
        controllers = [
            event
            for event in list(observation.browser.get("theta_events") or [])
            if (
                isinstance(event, Mapping)
                and event.get("kind") == "controller_loop_event_v1"
                and event.get("dispatch_id") == request_id
                and event.get("dispatcher_identity_id") is not None
            )
        ]
        for event in controllers:
            actual = str(event.get("dispatcher_identity_id"))
            if not funked:
                if actual != expected:
                    raise AssertionError(
                        "server did not observe the identity rendered into the "
                        f"browser page: expected={expected!r}, actual={actual!r}"
                    )
                continue
            if actual == expected:
                continue
            if not (
                actual.startswith("funkedauto-")
                and actual.endswith(f"-{expected}")
            ):
                raise AssertionError(
                    "funked browser dispatcher identity is not rooted in the "
                    f"initiating browser identity: {actual!r}"
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
        if packet.get("rejected") is True:
            return packet

        # Dispatch completion and rendered-client completion are separate
        # observable surfaces.
        #
        # The server may already have committed controller-end while a role
        # page's local rendered Q still ends at a middle datum event. P10's
        # S1 -> S2 transition exposes that race particularly clearly because
        # destination-scope mount messages are emitted immediately before the
        # terminal controller snapshot.
        #
        # Establish an explicit render barrier before any caller can inspect
        # Q/U through committed_events_v1(), poll_committed_events_v1(), or
        # read_context_v1().
        value.frontend.sync_all_roles_v1()

        self._assert_browser_identity_v1(
            funked=funked,
            observation=observation,
        )
        self._assert_dom_epsilon_theta_v1(
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
        return self._run_v1(run).frontend.sync_cursor_v1(role=None)

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
        return self._run_v1(run).frontend.read_context_v1(role=role)


__all__ = [
    "DEFAULT_BROWSER_COMMAND_TIMEOUT_SECONDS",
    "DEFAULT_NODE_BINARY",
    "DEFAULT_PROGRESS_PAGE_SIZE",
    "DEFAULT_PROGRESS_POLL_SECONDS",
    "DEFAULT_PROGRESS_TERMINAL_TIMEOUT_SECONDS",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "DryRunBrowserMembraneUnsupported",
    "SufficienceBrowserBackendRunV1",
    "SufficienceBrowserDispatchObservationV1",
    "SufficienceBrowserRunV1",
    "SufficienceBrowserSessionV1",
    "ThinkumentJSSufficienceBrowserDryRunStrategy",
]