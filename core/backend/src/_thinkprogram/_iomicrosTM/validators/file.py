from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.validators._common import unwrap


def normalize_extensions(extensions: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    values = [] if extensions is None else list(extensions)
    for raw in values:
        item = str(raw or "").strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = f".{item}"
        out.append(item)
    return sorted(set(out))


def validate_local_filepath(value: Any) -> tuple[bool, str | None]:
    value = unwrap(value)
    if not isinstance(value, str) or not value.strip():
        return False, "must be a non-empty filepath string"
    raw = value.strip()
    if "\x00" in raw:
        return False, "filepath must not contain null bytes"
    if "://" in raw or "?" in raw or "#" in raw:
        return False, "filepath must be local, not a URL/URI"
    normalized = raw.replace("\\", "/")
    base = os.path.basename(normalized)
    if not base or base in {".", ".."}:
        return False, "filepath must point to a concrete file"
    windows_abs = bool(re.match(r"^[A-Za-z]:[\\/]", raw))
    looks_path = "/" in normalized or windows_abs or "." in base
    if not looks_path:
        return False, "value does not look like a local filepath"
    return True, None


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": ["./data/file.txt", "/tmp/file.bin", r"C:\data\file.csv", "report.pdf"],
        "invalid_examples": ["https://example.com/file.txt", "not-a-path", "", None],
        "modality": "file_filepath",
    }],
    description="Local-looking file path; existence is intentionally not checked.",
)
def local_filepath(value: Any) -> tuple[bool, str | None]:
    return validate_local_filepath(value)


@guidance_for("local_filepath")
def local_filepath_guidance() -> Dict[str, Any]:
    return {
        "message": "Provide a local file path such as ./data/report.pdf.",
        "modality": "file_filepath",
    }


@validator(
    arg_combos=[{
        "args": {"allowed_extensions": [".csv", ".json"]},
        "valid_examples": ["./data/file.csv", {"__boxed__": True, "value": "report.JSON"}],
        "invalid_examples": ["./data/file.txt", "not-a-path", None],
        "modality": "file_filepath",
    }],
    description="Local filepath whose filename has one of the allowed extensions.",
)
def filepath_has_allowed_extension(
    value: Any,
    *,
    allowed_extensions: Iterable[str],
) -> tuple[bool, str | None]:
    ok, message = validate_local_filepath(value)
    if not ok:
        return ok, message
    allowed = normalize_extensions(allowed_extensions)
    if not allowed:
        return False, "allowed_extensions must contain at least one extension"
    raw = str(unwrap(value)).lower()
    ok = any(raw.endswith(ext) for ext in allowed)
    return ok, None if ok else "filepath must end with one of: " + ", ".join(allowed)


@guidance_for("filepath_has_allowed_extension")
def filepath_has_allowed_extension_guidance(*, allowed_extensions: Iterable[str]) -> Dict[str, Any]:
    allowed = normalize_extensions(allowed_extensions)
    return {
        "message": "Use a file ending with one of: " + ", ".join(allowed),
        "args": {"allowed_extensions": allowed},
        "modality": "file_filepath",
    }


__all__ = [
    "normalize_extensions",
    "validate_local_filepath",
    "local_filepath",
    "local_filepath_guidance",
    "filepath_has_allowed_extension",
    "filepath_has_allowed_extension_guidance",
]
