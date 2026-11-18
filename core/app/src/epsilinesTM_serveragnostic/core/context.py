from __future__ import annotations

"""Ambient economics provider and epsilon (eps) sink/reader binding and resolution."""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Callable, Mapping
import uuid

if TYPE_CHECKING:
    from .contracts import EconomicsProvider

from .contracts import (
    CannotReadTransientEpsChannelError,
    EconomicsNotConfigured,
    EpsReaderNotConfigured,
    EpsReadPermissionDeniedError,
)
from .registry import MODE_PERSISTENCE, require_registered_eps_channel_v1

_provider: ContextVar[Any] = ContextVar("economics_provider", default=None)
_eps_sink: ContextVar[Callable[..., Any] | None] = ContextVar("eps_sink", default=None)
_eps_reader: ContextVar[Callable[..., Any] | None] = ContextVar("eps_reader", default=None)


class EpsSinkNotConfigured(RuntimeError):
    """Raised when `emit_eps_v1` or `get_eps_sink_v1` is called without an active eps sink."""


@contextmanager
def bind_provider_v1(provider: Any):
    """Context manager binding an ambient EconomicsProvider to the active execution context."""
    token = _provider.set(provider)
    try:
        yield provider
    finally:
        _provider.reset(token)


def get_provider_v1():
    """Retrieve the currently bound EconomicsProvider or raise EconomicsNotConfigured."""
    provider = _provider.get()
    if provider is None:
        raise EconomicsNotConfigured("Economics provider is not bound in active context.")
    return provider


def has_provider_v1() -> bool:
    """Return True if an ambient EconomicsProvider is bound in the active context."""
    return _provider.get() is not None


@contextmanager
def bind_eps_sink_v1(sink: Callable[..., Any]):
    """Context manager binding an ambient epsilon (`eps`) sink to the active execution context."""
    if not callable(sink):
        raise TypeError("eps sink must be callable")
    token = _eps_sink.set(sink)
    try:
        yield sink
    finally:
        _eps_sink.reset(token)


def get_eps_sink_v1() -> Callable[..., Any]:
    """Retrieve the currently bound epsilon (`eps`) sink or raise `EpsSinkNotConfigured`."""
    sink = _eps_sink.get()
    if sink is None:
        raise EpsSinkNotConfigured("Epsilon (eps) sink is not bound in active context.")
    return sink


def has_eps_sink_v1() -> bool:
    """Return True if an ambient epsilon (`eps`) sink is bound in the active context."""
    return _eps_sink.get() is not None


@contextmanager
def bind_eps_reader_v1(reader: Callable[..., Any]):
    """Context manager binding an ambient epsilon (`eps`) reader to the active execution context."""
    if not callable(reader):
        raise TypeError("eps reader must be callable")
    token = _eps_reader.set(reader)
    try:
        yield reader
    finally:
        _eps_reader.reset(token)


def get_eps_reader_v1() -> Callable[..., Any]:
    """Retrieve the currently bound epsilon (`eps`) reader or raise `EpsReaderNotConfigured`."""
    reader = _eps_reader.get()
    if reader is None:
        raise EpsReaderNotConfigured("Epsilon (eps) reader is not bound in active context.")
    return reader


def has_eps_reader_v1() -> bool:
    """Return True if an ambient epsilon (`eps`) reader is bound in the active context."""
    return _eps_reader.get() is not None


def emit_eps_v1(
    channel: str,
    payload: Mapping[str, Any],
    *,
    ref: str | None = None,
    parent_ref: str | None = None,
    meta: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> str:
    """Validate (channel, payload) against central registry and deliver to bound sink.

    Returns the confirmed unique reference ID (ref). If ref is omitted and channel
    has mode=MODE_PERSISTENCE, a compact reference is allocated automatically.
    """
    spec = require_registered_eps_channel_v1(channel)
    validated = spec.validate(payload)
    sink = get_eps_sink_v1()

    assigned_ref = ref
    if assigned_ref is None and spec.mode == MODE_PERSISTENCE:
        assigned_ref = str(uuid.uuid4())

    call_kwargs = dict(kwargs)
    call_kwargs.setdefault("visibility", spec.visibility)
    if assigned_ref is not None:
        call_kwargs["ref"] = assigned_ref
    if parent_ref is not None:
        call_kwargs["parent_ref"] = parent_ref
    if meta is not None:
        call_kwargs["meta"] = dict(meta)

    sink_result = sink(spec.channel, validated, **call_kwargs)
    if isinstance(sink_result, str) and sink_result:
        return sink_result
    return assigned_ref or ""


def read_eps_v1(
    channel: str | None = None,
    *,
    ref: str | None = None,
    parent_ref: str | None = None,
    ref_prefix: str | None = None,
    ref_regex: str | None = None,
    meta: Mapping[str, Any] | None = None,
    all_in_run: bool = False,
    all_for_owner: bool = False,
    run_id: str | None = None,
    owner_id: str | None = None,
    app: str | None = None,
    after_seq: int = 0,
    limit: int = 100,
    caller_role: str | None = None,
    for_owner: bool = False,
    allow_all: bool = False,
    emitted_from: Any = None,
    emitted_to: Any = None,
    **kwargs: Any,
) -> list[dict[str, Any]] | dict[str, Any] | None:
    """Targeted or batch retrieval of persisted epsilon records.

    Invariants:
    - Fails fast with CannotReadTransientEpsChannelError if spec.mode != MODE_PERSISTENCE.
    - Point seek (ref=...) returns a single dict envelope (or None if not found).
    - All batch queries (parent_ref, ref_prefix, all_in_run, all_for_owner, cursor) return list[dict].
    """
    spec = None
    if channel is not None:
        spec = require_registered_eps_channel_v1(channel)
        if spec.mode != MODE_PERSISTENCE:
            raise CannotReadTransientEpsChannelError(
                f"Channel {spec.channel!r} has mode={spec.mode!r} and cannot be read from persistence."
            )

    reader = get_eps_reader_v1()
    spec_channel = spec.channel if spec is not None else None

    call_kwargs = dict(kwargs)
    if ref is not None:
        call_kwargs["ref"] = ref
    if parent_ref is not None:
        call_kwargs["parent_ref"] = parent_ref
    if ref_prefix is not None:
        call_kwargs["ref_prefix"] = ref_prefix
    if ref_regex is not None:
        call_kwargs["ref_regex"] = ref_regex
    if meta is not None:
        call_kwargs["meta"] = meta
    if all_in_run:
        call_kwargs["all_in_run"] = True
    if all_for_owner:
        call_kwargs["all_for_owner"] = True
    if run_id is not None:
        call_kwargs["run_id"] = run_id
    if owner_id is not None:
        call_kwargs["owner_id"] = owner_id
    if app is not None:
        call_kwargs["app"] = app
    if after_seq > 0:
        call_kwargs["after_seq"] = after_seq
    if limit != 100:
        call_kwargs["limit"] = limit
    if caller_role is not None:
        call_kwargs["caller_role"] = caller_role
    if for_owner:
        call_kwargs["for_owner"] = True
    if allow_all:
        call_kwargs["allow_all"] = True
    if emitted_from is not None:
        call_kwargs["emitted_from"] = emitted_from
    if emitted_to is not None:
        call_kwargs["emitted_to"] = emitted_to

    raw_result = reader(spec_channel, **call_kwargs)

    if ref is not None:
        if isinstance(raw_result, dict):
            return raw_result
        if isinstance(raw_result, (list, tuple)):
            return raw_result[0] if raw_result else None
        return None

    if isinstance(raw_result, list):
        return raw_result
    if raw_result is None:
        return []
    return list(raw_result)


__all__ = [
    "CannotReadTransientEpsChannelError",
    "EpsReaderNotConfigured",
    "EpsReadPermissionDeniedError",
    "EpsSinkNotConfigured",
    "bind_eps_reader_v1",
    "bind_eps_sink_v1",
    "bind_provider_v1",
    "emit_eps_v1",
    "get_eps_reader_v1",
    "get_eps_sink_v1",
    "get_provider_v1",
    "has_eps_reader_v1",
    "has_eps_sink_v1",
    "has_provider_v1",
    "read_eps_v1",
]
