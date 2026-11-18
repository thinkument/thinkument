from __future__ import annotations

"""
thinksession.__persistence.config
===============================

Single injection point for session persistence.

Required adapter surface:
  create, get, get_stepper, save_stepper, save_state, delete

Optional feature surface:
  save_aux_json(session_id, namespace=..., value=...)
  get_aux_json(session_id, namespace=...)

The optional methods support compact hosting-owned JSON without coupling the
engine to a particular feature or database.

The highest ``_thinksessions.run.run_from_here`` façade does not call these
methods implicitly. A hosting transaction coordinator may use them while
holding its own cross-process session boundary.

A coordinator that commits mutations must also force the concrete session API
to checkpoint the complete opaque runtime before committing the surrounding
transaction. Persisting only ``latest_event_seq`` or auxiliary JSON is not a
complete session commit.

The repository operations have two distinct meanings:

``save_latest_event_seq``
    Optional incremental high-water persistence while canonical events are
    appended.

``save_state`` plus the current opaque stepper/blob
    One complete coherent runtime checkpoint. At this boundary the high-water
    encoded by the blob must equal ``SessionState.latest_event_seq``.
"""

from typing import Any, Type

from _thinkengine.__persistence import repo as _repo_mod

_SESSION_REPO_CLS: Type[Any] = _repo_mod.SessionRepo


def set_session_repo(repo_cls: Type[Any]) -> None:
    if repo_cls is None:
        raise TypeError("repo_cls must be a class, not None")
    if not isinstance(repo_cls, type):
        raise TypeError(f"repo_cls must be a class; got {type(repo_cls)!r}")

    required = (
        "create",
        "get",
        "get_stepper",
        "save_stepper",
        "save_state",
        "delete",
    )
    missing = [
        method
        for method in required
        if not hasattr(repo_cls, method)
    ]
    if missing:
        raise TypeError(
            f"repo_cls missing required methods: {missing}"
        )

    global _SESSION_REPO_CLS
    _SESSION_REPO_CLS = repo_cls


def get_session_repo() -> Type[Any]:
    return _SESSION_REPO_CLS


__all__ = ["set_session_repo", "get_session_repo"]