from __future__ import annotations

"""Target registration and decorator for asynchronous functions in authoring."""

from typing import Any, Callable, Dict, Optional

_AUTHORING_TARGETS: Dict[str, Callable[..., Any]] = {}


def async_work_target(name: Optional[str] = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator declaring a function as a sanctioned asyncwork target.
    
    Can be used with or without arguments:
        @async_work_target
        def my_task(x: int): ...
        
        @async_work_target("custom_task_name")
        def my_task(x: int): ...
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        target_name = (name or getattr(fn, "__name__", "")).strip()
        if not target_name:
            raise ValueError("Target function must have a non-empty name")
        
        _AUTHORING_TARGETS[target_name] = fn

        # Also register with service Celery task registry if available
        try:
            from celery_jobs.asyncwork_tasks import register_async_work_target
            register_async_work_target(target_name, fn)
        except ImportError:
            pass

        return fn

    if callable(name):
        actual_fn = name
        name = None
        return decorator(actual_fn)

    return decorator


def register_authoring_target(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
    """Programmatically register an asyncwork target function."""
    norm = str(name).strip()
    _AUTHORING_TARGETS[norm] = fn
    try:
        from celery_jobs.asyncwork_tasks import register_async_work_target
        register_async_work_target(norm, fn)
    except ImportError:
        pass
    return fn


def get_authoring_target(name: str) -> Optional[Callable[..., Any]]:
    """Retrieve a registered asyncwork target by name."""
    norm = str(name).strip()
    if norm in _AUTHORING_TARGETS:
        return _AUTHORING_TARGETS[norm]
    try:
        from celery_jobs.asyncwork_tasks import get_async_work_target
        return get_async_work_target(norm)
    except ImportError:
        return None
