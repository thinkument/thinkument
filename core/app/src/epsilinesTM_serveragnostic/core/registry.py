from __future__ import annotations

"""Generic, domain-aware epsilon (eps) channel and app registry (Hub 2).

Defines the Tier-1 channel specification (`EpsChannelSpecV1`) and app specification
(`EpsAppSpecV1`) without any dependency on Django or Celery.
"""

from copy import deepcopy
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Literal, Mapping

from _thinkprogram._iomicrosTM.tiny_helpers import assert_dead_json

VISIBILITY_OWNER_ONLY: Literal["owner-only"] = "owner-only"
VISIBILITY_ALL_WITH_MODULATION: Literal["all-with-modulation"] = "all-with-modulation"
VISIBILITY_ALL_NO_MODULATION: Literal["all-no-modulation"] = "all-no-modulation"

EpsVisibilityLiteral = Literal[
    "owner-only",
    "all-with-modulation",
    "all-no-modulation",
]

ALLOWED_EPS_VISIBILITIES = frozenset(
    {
        VISIBILITY_OWNER_ONLY,
        VISIBILITY_ALL_WITH_MODULATION,
        VISIBILITY_ALL_NO_MODULATION,
    }
)

MODE_PERSISTENCE: Literal["persistence"] = "persistence"
MODE_NONE: Literal["none"] = "none"
ALLOWED_EPS_MODES = frozenset({MODE_PERSISTENCE, MODE_NONE})

RETENTION_DURABLE: Literal["durable"] = "durable"
RETENTION_TTL: Literal["ttl"] = "ttl"
RETENTION_NONE: Literal["none"] = "none"
ALLOWED_EPS_RETENTIONS = frozenset({RETENTION_DURABLE, RETENTION_TTL, RETENTION_NONE})


class EpsRegistryError(ValueError):
    """Raised when an eps channel or app registration or lookup fails."""

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(str(message))
        self.details = deepcopy(dict(details or {}))


class AnalyticaProtocolError(EpsRegistryError):
    """Malformed Analytica event, unregistered channel, or impossible operation event sequence."""


class UnregisteredEpsChannelError(AnalyticaProtocolError):
    """Raised when emitting or looking up an unregistered eps channel (D12)."""


class InvalidEpsChannelSpecificationError(EpsRegistryError):
    """Raised when an eps channel specification fails invariant validation."""


EpsChannelValidationError = InvalidEpsChannelSpecificationError


def _default_channel_validator(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return dict(payload) if isinstance(payload, Mapping) else {"payload": payload}


def _invoke_channel_validator_v1(
    validator: Callable[..., Mapping[str, Any]],
    channel: str,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise EpsRegistryError(
            f"eps payload for channel {channel!r} must be a mapping"
        )
    raw = deepcopy(dict(payload))
    assert_dead_json(raw, path=f"eps[{channel}]")
    try:
        sig = inspect.signature(validator)
        positional = [
            p
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        has_varargs = any(
            p.kind == inspect.Parameter.VAR_POSITIONAL
            for p in sig.parameters.values()
        )
        if len(positional) >= 2 and not has_varargs:
            validated = validator(channel, raw)
        else:
            validated = validator(raw)
    except TypeError:
        validated = validator(channel, raw)

    if not isinstance(validated, Mapping):
        raise EpsRegistryError(
            f"validator for eps channel {channel!r} must return a mapping"
        )
    out = deepcopy(dict(validated))
    assert_dead_json(out, path=f"eps[{channel}]")
    return out


@dataclass(frozen=True)
class EpsChannelSpecV1:
    """Declarative specification for one registered epsilon channel (D27, D35)."""

    channel: str
    app: str
    schema: str = "thinkument.eps.generic.v1"
    event: str = "event"
    validator: Callable[..., Dict[str, Any]] = _default_channel_validator
    visibility: EpsVisibilityLiteral = "owner-only"
    mode: Literal["persistence", "none"] = "persistence"
    retention: Literal["durable", "ttl", "none"] = "durable"
    ttl_seconds: int | None = None
    terminal: bool = False

    def __post_init__(self) -> None:
        ch = str(self.channel or "").strip()
        app_name = str(self.app or "").strip()
        schema_name = str(self.schema or "").strip()
        event_name = str(self.event or "").strip()
        vis = str(self.visibility or "").strip()
        m = str(self.mode or "persistence").strip()
        ret = str(self.retention or "durable").strip()
        term = bool(self.terminal)

        if not ch or len(ch) > 200:
            raise InvalidEpsChannelSpecificationError("EpsChannelSpecV1.channel must be 1..200 chars")
        if not app_name or len(app_name) > 120:
            raise InvalidEpsChannelSpecificationError("EpsChannelSpecV1.app must be 1..120 chars")
        if not schema_name:
            raise InvalidEpsChannelSpecificationError("EpsChannelSpecV1.schema must be non-empty")
        if not event_name:
            raise InvalidEpsChannelSpecificationError("EpsChannelSpecV1.event must be non-empty")
        if not callable(self.validator):
            raise InvalidEpsChannelSpecificationError("EpsChannelSpecV1.validator must be callable")
        if vis not in ALLOWED_EPS_VISIBILITIES:
            raise InvalidEpsChannelSpecificationError(
                f"EpsChannelSpecV1.visibility {vis!r} must be one of {sorted(ALLOWED_EPS_VISIBILITIES)}"
            )
        if m not in ALLOWED_EPS_MODES:
            raise InvalidEpsChannelSpecificationError(
                f"EpsChannelSpecV1.mode {m!r} must be one of {sorted(ALLOWED_EPS_MODES)}"
            )
        if ret not in ALLOWED_EPS_RETENTIONS:
            raise InvalidEpsChannelSpecificationError(
                f"EpsChannelSpecV1.retention {ret!r} must be one of {sorted(ALLOWED_EPS_RETENTIONS)}"
            )
        if m == MODE_NONE and ret != RETENTION_NONE:
            raise InvalidEpsChannelSpecificationError(
                f"mode='none' requires retention='none' on channel {ch!r}, got {ret!r}"
            )
        if m == MODE_PERSISTENCE and ret == RETENTION_NONE:
            raise InvalidEpsChannelSpecificationError(
                f"mode='persistence' cannot have retention='none' on channel {ch!r}"
            )
        if ret == RETENTION_TTL and (self.ttl_seconds is None or self.ttl_seconds <= 0):
            raise InvalidEpsChannelSpecificationError(
                f"retention='ttl' requires positive ttl_seconds on channel {ch!r}"
            )

        object.__setattr__(self, "channel", ch)
        object.__setattr__(self, "app", app_name)
        object.__setattr__(self, "schema", schema_name)
        object.__setattr__(self, "event", event_name)
        object.__setattr__(self, "visibility", vis)
        object.__setattr__(self, "mode", m)
        object.__setattr__(self, "retention", ret)
        object.__setattr__(self, "terminal", term)

    def validate(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate and normalize `payload` for this channel."""
        return _invoke_channel_validator_v1(self.validator, self.channel, payload)


@dataclass(frozen=True, init=False)
class EpsAppSpecV1:
    """Declarative specification for an application family of eps channels."""

    name: str
    channels: tuple[EpsChannelSpecV1, ...]
    stream_validator_factory: Callable[[], Any] | None
    anomaly_aggregator: Callable[[list[Mapping[str, Any]], Mapping[str, Any]], Mapping[str, Any]] | None

    def __init__(
        self,
        name: str = "",
        channels: Sequence[EpsChannelSpecV1] = (),
        stream_validator_factory: Callable[[], Any] | None = None,
        anomaly_aggregator: Callable[[list[Mapping[str, Any]], Mapping[str, Any]], Mapping[str, Any]] | None = None,
        *,
        app: str = "",
    ) -> None:
        resolved_name = str(name or app or "").strip()
        if not resolved_name:
            raise EpsRegistryError("EpsAppSpecV1.name must be non-empty")
        channels_tuple = tuple(channels or ())
        seen: set[str] = set()
        for spec in channels_tuple:
            if not isinstance(spec, EpsChannelSpecV1):
                raise EpsRegistryError(
                    f"EpsAppSpecV1 {resolved_name!r} channels must be EpsChannelSpecV1 instances"
                )
            if spec.app != resolved_name:
                raise EpsRegistryError(
                    f"channel {spec.channel!r} declares app={spec.app!r} inside app {resolved_name!r}"
                )
            if spec.channel in seen:
                raise EpsRegistryError(
                    f"duplicate channel {spec.channel!r} in EpsAppSpecV1 {resolved_name!r}"
                )
            seen.add(spec.channel)
        if (
            stream_validator_factory is not None
            and not callable(stream_validator_factory)
        ):
            raise TypeError(
                "EpsAppSpecV1.stream_validator_factory must be callable or None"
            )
        if (
            anomaly_aggregator is not None
            and not callable(anomaly_aggregator)
        ):
            raise TypeError(
                "EpsAppSpecV1.anomaly_aggregator must be callable or None"
            )
        object.__setattr__(self, "name", resolved_name)
        object.__setattr__(self, "channels", channels_tuple)
        object.__setattr__(self, "stream_validator_factory", stream_validator_factory)
        object.__setattr__(self, "anomaly_aggregator", anomaly_aggregator)

    @property
    def app(self) -> str:
        return self.name


_APPS_BY_NAME: Dict[str, EpsAppSpecV1] = {}
_CHANNELS_BY_NAME: Dict[str, EpsChannelSpecV1] = {}


def register_eps_app_v1(
    app_spec: EpsAppSpecV1,
    *,
    replace: bool = False,
) -> EpsAppSpecV1:
    """Register an `EpsAppSpecV1` and all of its channels."""
    if not isinstance(app_spec, EpsAppSpecV1):
        raise EpsRegistryError("app_spec must be an EpsAppSpecV1 instance")
    if app_spec.name in _APPS_BY_NAME and not replace:
        raise EpsRegistryError(f"eps app {app_spec.name!r} is already registered")
    for spec in app_spec.channels:
        existing = _CHANNELS_BY_NAME.get(spec.channel)
        if existing is not None and not replace and existing.app != app_spec.name:
            raise EpsRegistryError(
                f"eps channel {spec.channel!r} is already registered by app {existing.app!r}"
            )
        if existing is not None and not replace:
            raise EpsRegistryError(
                f"eps channel {spec.channel!r} is already registered"
            )

    if app_spec.name in _APPS_BY_NAME and replace:
        old_app = _APPS_BY_NAME[app_spec.name]
        for old_spec in old_app.channels:
            _CHANNELS_BY_NAME.pop(old_spec.channel, None)

    _APPS_BY_NAME[app_spec.name] = app_spec
    for spec in app_spec.channels:
        _CHANNELS_BY_NAME[spec.channel] = spec
    return app_spec


def register_eps_channel_v1(
    spec: EpsChannelSpecV1,
    *,
    replace: bool = False,
) -> EpsChannelSpecV1:
    """Register a single `EpsChannelSpecV1` into its app family."""
    if not isinstance(spec, EpsChannelSpecV1):
        raise EpsRegistryError("spec must be an EpsChannelSpecV1 instance")
    existing = _CHANNELS_BY_NAME.get(spec.channel)
    if existing is not None and not replace:
        raise EpsRegistryError(
            f"eps channel {spec.channel!r} is already registered"
        )
    _CHANNELS_BY_NAME[spec.channel] = spec
    app_existing = _APPS_BY_NAME.get(spec.app)
    if app_existing is None:
        _APPS_BY_NAME[spec.app] = EpsAppSpecV1(
            name=spec.app,
            channels=(spec,),
            stream_validator_factory=None,
        )
    else:
        kept = tuple(c for c in app_existing.channels if c.channel != spec.channel)
        _APPS_BY_NAME[spec.app] = EpsAppSpecV1(
            name=app_existing.name,
            channels=(*kept, spec),
            stream_validator_factory=app_existing.stream_validator_factory,
        )
    return spec


def unregister_eps_app_v1(app_name: str) -> None:
    """Remove a registered `EpsAppSpecV1` and its channels (used by test fixtures)."""
    name = str(app_name or "").strip()
    old = _APPS_BY_NAME.pop(name, None)
    if old is not None:
        for spec in old.channels:
            _CHANNELS_BY_NAME.pop(spec.channel, None)


def unregister_eps_channel_v1(channel: str) -> None:
    """Remove a single registered `EpsChannelSpecV1` (used by test fixtures)."""
    ch = str(channel or "").strip()
    old = _CHANNELS_BY_NAME.pop(ch, None)
    if old is not None and old.app in _APPS_BY_NAME:
        app_spec = _APPS_BY_NAME[old.app]
        remaining = tuple(c for c in app_spec.channels if c.channel != ch)
        if remaining:
            _APPS_BY_NAME[old.app] = EpsAppSpecV1(
                name=app_spec.name,
                channels=remaining,
                stream_validator_factory=app_spec.stream_validator_factory,
            )
        else:
            _APPS_BY_NAME.pop(old.app, None)


_DYNAMIC_CHANNEL_RESOLVERS: list[Callable[[str], EpsChannelSpecV1 | None]] = []


def register_dynamic_channel_resolver_v1(
    resolver: Callable[[str], EpsChannelSpecV1 | None],
) -> None:
    """Register a dynamic channel resolution fallback (e.g. pattern-based channels)."""
    if not callable(resolver):
        raise EpsRegistryError("resolver must be callable")
    if resolver not in _DYNAMIC_CHANNEL_RESOLVERS:
        _DYNAMIC_CHANNEL_RESOLVERS.append(resolver)


def get_registered_eps_channel_v1(channel: Any) -> EpsChannelSpecV1 | None:
    """Return the `EpsChannelSpecV1` for `channel`, or `None` if not registered."""
    if not isinstance(channel, str):
        return None
    norm = channel.strip()
    spec = _CHANNELS_BY_NAME.get(norm)
    if spec is not None:
        return spec
    for resolver in _DYNAMIC_CHANNEL_RESOLVERS:
        resolved = resolver(norm)
        if resolved is not None:
            return resolved
    return None


def is_registered_eps_channel_v1(channel: Any) -> bool:
    """Return True iff `channel` is registered in the central eps registry."""
    return get_registered_eps_channel_v1(channel) is not None


def require_registered_eps_channel_v1(channel: Any) -> EpsChannelSpecV1:
    """Return the `EpsChannelSpecV1` for `channel` or raise `UnregisteredEpsChannelError` (D12)."""
    if not isinstance(channel, str) or not channel.strip():
        raise UnregisteredEpsChannelError(
            "eps channel must be a non-empty string",
            details={"channel": channel},
        )
    normalized = channel.strip()
    spec = get_registered_eps_channel_v1(normalized)
    if spec is None:
        raise UnregisteredEpsChannelError(
            f"{normalized!r} is not a registered eps channel",
            details={"channel": normalized},
        )
    return spec


def policy_of_v1(channel: str) -> EpsChannelSpecV1:
    """Alias for `require_registered_eps_channel_v1(channel)`."""
    return require_registered_eps_channel_v1(channel)


def visibility_of_v1(channel: str) -> EpsVisibilityLiteral:
    """Return the registered visibility (`owner-only`, `all-with-modulation`, `all-no-modulation`) for `channel`."""
    return require_registered_eps_channel_v1(channel).visibility


def validate_eps_channel_payload_v1(
    channel: str,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate `payload` against the registered validator for `channel`."""
    spec = require_registered_eps_channel_v1(channel)
    return spec.validate(payload)


def registered_eps_channels_v1() -> Dict[str, EpsChannelSpecV1]:
    """Return a shallow copy of all currently registered `channel -> EpsChannelSpecV1`."""
    return dict(_CHANNELS_BY_NAME)


def registered_eps_apps_v1() -> Dict[str, EpsAppSpecV1]:
    """Return a shallow copy of all currently registered `app -> EpsAppSpecV1`."""
    return dict(_APPS_BY_NAME)


def channels_for_eps_app_v1(app_name: str) -> tuple[EpsChannelSpecV1, ...]:
    """Return all registered `EpsChannelSpecV1` entries belonging to `app_name`."""
    name = str(app_name or "").strip()
    app_spec = _APPS_BY_NAME.get(name)
    if app_spec is None:
        return ()
    return app_spec.channels


def stream_validator_factory_for_app_v1(
    app_name: str,
) -> Callable[[], Any] | None:
    """Return the optional per-stream validator factory for `app_name`."""
    name = str(app_name or "").strip()
    app_spec = _APPS_BY_NAME.get(name)
    if app_spec is None:
        return None
    return app_spec.stream_validator_factory


def anomaly_aggregator_for_app_v1(
    app_name: str,
) -> Callable[[list[Mapping[str, Any]], Mapping[str, Any]], Mapping[str, Any]] | None:
    """Return the optional anomaly aggregator for `app_name`."""
    name = str(app_name or "").strip()
    app_spec = _APPS_BY_NAME.get(name)
    if app_spec is None:
        return None
    return app_spec.anomaly_aggregator


def register_anomaly_aggregator_v1(
    app_name: str,
    aggregator: Callable[[list[Mapping[str, Any]], Mapping[str, Any]], Mapping[str, Any]],
) -> None:
    """Register or update an anomaly aggregator for a registered app."""
    name = str(app_name or "").strip()
    app_spec = _APPS_BY_NAME.get(name)
    if app_spec is None:
        raise EpsRegistryError(f"cannot register anomaly aggregator for unknown app {name!r}")
    if not callable(aggregator):
        raise EpsRegistryError("aggregator must be callable")
    new_spec = EpsAppSpecV1(
        name=app_spec.name,
        channels=app_spec.channels,
        stream_validator_factory=app_spec.stream_validator_factory,
        anomaly_aggregator=aggregator,
    )
    register_eps_app_v1(new_spec, replace=True)


__all__ = [
    "ALLOWED_EPS_MODES",
    "ALLOWED_EPS_RETENTIONS",
    "ALLOWED_EPS_VISIBILITIES",
    "EpsAppSpecV1",
    "EpsChannelSpecV1",
    "EpsChannelValidationError",
    "EpsRegistryError",
    "EpsVisibilityLiteral",
    "InvalidEpsChannelSpecificationError",
    "MODE_NONE",
    "MODE_PERSISTENCE",
    "RETENTION_DURABLE",
    "RETENTION_NONE",
    "RETENTION_TTL",
    "UnregisteredEpsChannelError",
    "VISIBILITY_ALL_NO_MODULATION",
    "VISIBILITY_ALL_WITH_MODULATION",
    "VISIBILITY_OWNER_ONLY",
    "anomaly_aggregator_for_app_v1",
    "channels_for_eps_app_v1",
    "get_registered_eps_channel_v1",
    "is_registered_eps_channel_v1",
    "policy_of_v1",
    "register_anomaly_aggregator_v1",
    "register_dynamic_channel_resolver_v1",
    "register_eps_app_v1",
    "register_eps_channel_v1",
    "registered_eps_apps_v1",
    "registered_eps_channels_v1",
    "require_registered_eps_channel_v1",
    "stream_validator_factory_for_app_v1",
    "unregister_eps_app_v1",
    "unregister_eps_channel_v1",
    "validate_eps_channel_payload_v1",
    "visibility_of_v1",
]
