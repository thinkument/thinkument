"""Catalogue and schema validation namespace for ThinkClient."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    kind: str
    errors: List[str]
    title: Optional[str] = None


class CatalogueNamespace:
    """Validates schemas and publishes immutable manifests to the global catalogue."""

    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def validate(self, manifest_or_path: Mapping[str, Any] | str) -> ValidationReport:
        """Validate a widget or program JSON manifest offline in <1ms."""
        if isinstance(manifest_or_path, str):
            if os.path.exists(manifest_or_path):
                with open(manifest_or_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            else:
                manifest = json.loads(manifest_or_path)
        else:
            manifest = dict(manifest_or_path)

        errors: List[str] = []
        kind = str(manifest.get("kind", ""))

        if not kind:
            errors.append("Manifest is missing required top-level 'kind' field")
        elif kind == "json_widget_v1":
            if not manifest.get("name"):
                errors.append("Widget manifest missing 'name'")
            if "declaration" not in manifest:
                errors.append("Widget manifest missing 'declaration'")
            if "signals" not in manifest:
                errors.append("Widget manifest missing 'signals'")
        elif kind == "think_program_v1":
            run = manifest.get("run") or {}
            program = run.get("program") or {}
            if "flow" not in program:
                errors.append("Program manifest missing 'flow' array")
            if "widgets" not in program:
                errors.append("Program manifest missing 'widgets' mapping")
        else:
            errors.append(f"Unrecognized manifest kind: {kind!r}")

        return ValidationReport(
            valid=len(errors) == 0,
            kind=kind,
            errors=errors,
            title=manifest.get("name") or manifest.get("run", {}).get("program", {}).get("info", {}).get("title"),
        )

    def publish_widget(self, manifest_or_path: Mapping[str, Any] | str) -> Dict[str, Any]:
        """Publish a validated JSON widget manifest to the cloud catalogue."""
        report = self.validate(manifest_or_path)
        if not report.valid:
            raise ValueError(f"Cannot publish invalid manifest: {report.errors}")

        if isinstance(manifest_or_path, str) and os.path.exists(manifest_or_path):
            with open(manifest_or_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        else:
            manifest = dict(manifest_or_path)

        url = f"{self.base_url}/api/v1/catalogue/widgets/"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data_bytes = json.dumps(manifest).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            raise RuntimeError(f"HTTP {exc.code} on publishing: {err_body}") from exc
