from __future__ import annotations

"""Real-local-Flask adapter for the standard P / SM / C / A / E dry run.

The strategy owns only translation and transport.  It never imports
``_thinksessions.run.run_from_here`` and it does not reproduce dry-run proof
logic.

One case is hosted by one real threaded Werkzeug WSGI server bound to an
ephemeral loopback port.  The strategy drives that server only through HTTP for
run reads and writes.  App construction is the hosting bootstrap boundary; the
session itself is thereafter observed and mutated through Flask capabilities.

Performance note
----------------
``socketserver.BaseServer.serve_forever`` defaults to a 0.5 second shutdown
poll interval.  A dry-run suite creates one server per case, so accepting that
default can add roughly ``case_count * 0.5s`` of teardown latency.  This
strategy deliberately supplies a small poll interval to ``serve_forever``.
That changes only shutdown responsiveness; it does not bypass Flask, HTTP,
request parsing, role-sealed handles, provisional progress, or the underlying
runtime.
"""

import builtins
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Dict, Mapping, Optional
from urllib.error import HTTPError as UrlHTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from _thinkprogram.thinkprogramTM.api import (
    LANG_THINK_PROGRAM_V1,
    overlay_initial_parameter_overrides_onto_program_v1,
)
from live_vial._flask._helpers_for_local_server import (
    build_local_flask_launch_spec,
)
from live_vial._flask.adapter import build_access_handle_urls
from live_vial._flask.server_wrapper import (
    close_app_sessions,
    create_app_for_program,
    get_app_launch_bundle,
)
from werkzeug.serving import WSGIRequestHandler, make_server

from .BASE_CLASS import (
    BaseDryRunStrategy,
    DryRunLiveEventSinkV1,
    DryRunRunHandleV1,
)


TYPED_EXCEPTION_KIND_V1 = "thinkument_local_flask_typed_exception_v1"

DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_PROGRESS_POLL_SECONDS = 0.01
DEFAULT_SERVER_SHUTDOWN_POLL_SECONDS = 0.01

_FLASK_ONLY_TOP_LEVEL_RECEIPT_KEYS = frozenset(
    {
        "request_id",
    }
)
_FLASK_ONLY_CONCURRENCY_KEYS = frozenset(
    {
        "coordination_layer",
        "reason",
        "request_id",
    }
)


class _QuietWSGIRequestHandler(WSGIRequestHandler):
    def log(self, type: str, message: str, *args: Any) -> None:
        del type, message, args


@dataclass(frozen=True, slots=True)
class _HTTPResult:
    status: int
    packet: Dict[str, Any]


@dataclass(slots=True)
class FlaskFacadeBackendOnlyRunV1:
    app: Any
    server: Any
    thread: threading.Thread
    base_url: str
    session_id: str
    endpoints_by_role: Dict[Optional[str], Dict[str, str]]
    unmodulated_endpoints: Dict[str, str]


class FlaskFacadeBackendOnlyDryRunStrategy(BaseDryRunStrategy):
    """Drive one dry-run case as an HTTP client of a real local Flask server."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        progress_poll_seconds: float = DEFAULT_PROGRESS_POLL_SECONDS,
        server_shutdown_poll_seconds: float = (
            DEFAULT_SERVER_SHUTDOWN_POLL_SECONDS
        ),
    ) -> None:
        normalized_host = str(host or "").strip()
        if not normalized_host:
            raise ValueError("host must be non-empty")

        request_timeout = float(request_timeout_seconds)
        if request_timeout <= 0:
            raise ValueError("request_timeout_seconds must be > 0")

        self._host = normalized_host
        self._request_timeout_seconds = request_timeout
        self._progress_poll_seconds = max(
            0.001,
            float(progress_poll_seconds),
        )
        self._server_shutdown_poll_seconds = max(
            0.001,
            float(server_shutdown_poll_seconds),
        )

    @property
    def strategy_name(self) -> str:
        return "flask-facade-backend-only-strategy"

    @property
    def server_shutdown_poll_seconds(self) -> float:
        """Werkzeug serve-loop poll interval used for responsive teardown.

        This is intentionally observable so the Flask dry-run sheet can guard
        the efficiency invariant that removed the historical per-case
        ``serve_forever()`` shutdown tax without bypassing the real HTTP server.
        """
        return self._server_shutdown_poll_seconds

    # ------------------------------------------------------------------ launch

    @staticmethod
    def _effective_program(
        program: Mapping[str, Any],
        C: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Resolve standard C into the exact authored P accepted by Flask."""
        if not C:
            return deepcopy(dict(program))
        return deepcopy(
            overlay_initial_parameter_overrides_onto_program_v1(
                deepcopy(dict(program)),
                initial_parameter_overrides=deepcopy(dict(C)),
            )
        )

    @staticmethod
    def _split_SM(
        SM: Mapping[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """Translate standard SM into the local-Flask launch partitions."""
        metadata = deepcopy(dict(SM or {}))
        roles = metadata.pop("roles", {}) or {}
        policy = metadata.pop("role_mismatch_policy", {}) or {}

        if not isinstance(roles, Mapping):
            raise TypeError("session_metadata.roles must be a mapping")
        if not isinstance(policy, Mapping):
            raise TypeError(
                "session_metadata.role_mismatch_policy must be a mapping"
            )

        normalized_roles = {
            str(name): deepcopy(value)
            for name, value in dict(roles).items()
        }
        return metadata, normalized_roles, deepcopy(dict(policy))

    @staticmethod
    def _relative_endpoints(app: Any, access_id: str) -> Dict[str, str]:
        with app.test_request_context("/"):
            row = build_access_handle_urls(
                access_ids={"selected": str(access_id)}
            )["selected"]
        return {
            key: str(value)
            for key, value in row.items()
            if key != "role"
        }

    def _serve_forever(self, server: Any) -> None:
        server.serve_forever(
            poll_interval=self._server_shutdown_poll_seconds,
        )

    def start_run_v1(
        self,
        *,
        program: Mapping[str, Any],
        session_metadata: Mapping[str, Any],
        initial_parameter_overrides: Mapping[str, Any],
    ) -> DryRunRunHandleV1:
        metadata, roles, policy = self._split_SM(session_metadata)
        wrapper = {
            "program_language": LANG_THINK_PROGRAM_V1,
            "program": self._effective_program(
                program,
                initial_parameter_overrides,
            ),
            "session_surface": {
                "session_metadata": metadata,
                "roles": roles,
                "role_mismatch_policy": policy,
                "public_view_role": next(iter(roles), None),
                "start_on_create": False,
                # The standard strategy contract includes role=None reads,
                # role=None actions, and canonical live epsilon.  Ordinary
                # browser handles remain role-sealed; this extra opaque
                # capability is opt-in and exists only for trusted local
                # adapters such as this strategy.
                "include_unmodulated_access": True,
                # Preserve the standard preflight-exception grammar across an
                # HTTP 500 boundary without exposing tracebacks.
                "expose_typed_exceptions": True,
            },
        }
        app = create_app_for_program(
            launch_spec=build_local_flask_launch_spec(wrapper=wrapper)
        )
        bundle = get_app_launch_bundle(app)

        unmodulated_access_id = str(
            bundle.get("unmodulated_access_id") or ""
        ).strip()
        if not unmodulated_access_id:
            close_app_sessions(app)
            raise AssertionError("Flask launch omitted unmodulated access")

        endpoints_by_role: Dict[Optional[str], Dict[str, str]] = {
            None: self._relative_endpoints(app, unmodulated_access_id)
        }
        for role in roles:
            endpoints_by_role[str(role)] = self._relative_endpoints(
                app,
                str(bundle["access_ids"][str(role)]),
            )

        server = make_server(
            self._host,
            0,
            app,
            threaded=True,
            request_handler=_QuietWSGIRequestHandler,
        )
        thread = threading.Thread(
            target=self._serve_forever,
            args=(server,),
            name=f"thinkument-dry-run-flask-{bundle['session_id']}",
            daemon=True,
        )
        thread.start()

        run = FlaskFacadeBackendOnlyRunV1(
            app=app,
            server=server,
            thread=thread,
            base_url=f"http://{self._host}:{int(server.server_port)}",
            session_id=str(bundle["session_id"]),
            endpoints_by_role=endpoints_by_role,
            unmodulated_endpoints=endpoints_by_role[None],
        )

        # One real HTTP read is the readiness check.  make_server has already
        # bound the socket, but this proves the request loop is actually live.
        try:
            self.latest_committed_event_seq_v1(run=run)
        except Exception:
            self.close_run_v1(run=run)
            raise

        return run

    def close_run_v1(self, *, run: DryRunRunHandleV1) -> None:
        value = self._run(run)
        try:
            value.server.shutdown()
        finally:
            try:
                value.server.server_close()
            finally:
                value.thread.join(timeout=5)
                close_app_sessions(value.app)

    @staticmethod
    def _run(run: DryRunRunHandleV1) -> FlaskFacadeBackendOnlyRunV1:
        if not isinstance(run, FlaskFacadeBackendOnlyRunV1):
            raise TypeError("wrong run handle for Flask dry-run strategy")
        return run

    # --------------------------------------------------------------- HTTP seam

    def _http(
        self,
        run: FlaskFacadeBackendOnlyRunV1,
        path: str,
        *,
        method: str = "GET",
        payload: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
    ) -> _HTTPResult:
        url = f"{run.base_url.rstrip('/')}/{str(path).lstrip('/')}"
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
                timeout=self._request_timeout_seconds,
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

        return _HTTPResult(
            status=status,
            packet=(
                dict(parsed)
                if isinstance(parsed, Mapping)
                else {"value": parsed}
            ),
        )

    def _endpoints(
        self,
        run: FlaskFacadeBackendOnlyRunV1,
        role: Optional[str],
    ) -> Dict[str, str]:
        key = None if role in (None, "") else str(role).strip() or None
        try:
            return run.endpoints_by_role[key]
        except KeyError as exc:
            raise KeyError(
                f"no Flask access handle for role {key!r}"
            ) from exc

    # ------------------------------------------------------------ A translation

    @staticmethod
    def _targets(A: Mapping[str, Any]) -> list[str]:
        out: list[str] = []

        fill = A.get("user_fill")
        if isinstance(fill, Mapping):
            out.extend(str(key).split(".", 1)[0] for key in fill)

        signal = A.get("user_signal")
        if isinstance(signal, Mapping) and signal.get("datum_id"):
            out.append(str(signal["datum_id"]))

        return list(dict.fromkeys(target for target in out if target))

    @staticmethod
    def _remote_exception_type(name: str) -> type[Exception]:
        candidate = getattr(builtins, name, None)
        if isinstance(candidate, type) and issubclass(candidate, Exception):
            return candidate

        for module_name in ("__exceptions.engine", "__exceptions"):
            try:
                candidate = getattr(import_module(module_name), name, None)
            except Exception:
                continue
            if isinstance(candidate, type) and issubclass(candidate, Exception):
                return candidate

        return type(name or "RemoteFlaskDryRunError", (RuntimeError,), {})

    @classmethod
    def _raise_remote_exception(cls, packet: Mapping[str, Any]) -> None:
        name = str(
            packet.get("exception_type") or "RemoteFlaskDryRunError"
        )
        message = str(packet.get("message") or "remote Flask exception")
        exc_type = cls._remote_exception_type(name)

        try:
            exc = exc_type(message)
        except Exception:
            exc = type(name, (RuntimeError,), {})(message)

        raise exc

    def _invalid_cursor_packet(
        self,
        run: FlaskFacadeBackendOnlyRunV1,
        A: Mapping[str, Any],
    ) -> Dict[str, Any]:
        observed = self.latest_committed_event_seq_v1(run=run)
        return {
            "kind": "live_session_dispatch_rejected_v1",
            "ok": False,
            "applied": False,
            "rejected": True,
            "rejection_kind": "invalid_event_cursor",
            "dispatch_outcome": "stale_rejected",
            "write_committed": False,
            "events_only": False,
            "session_id": run.session_id,
            "dispatch_staleness": {
                "kind": "live_session_dispatch_staleness_receipt_v1",
                "checked": True,
                "outcome": "rejected",
                "reason": "invalid_event_cursor",
                "supplied_event_seq": None,
                "observed_event_seq": observed,
                "scope_last_changed_seq": 0,
                "target_last_changed_seq": 0,
                "target_count": len(self._targets(A)),
            },
        }

    @staticmethod
    def _standard_receipt(packet: Mapping[str, Any]) -> Dict[str, Any]:
        """Normalize Flask transport facts back to standard dry-run facts.

        The generic P/SM/C/A/E machinery must not acquire Flask-only receipt
        keys.  Accepted dispatches retain the same highest-facade concurrency
        pocket as the direct strategy.  Eventless rejections retain the direct
        strategy's rejection shape, which has no concurrency pocket.
        """
        out = deepcopy(dict(packet))

        for key in _FLASK_ONLY_TOP_LEVEL_RECEIPT_KEYS:
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
            for key in _FLASK_ONLY_CONCURRENCY_KEYS:
                normalized.pop(key, None)
            normalized["guarding"] = (
                "per_session_serialized_highest_facade"
            )
            out["dispatch_concurrency"] = normalized

        return out

    def _dispatch_payload(
        self,
        run: FlaskFacadeBackendOnlyRunV1,
        A: Mapping[str, Any],
        *,
        request_id: str,
        funked: bool,
    ) -> Dict[str, Any]:
        cursor = A.get("my_current_event_seq_number")
        if cursor is None:
            # The public Flask contract requires an exact integer cursor.
            # Standard A permits None, meaning this sequential client did not
            # explicitly provide one.  The faithful client-side translation is
            # to synchronize to canonical high-water immediately before POST.
            cursor = self.latest_committed_event_seq_v1(run=run)

        out = {
            "action": A.get("action", "STEP"),
            "identity_id": str(A.get("identity_id") or ""),
            "request_id": request_id,
            "my_current_event_seq_number": cursor,
            "user_fill": deepcopy(A.get("user_fill")),
            "user_signal": deepcopy(A.get("user_signal")),
        }
        if funked and "chainreactionTM_config" in A:
            out["chainreactionTM_config"] = deepcopy(
                A["chainreactionTM_config"]
            )
        return out

    def _progress(
        self,
        run: FlaskFacadeBackendOnlyRunV1,
        *,
        request_id: str,
        identity_id: str,
        after: int,
    ) -> Dict[str, Any]:
        eps_endpoint = run.unmodulated_endpoints.get("eps") or run.unmodulated_endpoints.get("dispatchProgress")
        result = self._http(
            run,
            eps_endpoint,
            query={
                "request_id": request_id,
                "identity_id": identity_id,
                "after_seq": after,
                "after_eps_seq": after,
                "after_provisional_seq": after,
                "limit": 500,
            },
        )
        if result.status != 200:
            raise AssertionError(
                "Flask progress read failed: "
                f"{result.status} {result.packet!r}"
            )
        return result.packet

    @staticmethod
    def _emit_progress(
        page: Mapping[str, Any],
        *,
        after: int,
        sink: DryRunLiveEventSinkV1,
    ) -> int:
        cursor = int(after)
        rows = list(page.get("rows") or page.get("events") or [])
        for row in rows:
            if not isinstance(row, Mapping):
                continue

            sink(deepcopy(dict(row)))

            cursor = max(
                cursor,
                int(row.get("eps_seq") or row.get("provisional_seq") or 0),
            )

        return cursor

    def _dispatch_http(
        self,
        run: FlaskFacadeBackendOnlyRunV1,
        A: Mapping[str, Any],
        *,
        funked: bool,
        live_event_sink: Optional[DryRunLiveEventSinkV1],
    ) -> Mapping[str, Any]:
        raw_role = A.get("role")
        role = (
            None
            if raw_role in (None, "")
            else str(raw_role).strip() or None
        )
        endpoints = self._endpoints(run, role)

        request_id = f"dry-run-{uuid4().hex}"
        identity_id = str(A.get("identity_id") or "")
        payload = self._dispatch_payload(
            run,
            A,
            request_id=request_id,
            funked=funked,
        )
        path = endpoints[
            "dispatchFunked" if funked else "dispatch"
        ]

        if live_event_sink is None:
            response = self._http(
                run,
                path,
                method="POST",
                payload=payload,
            )
        else:
            # The POST remains in flight on one client thread while this thread
            # reads the request-scoped unmodulated progress capability.
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    self._http,
                    run,
                    path,
                    method="POST",
                    payload=payload,
                )

                after = 0
                last_state = ""

                while not future.done():
                    page = self._progress(
                        run,
                        request_id=request_id,
                        identity_id=identity_id,
                        after=after,
                    )
                    after = self._emit_progress(
                        page,
                        after=after,
                        sink=live_event_sink,
                    )
                    last_state = str(page.get("state") or "")

                    if future.done():
                        break
                    time.sleep(self._progress_poll_seconds)

                response = future.result()

                # If the last in-flight page was not already finalized, one
                # final page drains events published just before the POST
                # completed.  No busy final polling is required because a
                # returned dispatch response is after publisher finalization.
                if last_state not in {"committed", "aborted"}:
                    final = self._progress(
                        run,
                        request_id=request_id,
                        identity_id=identity_id,
                        after=after,
                    )
                    self._emit_progress(
                        final,
                        after=after,
                        sink=live_event_sink,
                    )

        packet = response.packet

        if (
            response.status == 403
            and packet.get("rejection_kind") == "permission_denied"
        ):
            targets = self._targets(A)
            raise PermissionError(
                "permission denied for "
                + (", ".join(targets) or "submitted action")
            )

        raw_cursor = A.get("my_current_event_seq_number")
        if (
            response.status == 400
            and raw_cursor is not None
            and type(raw_cursor) is not int
        ):
            return self._invalid_cursor_packet(run, A)

        if (
            response.status >= 500
            and packet.get("kind") == TYPED_EXCEPTION_KIND_V1
        ):
            self._raise_remote_exception(packet)

        if response.status not in {200, 409}:
            raise AssertionError(
                "Flask dispatch failed: "
                f"status={response.status}, "
                f"packet={packet!r}, A={dict(A)!r}"
            )

        return self._standard_receipt(packet)

    def dispatch_action_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        A: Mapping[str, Any],
        live_event_sink: Optional[DryRunLiveEventSinkV1] = None,
    ) -> Mapping[str, Any]:
        return self._dispatch_http(
            self._run(run),
            A,
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
        return self._dispatch_http(
            self._run(run),
            A,
            funked=True,
            live_event_sink=live_event_sink,
        )

    # ----------------------------------------------------------- theta / Q reads

    def latest_committed_event_seq_v1(
        self,
        *,
        run: DryRunRunHandleV1,
    ) -> int:
        value = self._run(run)
        result = self._http(
            value,
            value.unmodulated_endpoints["latestEventSeq"],
        )
        if result.status != 200:
            raise AssertionError(
                "Flask latest-event read failed: "
                f"{result.status} {result.packet!r}"
            )
        return int(result.packet["event_seq"])

    @staticmethod
    def _merge_ranges(
        rows: list[Mapping[str, Any]],
    ) -> list[Dict[str, int]]:
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
            {
                "from_event_seq": start,
                "to_event_seq": end,
            }
            for start, end in merged
        ]

    def _poll(
        self,
        run: FlaskFacadeBackendOnlyRunV1,
        *,
        role: Optional[str],
        after_event_seq: int,
        identity_id: str,
        limit: Optional[int],
    ) -> Dict[str, Any]:
        endpoints = self._endpoints(run, role)
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
                else min(500, remaining or 500)
            )
            result = self._http(
                run,
                endpoints["events"],
                query={
                    "identity_id": identity_id,
                    "after_event_seq": cursor,
                    "limit": request_limit,
                },
            )
            if result.status != 200:
                raise AssertionError(
                    "Flask events read failed: "
                    f"{result.status} {result.packet!r}"
                )

            page = result.packet
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

        out = deepcopy(pages[0])
        out["events"] = visible
        out["after_event_seq"] = start
        out["scanned_through_event_seq"] = cursor
        out["next_after_event_seq"] = cursor
        out["session_latest_event_seq"] = int(
            pages[-1].get("session_latest_event_seq") or cursor
        )

        ranges = self._merge_ranges(hidden)
        hidden_count = sum(
            row["to_event_seq"] - row["from_event_seq"] + 1
            for row in ranges
        )
        out["visibility_receipt"] = {
            "kind": "live_session_event_visibility_receipt_v1",
            "role": (
                None
                if role in (None, "")
                else str(role).strip() or None
            ),
            "scanned_from_event_seq_exclusive": start,
            "scanned_through_event_seq": cursor,
            "hidden_event_count": hidden_count,
            "hidden_event_seq_ranges": ranges,
            "reason": "role_projection" if hidden_count else "none",
        }
        return out

    def committed_events_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> list[Mapping[str, Any]]:
        page = self._poll(
            self._run(run),
            role=role,
            after_event_seq=0,
            identity_id=(
                f"{self.strategy_name}.retained.{uuid4().hex}"
            ),
            limit=None,
        )
        return [
            dict(event)
            for event in list(page.get("events") or [])
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
        return self._poll(
            self._run(run),
            role=role,
            after_event_seq=after_event_seq,
            identity_id=str(identity_id),
            limit=limit,
        )

    def read_context_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> Mapping[str, Any]:
        value = self._run(run)
        result = self._http(
            value,
            self._endpoints(value, role)["context"],
        )
        if (
            result.status != 200
            or not isinstance(result.packet.get("ctx"), Mapping)
        ):
            raise AssertionError(
                "Flask context read failed: "
                f"{result.status} {result.packet!r}"
            )
        return deepcopy(dict(result.packet["ctx"]))


__all__ = [
    "DEFAULT_PROGRESS_POLL_SECONDS",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "DEFAULT_SERVER_SHUTDOWN_POLL_SECONDS",
    "FlaskFacadeBackendOnlyDryRunStrategy",
    "FlaskFacadeBackendOnlyRunV1",
]
