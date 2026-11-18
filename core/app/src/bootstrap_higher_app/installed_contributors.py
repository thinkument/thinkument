from __future__ import annotations

"""Installed runtime-contributor discovery for the Thinkument app composition.

The distribution graph is owned by ``think-app``.  Packages pulled into
that graph may optionally expose one process-startup registration callback via
package metadata instead of requiring a hard-coded import in every higher host.

Static/browser contributions use the independent
``thinkument.static_roots.v1`` entry-point group owned by ``think-frontend``.
This module is only for Python runtime registration that must happen after the
base Thinkument runtime is active.
"""

from dataclasses import dataclass
from importlib import metadata
from threading import RLock
from typing import Any


THINKUMENT_RUNTIME_CONTRIBUTOR_ENTRYPOINT_GROUP = (
    "thinkument.runtime_contributors.v1"
)


class RuntimeContributorError(RuntimeError):
    """An installed runtime contributor violated the bootstrap contract."""


@dataclass(frozen=True, slots=True)
class RuntimeContributorActivationV1:
    """Deterministic receipt for one installed contributor."""

    distribution: str
    name: str
    value: str
    activated_now: bool


_ACTIVATION_LOCK = RLock()
_ACTIVATED: dict[tuple[str, str, str], Any] = {}
_ACTIVATING: set[tuple[str, str, str]] = set()


def _distribution_name(entry_point: Any) -> str:
    dist = getattr(entry_point, "dist", None)
    name = getattr(dist, "name", None)
    return str(name or "<unknown-distribution>")


def _entry_point_identity(entry_point: Any) -> tuple[str, str, str]:
    return (
        _distribution_name(entry_point),
        str(getattr(entry_point, "name", "") or ""),
        str(getattr(entry_point, "value", "") or ""),
    )


def _metadata_entry_points() -> tuple[Any, ...]:
    discovered = metadata.entry_points()

    # Python 3.10+ importlib.metadata exposes ``select``.  Keep the legacy
    # branch so editable/dev environments using older backports remain clean.
    select = getattr(discovered, "select", None)
    if callable(select):
        return tuple(
            select(
                group=(
                    THINKUMENT_RUNTIME_CONTRIBUTOR_ENTRYPOINT_GROUP
                )
            )
        )

    get = getattr(discovered, "get", None)
    if callable(get):
        return tuple(
            get(
                THINKUMENT_RUNTIME_CONTRIBUTOR_ENTRYPOINT_GROUP,
                (),
            )
        )

    return ()


def installed_runtime_contributor_entry_points_v1() -> tuple[Any, ...]:
    """Return installed contributor entry points in deterministic order."""

    return tuple(
        sorted(
            _metadata_entry_points(),
            key=_entry_point_identity,
        )
    )


def _load_contributor(entry_point: Any):
    identity = _entry_point_identity(entry_point)
    try:
        callback = entry_point.load()
    except Exception as exc:  # pragma: no cover - exact loader is external
        raise RuntimeContributorError(
            "could not load Thinkument runtime contributor "
            f"{identity!r}"
        ) from exc

    if not callable(callback):
        raise RuntimeContributorError(
            "Thinkument runtime contributor must resolve to a callable: "
            f"{identity!r}"
        )

    return callback


def activate_installed_runtime_contributors_v1(
) -> tuple[RuntimeContributorActivationV1, ...]:
    """Activate every installed runtime contributor exactly once per process.

    Contract for a contributing package:

    * register a no-argument callable under
      ``thinkument.runtime_contributors.v1``;
    * make the callable safe to run during ordinary application startup;
    * do not rely on entry-point ordering for semantic precedence.

    Central activation itself is idempotent and serialized.  A failing callback
    is never marked active, so the bootstrap fails closed rather than leaving a
    false successful receipt.
    """

    receipts: list[RuntimeContributorActivationV1] = []

    with _ACTIVATION_LOCK:
        for entry_point in installed_runtime_contributor_entry_points_v1():
            identity = _entry_point_identity(entry_point)
            activated_now = identity not in _ACTIVATED

            if activated_now:
                if identity in _ACTIVATING:
                    raise RuntimeContributorError(
                        "Thinkument runtime contributor re-entered central "
                        f"activation before completing: {identity!r}"
                    )

                callback = _load_contributor(entry_point)
                _ACTIVATING.add(identity)
                try:
                    result = callback()
                except Exception as exc:
                    raise RuntimeContributorError(
                        "Thinkument runtime contributor failed during "
                        f"activation: {identity!r}"
                    ) from exc
                finally:
                    _ACTIVATING.discard(identity)

                _ACTIVATED[identity] = result

            receipts.append(
                RuntimeContributorActivationV1(
                    distribution=identity[0],
                    name=identity[1],
                    value=identity[2],
                    activated_now=activated_now,
                )
            )

    return tuple(receipts)


def _reset_runtime_contributors_for_tests() -> None:
    with _ACTIVATION_LOCK:
        _ACTIVATED.clear()
        _ACTIVATING.clear()


__all__ = [
    "RuntimeContributorActivationV1",
    "RuntimeContributorError",
    "THINKUMENT_RUNTIME_CONTRIBUTOR_ENTRYPOINT_GROUP",
    "activate_installed_runtime_contributors_v1",
    "installed_runtime_contributor_entry_points_v1",
]
