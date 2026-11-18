from __future__ import annotations

"""The `authoring_w_persistence_async` package.

Exposes high-level Jobsian minimalist primitives for submitting, tracking,
and consuming asynchronous work backed by dedicated Celery worker pools.
"""

from .handle import AsyncWorkHandle
from .mixin import AsyncWorkWidgetMixin
from .registry import (
    async_work_target,
    get_authoring_target,
    register_authoring_target,
)
from .submit import (
    get_async_work_handle_v1,
    submit_async_work_v1,
)

__all__ = [
    "AsyncWorkHandle",
    "AsyncWorkWidgetMixin",
    "async_work_target",
    "get_async_work_handle_v1",
    "get_authoring_target",
    "register_authoring_target",
    "submit_async_work_v1",
]
