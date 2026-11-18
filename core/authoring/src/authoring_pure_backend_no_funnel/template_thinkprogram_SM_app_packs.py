from __future__ import annotations

"""Pure P/SM/C authoring helpers for HAI app-pack selection.

An app pack is a session-metadata choice. It is not a fourth runtime input,
not a Starter property, and not the browser ``opinionation_module``.

The public wire shape is intentionally dead JSON so remote callers do not need
to import Thinkument runtime or Django packages::

    SM["app_pack_mould"] = {
        "app_pack": "packito",
        "app_args": {"lesson": "pedagogy"},
    }

Django/Flask host composition still decides which pack ids are installed. The
selected pack id only chooses one of those installed packs for this session.
"""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any


# This literal is the public P/SM/C wire contract shared with
# app_pack_mould.runtime.APP_PACK_SESSION_METADATA_KEY. A cross-package E2E test in
# service proves the SDK and installed HAI runtime stay aligned.
APP_PACK_SESSION_METADATA_KEY = "app_pack_mould"


def with_app_pack(
    SM: Mapping[str, Any] | None = None,
    *,
    app_pack: str,
    app_args: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a copied SM document selecting one HAI app pack.

    ``app_pack`` is the installed manifest id, for example ``"packito"``.
    ``app_args`` is pack-owned dead JSON exposed to that browser pack.

    The helper performs only local shape validation. Whether a pack id exists
    is deployment composition and is therefore proven/validated by the remote
    host's installed app-pack catalog rather than by this independent SDK.
    """

    if SM is not None and not isinstance(SM, Mapping):
        raise TypeError("SM must be a mapping or None")

    pack = str(app_pack or "").strip()
    if not pack:
        raise ValueError("app_pack must be a non-empty installed app-pack id")

    if app_args is not None and not isinstance(app_args, Mapping):
        raise TypeError("app_args must be a mapping or None")

    out = deepcopy(dict(SM or {}))
    out[APP_PACK_SESSION_METADATA_KEY] = {
        "app_pack": pack,
        "app_args": deepcopy(dict(app_args or {})),
    }
    return out


def app_pack_selection(
    SM: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Read and validate the SDK-visible app-pack selection from SM.

    ``None`` means the flow did not make an explicit choice and the installed
    HAI default applies.
    """

    if SM is None:
        return None
    if not isinstance(SM, Mapping):
        raise TypeError("SM must be a mapping or None")

    raw = SM.get(APP_PACK_SESSION_METADATA_KEY)
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"SM.{APP_PACK_SESSION_METADATA_KEY} must be an object when present"
        )

    pack = str(raw.get("app_pack") or "").strip()
    if not pack:
        raise ValueError(
            f"SM.{APP_PACK_SESSION_METADATA_KEY}.app_pack must be non-empty"
        )

    raw_args = raw.get("app_args", {})
    if not isinstance(raw_args, Mapping):
        raise ValueError(
            f"SM.{APP_PACK_SESSION_METADATA_KEY}.app_args must be an object"
        )

    return {
        "app_pack": pack,
        "app_args": deepcopy(dict(raw_args)),
    }


__all__ = [
    "APP_PACK_SESSION_METADATA_KEY",
    "app_pack_selection",
    "with_app_pack",
]
