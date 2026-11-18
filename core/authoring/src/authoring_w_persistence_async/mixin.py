from __future__ import annotations

"""Jobsian widget mixin providing native asyncwork delegation and wire inspection."""

from typing import Any, Callable, Dict, Mapping, Optional, Union

from .handle import AsyncWorkHandle
from .submit import get_async_work_handle_v1, submit_async_work_v1


class AsyncWorkWidgetMixin:
    """Provides high-level async work methods directly on widget classes.
    
    Adheres strictly to Philosophy 2:
    - Step 1 Submitter widget calls `self.submit_async_work_v1(...)` and writes `handle.ref` to state.
    - Step 2 Consumer widget connected via static wire reads `wire["task_ref"]`, checks
      `self.is_async_work_done_v1(wire["task_ref"])`, and marks `self.is_done = True` when ready.
    """

    def submit_async_work_v1(
        self,
        target: Union[str, Callable[..., Any]],
        kwargs: Optional[Mapping[str, Any]] = None,
        *,
        timeout_seconds: Optional[float] = None,
        ref: Optional[str] = None,
        max_retries: Optional[int] = None,
        priority: Optional[int] = None,
        meta: Optional[Mapping[str, Any]] = None,
        deduplication_key: Optional[str] = None,
    ) -> AsyncWorkHandle:
        """Submit async work from the current widget explosion context."""
        initiator_name = self.__class__.__name__

        return submit_async_work_v1(
            target=target,
            kwargs=kwargs,
            timeout_seconds=timeout_seconds,
            ref=ref,
            max_retries=max_retries,
            priority=priority,
            meta=meta,
            deduplication_key=deduplication_key,
            initiator_widget=initiator_name,
        )

    def get_async_work_handle_v1(self, ref: str) -> AsyncWorkHandle:
        """Obtain an AsyncWorkHandle for a task ref passed via static wire or state."""
        return get_async_work_handle_v1(ref=ref)

    def is_async_work_done_v1(self, ref: str, for_owner: bool = True) -> bool:
        """Check whether an async work task is finished using `<1ms` point seek."""
        handle = self.get_async_work_handle_v1(ref)
        return handle.is_done(for_owner=for_owner)

    def get_async_work_result_v1(self, ref: str, for_owner: bool = True) -> Any:
        """Retrieve return value of completed async task, or None if still running."""
        handle = self.get_async_work_handle_v1(ref)
        return handle.get_result(for_owner=for_owner)

    def get_async_work_outcome_v1(self, ref: str, for_owner: bool = True) -> Optional[str]:
        """Retrieve outcome ('success', 'error', 'timeout') of task, or None if running."""
        handle = self.get_async_work_handle_v1(ref)
        return handle.get_outcome(for_owner=for_owner)

    def get_async_work_progress_v1(self, ref: str, for_owner: bool = True) -> Optional[Dict[str, Any]]:
        """Retrieve latest progress update for an ongoing async task."""
        handle = self.get_async_work_handle_v1(ref)
        return handle.get_latest_progress(for_owner=for_owner)
