from __future__ import annotations

"""Expectation constructors for complete highest-facade data blankets.

A data blanket is the downstream-visible collection surrounding one admitted
live-session action:

* the direct dispatch receipt;
* controller and datum packets delivered live through threaded callbacks;
* the canonical events-since page produced after dispatch;
* optional post-dispatch U reads for roleless or named-role viewers; and
* the exact live-to-canonical packet bridge.

The helpers return inert expectation mappings only. They do not create a
session, dispatch, read state, or know an application widget.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping, Optional, Sequence


DATA_BLANKET_EXPECTATION_KIND_V1 = "live_session_data_blanket_expectation_v1"
DATA_BLANKET_CONTEXT_VIEW_KIND_V1 = (
    "live_session_data_blanket_context_view_expectation_v1"
)


def CONTEXT_VIEW(
    *,
    expect: Mapping[str, Any],
    role: Optional[str] = None,
) -> Dict[str, Any]:
    """Describe one post-dispatch highest-facade context read."""
    return {
        "kind": DATA_BLANKET_CONTEXT_VIEW_KIND_V1,
        "role": None if role is None else str(role),
        "U": deepcopy(dict(expect)),
    }


def DATA_BLANKET(
    *,
    live: Optional[Mapping[str, Any]] = None,
    eps: Optional[Sequence[Mapping[str, Any]]] = None,
    eps_views: Optional[Sequence[Mapping[str, Any]]] = None,
    dispatch: Optional[Mapping[str, Any]] = None,
    canonical_page: Optional[Mapping[str, Any]] = None,
    contexts: Optional[Sequence[Mapping[str, Any]]] = None,
    exact_live_canonical_wire: bool = False,
) -> Dict[str, Any]:
    """Build one complete data-blanket expectation pocket.

    ``eps`` contains expected `EpsRow` needles emitted on the run-level epsilon channel.

    ``live`` remains supported for backward compatibility with legacy trident expectations.

    ``dispatch`` and ``canonical_page`` are ordinary dotted-path needles.

    ``contexts`` contains ``CONTEXT_VIEW`` rows.
    """
    return {
        "kind": DATA_BLANKET_EXPECTATION_KIND_V1,
        "live": None if live is None else deepcopy(dict(live)),
        "eps": None if eps is None else [deepcopy(dict(row)) for row in list(eps)],
        "eps_views": None if eps_views is None else [deepcopy(dict(row)) for row in list(eps_views)],
        "dispatch": deepcopy(dict(dispatch or {})),
        "canonical_page": deepcopy(dict(canonical_page or {})),
        "contexts": [
            deepcopy(dict(row))
            for row in list(contexts or [])
        ],
        "exact_live_canonical_wire": bool(exact_live_canonical_wire),
    }


# Guide-facing compact aliases.
data_blanket = DATA_BLANKET
context_view = CONTEXT_VIEW


__all__ = [
    "CONTEXT_VIEW",
    "DATA_BLANKET",
    "DATA_BLANKET_CONTEXT_VIEW_KIND_V1",
    "DATA_BLANKET_EXPECTATION_KIND_V1",
    "context_view",
    "data_blanket",
]