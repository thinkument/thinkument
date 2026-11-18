from __future__ import annotations

"""
authoring_funneling.d_module_composition_and_stitching.manifest
================================================================
Canonical schema validation, normalization, and fingerprinting for Thinkument Modules (think_module_v1).
A module is a sealed, first-class tuple: <P, C, SM, Interface>.
"""

from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any, Dict, Mapping

from bindings2bindingsTM import CompilationError


LANG_THINK_MODULE_V1 = "think_module_v1"

_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+(/[a-zA-Z0-9_\-]+)?$")
_VALID_VERSION_RE = re.compile(r"^[0-9]+(\.[0-9]+)*(-[a-zA-Z0-9_\.]+)?$")


def validate_think_module_v1(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """Strictly validate a think_module_v1 manifest according to the canonical specification.
    
    Raises:
        CompilationError: If any required key is missing or schema invariant is violated.
    """
    if not isinstance(manifest, Mapping):
        raise CompilationError("invalid_module_manifest", ("module",))

    m = deepcopy(dict(manifest))
    if m.get("kind") != LANG_THINK_MODULE_V1:
        raise CompilationError(
            "unsupported_module_kind",
            ("module", "kind"),
            f"Expected {LANG_THINK_MODULE_V1!r}, got {m.get('kind')!r}",
        )

    name = m.get("name")
    if not isinstance(name, str) or not _VALID_NAME_RE.match(name.strip()):
        raise CompilationError(
            "invalid_module_name",
            ("module", "name"),
            "Module name must be a non-empty string like 'company/flow' or 'widget_name'",
        )

    version = m.get("version")
    if not isinstance(version, str) or not _VALID_VERSION_RE.match(version.strip()):
        raise CompilationError(
            "invalid_module_version",
            ("module", "version"),
            "Module version must follow semver format (e.g. '1.0.0')",
        )

    interface = m.get("interface")
    if not isinstance(interface, Mapping):
        raise CompilationError("missing_module_interface", ("module", "interface"))

    inputs = interface.get("inputs", {})
    if not isinstance(inputs, Mapping):
        raise CompilationError("invalid_interface_inputs", ("module", "interface", "inputs"))

    outputs = interface.get("outputs", {})
    if not isinstance(outputs, Mapping):
        raise CompilationError("invalid_interface_outputs", ("module", "interface", "outputs"))

    roles = interface.get("roles", {})
    if not isinstance(roles, Mapping):
        raise CompilationError("invalid_interface_roles", ("module", "interface", "roles"))

    # Validate P
    p = m.get("P")
    if not isinstance(p, Mapping):
        raise CompilationError("missing_module_p", ("module", "P"))

    p_body = p.get("run", {}).get("program", {}) if "run" in p else p
    widgets = p_body.get("widgets")
    flow = p_body.get("flow")

    if not isinstance(widgets, Mapping) or not widgets:
        raise CompilationError("module_p_missing_widgets", ("module", "P", "widgets"))

    if not isinstance(flow, list) or not flow:
        raise CompilationError("module_p_missing_flow", ("module", "P", "flow"))

    # Verify all widgets inside module P are inline json_widget_v1
    for wid, wdecl in widgets.items():
        if not isinstance(wdecl, Mapping):
            raise CompilationError("invalid_widget_declaration", ("module", "P", "widgets", wid))
        w_inner = wdecl.get("widget") or wdecl.get("inline_widget") or wdecl.get("inline")
        if not isinstance(w_inner, Mapping) or w_inner.get("kind") != "json_widget_v1":
            raise CompilationError(
                "non_inline_widget_in_module",
                ("module", "P", "widgets", wid),
                "All widgets in a published module must be inline json_widget_v1 datomatons",
            )

    # Validate C
    c = m.get("C", {})
    if not isinstance(c, Mapping):
        raise CompilationError("invalid_module_c", ("module", "C"))

    # Validate SM
    sm = m.get("SM", {})
    if not isinstance(sm, Mapping):
        raise CompilationError("invalid_module_sm", ("module", "SM"))

    return m


def normalize_think_module_v1(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize a valid module manifest into canonical sorted JSON form."""
    m = validate_think_module_v1(manifest)
    normalized = {
        "kind": LANG_THINK_MODULE_V1,
        "name": str(m["name"]).strip(),
        "version": str(m["version"]).strip(),
        "title": str(m.get("title") or m["name"]).strip(),
        "interface": {
            "inputs": dict(m.get("interface", {}).get("inputs", {})),
            "outputs": dict(m.get("interface", {}).get("outputs", {})),
            "roles": dict(m.get("interface", {}).get("roles", {})),
        },
        "P": dict(m["P"]),
        "C": dict(m.get("C", {})),
        "SM": dict(m.get("SM", {})),
    }
    return normalized


def compute_module_fingerprint(manifest: Mapping[str, Any]) -> str:
    """Compute the SHA256 content fingerprint of a canonical module manifest."""
    normalized = normalize_think_module_v1(manifest)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(("think_module_v1\0" + payload).encode("utf-8")).hexdigest()


__all__ = [
    "LANG_THINK_MODULE_V1",
    "compute_module_fingerprint",
    "normalize_think_module_v1",
    "validate_think_module_v1",
]
