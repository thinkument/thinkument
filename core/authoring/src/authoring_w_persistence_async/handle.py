from __future__ import annotations

"""Jobsian minimalist handle for asynchronous task inspection and progress following."""

import time
from typing import Any, Dict, List, Optional

from epsilinesTM_serveragnostic import (
    ASYNCWORK_ANNOUNCE_CHANNEL,
    ASYNCWORK_DONE_CHANNEL,
    ASYNCWORK_PROGRESS_CHANNEL,
    read_eps_v1,
)


class AsyncWorkHandle:
    """Represents an ongoing or completed asynchronous background job.
    
    Provides fast, BTree-indexed `<1ms` point-seek checks for doneness,
    clean progress stream retrieval, and bounded waiting.
    """

    def __init__(
        self,
        announcement_ref: str,
        *,
        run_id: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> None:
        norm = str(announcement_ref or "").strip()
        if not norm:
            raise ValueError("announcement_ref must be a non-empty string")
        self._ref = norm
        self._run_id = run_id
        self._owner_id = owner_id
        self._cached_done: Optional[Dict[str, Any]] = None

    @property
    def ref(self) -> str:
        """The root announcement reference of the job."""
        return self._ref

    @property
    def done_ref(self) -> str:
        """The predictable point-seek reference of the terminal done sandwich."""
        return f"{self._ref}/done"

    def get_announcement(self, for_owner: bool = True) -> Optional[Dict[str, Any]]:
        """Retrieve the initial announcement envelope for this job."""
        query_kwargs: Dict[str, Any] = {"ref": self._ref, "for_owner": for_owner}
        if self._run_id:
            query_kwargs["run_id"] = self._run_id
        if self._owner_id:
            query_kwargs["owner_id"] = self._owner_id

        res = read_eps_v1(ASYNCWORK_ANNOUNCE_CHANNEL, **query_kwargs)
        if isinstance(res, dict):
            return res
        return None

    def is_done(self, for_owner: bool = True) -> bool:
        """Perform a fast `<1ms` BTree point seek to check if the job is finished.
        
        Caches the done envelope upon first positive result.
        """
        if self._cached_done is not None:
            return True

        query_kwargs: Dict[str, Any] = {"ref": self.done_ref, "for_owner": for_owner}
        if self._run_id:
            query_kwargs["run_id"] = self._run_id
        if self._owner_id:
            query_kwargs["owner_id"] = self._owner_id

        res = read_eps_v1(ASYNCWORK_DONE_CHANNEL, **query_kwargs)
        if isinstance(res, dict):
            self._cached_done = res
            return True
        return False

    def get_done(self, for_owner: bool = True) -> Optional[Dict[str, Any]]:
        """Retrieve the terminal done sandwich envelope, or None if still running."""
        if self._cached_done is not None:
            return self._cached_done

        self.is_done(for_owner=for_owner)
        return self._cached_done

    def get_outcome(self, for_owner: bool = True) -> Optional[str]:
        """Return terminal outcome ('success', 'error', 'timeout') or None if ongoing."""
        done_env = self.get_done(for_owner=for_owner)
        if done_env:
            payload = done_env.get("payload") or done_env.get("content") or {}
            return payload.get("outcome")
        return None

    def get_result(self, for_owner: bool = True) -> Any:
        """Return task return value, or None if ongoing or failed."""
        done_env = self.get_done(for_owner=for_owner)
        if done_env:
            payload = done_env.get("payload") or done_env.get("content") or {}
            return payload.get("result")
        return None

    def get_error(self, for_owner: bool = True) -> Optional[str]:
        """Return error message if job failed or timed out, else None."""
        done_env = self.get_done(for_owner=for_owner)
        if done_env:
            payload = done_env.get("payload") or done_env.get("content") or {}
            return payload.get("error_message") or payload.get("error")
        return None

    def get_duration_ms(self, for_owner: bool = True) -> Optional[float]:
        """Return total elapsed execution duration in milliseconds, if done."""
        done_env = self.get_done(for_owner=for_owner)
        if done_env:
            payload = done_env.get("payload") or done_env.get("content") or {}
            return payload.get("duration_ms")
        return None

    def get_all_progress(self, for_owner: bool = True) -> List[Dict[str, Any]]:
        """Retrieve all intermediate progress events emitted for this job in order."""
        query_kwargs: Dict[str, Any] = {"parent_ref": self._ref, "for_owner": for_owner}
        if self._run_id:
            query_kwargs["run_id"] = self._run_id
        if self._owner_id:
            query_kwargs["owner_id"] = self._owner_id

        res = read_eps_v1(ASYNCWORK_PROGRESS_CHANNEL, **query_kwargs)
        if isinstance(res, list):
            return res
        return []

    def get_latest_progress(self, for_owner: bool = True) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent intermediate progress update, or None if no ticks yet."""
        all_p = self.get_all_progress(for_owner=for_owner)
        if all_p:
            return all_p[-1]
        return None

    def wait_until_done(
        self,
        *,
        timeout_seconds: float = 60.0,
        poll_interval: float = 0.25,
        for_owner: bool = True,
    ) -> Dict[str, Any]:
        """Synchronously poll until the job completes or deadline expires (Mode 2: Bounded Wait).
        
        Useful for blackbox or automated runs. Interactive runs should use Mode 1 (non-blocking wire polling).
        """
        deadline = time.monotonic() + max(0.1, float(timeout_seconds))
        interval = max(0.01, float(poll_interval))

        while time.monotonic() < deadline:
            if self.is_done(for_owner=for_owner):
                return self._cached_done or {}
            time.sleep(interval)

        if self.is_done(for_owner=for_owner):
            return self._cached_done or {}

        raise TimeoutError(
            f"Async work {self._ref!r} did not complete within {timeout_seconds}s deadline."
        )

    def __repr__(self) -> str:
        status = "DONE" if self._cached_done is not None else "RUNNING/PENDING"
        return f"<AsyncWorkHandle ref={self._ref!r} status={status}>"
