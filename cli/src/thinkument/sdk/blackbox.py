"""Black-box autonomous execution namespace for ThinkClient."""
from __future__ import annotations

import concurrent.futures
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional


@dataclass(frozen=True)
class RunResult:
    ok: bool
    status: str
    outputs: Dict[str, Any]
    canonical_context: Dict[str, Any]
    receipt: Dict[str, Any]


class BlackBoxJob:
    """Handle to an in-flight or synchronous black-box execution."""

    def __init__(self, execute_fn: Any) -> None:
        self._fn = execute_fn
        self._result: Optional[RunResult] = None

    def wait(self) -> RunResult:
        if self._result is None:
            raw = self._fn()
            self._result = RunResult(
                ok=bool(raw.get("ok", True)),
                status="COMPLETED" if raw.get("ok", True) else "FAILED",
                outputs=raw.get("outputs") or {},
                canonical_context=raw.get("canonical_context") or raw.get("ctx") or {},
                receipt=raw.get("receipt") or raw,
            )
        return self._result


class BatchJob:
    """Handle to a batch of black-box runs across a C-matrix parameter sweep."""

    def __init__(self, jobs: List[BlackBoxJob]) -> None:
        self.jobs = jobs

    def await_all(self) -> List[RunResult]:
        return [job.wait() for job in self.jobs]


class BlackBoxNamespace:
    """Executes autonomous headless runs and scaled C-matrix batch sweeps."""

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
            with urllib.request.urlopen(req, timeout=120) as resp:
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

    def run(
        self,
        P: Mapping[str, Any],
        C: Optional[Mapping[str, Any]] = None,
        SM: Optional[Mapping[str, Any]] = None,
        *,
        timeout_seconds: int = 60,
    ) -> BlackBoxJob:
        """Run an authored P x SM x C flow autonomously to ATCOMPLETION."""
        payload = {
            "P": dict(P),
            "C": dict(C or {}),
            "SM": dict(SM or {}),
            "timeout_seconds": timeout_seconds,
        }

        def execute():
            return self._request("POST", "/api/v1/blackbox/run/", payload)

        return BlackBoxJob(execute)

    def batch(
        self,
        P: Mapping[str, Any],
        C_matrix: List[Mapping[str, Any]],
        SM: Optional[Mapping[str, Any]] = None,
        *,
        concurrency: int = 10,
    ) -> BatchJob:
        """Execute a parallel parameter sweep over the C-matrix."""
        jobs: List[BlackBoxJob] = []

        def execute_one(c_item: Mapping[str, Any]):
            payload = {
                "P": dict(P),
                "C": dict(c_item),
                "SM": dict(SM or {}),
            }
            return self._request("POST", "/api/v1/blackbox/run/", payload)

        # ThreadPoolExecutor runs sweeps locally or across cloud endpoints
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(concurrency, len(C_matrix) or 1))
        futures = [executor.submit(execute_one, c) for c in C_matrix]

        for fut in futures:
            jobs.append(BlackBoxJob(fut.result))

        return BatchJob(jobs)
