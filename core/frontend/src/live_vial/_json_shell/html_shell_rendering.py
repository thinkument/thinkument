from __future__ import annotations

"""Transport-only HTML shell helpers for the modular Thinkument web client."""

import json
from importlib.metadata import entry_points
from html import escape
from typing import Any, Dict, Mapping, Optional


THINKUMENT_CLIENT_CONFIG_RESERVED_KEYS = frozenset(
    {
        "kind",
        "sessionId",
        "rootId",
        "identityId",
        "role",
        "title",
        "endpoints",
        "modules",
        "initialState",
        "initialEventSeq",
        "G",
        "polling",
        "dispatchContract",
    }
)


THINKUMENT_BROWSER_BOOT_ENTRYPOINT_GROUP = "thinkument.browser_boot_config.v1"


def installed_browser_boot_config_v1() -> dict[str, Any]:
    """Compose inert boot defaults supplied by installed runtime packages."""
    discovered = entry_points()
    providers = discovered.select(group=THINKUMENT_BROWSER_BOOT_ENTRYPOINT_GROUP) if hasattr(discovered, "select") else discovered.get(THINKUMENT_BROWSER_BOOT_ENTRYPOINT_GROUP, ())
    result: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for ep in sorted(providers, key=lambda item: (item.name, item.value)):
        source = f"{getattr(getattr(ep, 'dist', None), 'name', 'unknown distribution')}:{ep.name} -> {ep.value}"
        try:
            provider = ep.load()
            values = provider() if callable(provider) else provider
            if not isinstance(values, Mapping):
                raise TypeError("browser boot contributor must return a mapping")
            json.dumps(values, allow_nan=False)
            for key, value in values.items():
                if not isinstance(key, str) or key in THINKUMENT_CLIENT_CONFIG_RESERVED_KEYS:
                    raise ValueError(f"invalid or reserved browser boot key {key!r}")
                if key in result:
                    raise ValueError(f"duplicate browser boot key {key!r}; first provider {sources[key]}")
                result[key] = value
                sources[key] = source
        except Exception as exc:
            raise ValueError(f"invalid browser boot provider {source}: {exc}") from exc
    return result


def json_script_value(value: Any) -> str:
    text = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def initial_fragment() -> str:
    regions = (
        "header",
        "navigation",
        "page_alerts",
        "actions",
        "main",
        "overlays",
        "footer",
    )
    body_rows = []
    for name in regions:
        tag = "main" if name == "main" else "section"
        body_rows.append(
            f'<{tag} class="thinkument-region '
            f'thinkument-region-{name}" '
            f'data-thinkument-region="{name}" '
            f'data-formreact-region="{name}"></{tag}>'
        )
    body = "".join(body_rows)
    return (
        f'<section class="thinkument-shell" '
        f'data-thinkument-shell>{body}</section>'
    )


def build_thinkument_client_config(
    *,
    root_id: str,
    identity_id: str,
    role: Optional[str],
    endpoints: Mapping[str, str],
    initial_state: Mapping[str, Any],
    initial_event_seq: int,
    opinionation_module_url: str = "",
    title: str = "Thinkument Run",
    G: Optional[Mapping[str, Any]] = None,
    polling: Optional[Mapping[str, Any]] = None,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    required = {
        "latestEventSeq",
        "events",
        "eps",
        "dispatch",
        "dispatchFunked",
    }
    missing = required - set(endpoints)
    if missing:
        raise ValueError(
            "missing Thinkument client endpoint(s): "
            f"{sorted(missing)}"
        )

    config: Dict[str, Any] = {
        "kind": "thinkument_web_client_config_v1",
        "sessionId": str(
            initial_state.get("session_id")
            or initial_state.get("access_id")
            or root_id
        ),
        "rootId": str(root_id),
        "identityId": str(identity_id),
        "role": role,
        "title": str(title),
        "endpoints": {
            key: str(value)
            for key, value in endpoints.items()
        },
        "modules": {
            "opinionation": str(opinionation_module_url or ""),
        },
        "dispatchContract": {
            "kind": "thinkument_dispatch_contract_v1",
            "requestIdField": "request_id",
            "identityIdField": "identity_id",
            "cursorField": "my_current_event_seq_number",
        },
        "initialState": dict(initial_state),
        "initialEventSeq": int(initial_event_seq or 0),
        "G": {
            "num_rows": 12,
            "num_cols": 12,
            "gap": "1rem",
            **dict(G or {}),
        },
        "polling": {
            "eventPageSize": 100,
            "basePeriodMs": 30_000,
            "dispatchPeriodMs": 5_000,
            "dispatchWindowMs": 60_000,
            "remoteActivityPeriodMs": 15_000,
            "remoteActivityWindowMs": 60_000,
            "epsPollPeriodMs": 250,
            "epsPageSize": 100,
            "maxEpsRows": 512,
            **dict(polling or {}),
        },
    }

    extra_values = dict(extra or {})
    collisions = (
        THINKUMENT_CLIENT_CONFIG_RESERVED_KEYS
        & set(extra_values)
    )
    if collisions:
        raise ValueError(
            "extra Thinkument client configuration "
            "may not replace transport keys: "
            f"{sorted(collisions)}"
        )

    boot_values = installed_browser_boot_config_v1()
    if set(boot_values) & set(extra_values):
        raise ValueError("extra client configuration may not replace installed browser boot defaults")
    config.update(boot_values)
    config.update(extra_values)
    return config


def render_shell_html(
    *,
    title: str,
    client_config: Mapping[str, Any],
    shim_url: str,
    css_url: Optional[str] = None,
    embed: bool = False,
) -> str:
    root_id = str(client_config["rootId"])
    config_id = f"{root_id}-config"
    root_id_attr = escape(root_id, quote=True)
    config_id_attr = escape(config_id, quote=True)
    title_text = escape(str(title or "Thinkument Run"))
    shim = escape(str(shim_url), quote=True)
    config_json = json_script_value(client_config)
    css = (
        '<link rel="stylesheet" '
        f'href="{escape(css_url, quote=True)}">'
        if css_url
        else ""
    )

    body = f"""
<div id="{root_id_attr}" class="thinkument-root" data-thinkument-config-id="{config_id_attr}">
  {initial_fragment()}
</div>
<script type="application/json" id="{config_id_attr}">{config_json}</script>
<script type="module" src="{shim}"></script>
""".strip()

    if embed:
        return f"{css}\n{body}" if css else body

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{title_text}</title>
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    {css}
  </head>
  <body>
    {body}
  </body>
</html>"""


__all__ = [
    "THINKUMENT_CLIENT_CONFIG_RESERVED_KEYS",
    "build_thinkument_client_config",
    "initial_fragment",
    "json_script_value",
    "render_shell_html",
]
