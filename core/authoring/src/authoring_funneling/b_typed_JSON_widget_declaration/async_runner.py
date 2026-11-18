"""Celery-backed target execution for asynchronous JSON function chain flows on QUEUE_ASYNCWORK."""
from __future__ import annotations
from threading import get_ident
from typing import Any, Callable, Dict, Optional

from authoring_w_persistence_async.registry import async_work_target
from JSONfnchainTM import FlowPlan, execute_flow
from .interceptor import AsyncWorkFlowInterceptor
from .vocab_hub import THINKUMENT_GLOBAL_VOCAB


@async_work_target("jsonfnchain.execute_transition")
def execute_json_flow_target(
    recipe_json: str,
    root_scope: Dict[str, Any],
    operation_id: str = "",
    widget_id: str = "",
    transition_name: str = "",
    vendor_bindings: Optional[Dict[str, Any]] = None,
    progress: Optional[Callable[..., Any]] = None,
    announcement_ref: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute a compiled JSON flow within an asynchronous Celery worker process.
    
    Adheres strictly to Platform Philosophy 2:
    - Runs on QUEUE_ASYNCWORK, completely decoupled from the dispatch worker pool.
    - Emits live asyncwork.progress events via progress helper or direct epsiline emission.
    - Resolves vendor operations and database connections cleanly.
    """
    plan = FlowPlan.from_json(recipe_json, vocab=THINKUMENT_GLOBAL_VOCAB)
    total_steps = len(getattr(plan, "_contracts", {}))
    interceptor = AsyncWorkFlowInterceptor(
        widget=None,
        progress_callback=progress,
        announcement_ref=announcement_ref,
        total_steps=total_steps if total_steps > 0 else None,
    )
    context = {
        "owner_thread": get_ident(),
        "operation_id": operation_id,
        "widget_id": widget_id,
        "parent_ref": announcement_ref,
        "vendor_bindings": vendor_bindings or {},
    }
    result = execute_flow(
        plan,
        root_scope,
        vocab=THINKUMENT_GLOBAL_VOCAB,
        interceptor=interceptor,
        host_context=context,
        max_concurrency=8,
    )
    return result
