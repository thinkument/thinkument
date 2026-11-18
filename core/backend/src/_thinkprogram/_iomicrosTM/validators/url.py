from __future__ import annotations

from typing import Any, Dict, Iterable
from urllib.parse import urlparse

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.validators._common import unwrap


def validate_url(value: Any, *, schemes: Iterable[str] = ("http", "https")) -> tuple[bool, str | None]:
    value = unwrap(value)
    if not isinstance(value, str) or not value.strip():
        return False, "must be a non-empty URL string"
    raw = value.strip()
    if any(ch.isspace() for ch in raw):
        return False, "URL must not contain whitespace"
    parsed = urlparse(raw)
    allowed = {str(s).lower() for s in schemes}
    if parsed.scheme.lower() not in allowed:
        return False, f"URL scheme must be one of: {', '.join(sorted(allowed))}"
    if not parsed.netloc:
        return False, "URL must include a network location"
    if parsed.username is not None or parsed.password is not None:
        return False, "URL must not embed credentials"
    try:
        if parsed.hostname is None:
            return False, "URL must include a valid hostname"
        _ = parsed.port
    except ValueError:
        return False, "URL contains an invalid port"
    return True, None


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": [
            "https://example.com",
            "http://example.com/a?x=1",
            {"__boxed__": True, "value": "https://sub.example.org/path"},
        ],
        "invalid_examples": [
            "example.com",
            "ftp://example.com",
            "https:///broken",
            "https://example.com:bad",
            "https://user:pass@example.com",
            "",
            None,
        ],
        "modality": "url",
    }],
    description="Credential-free absolute HTTP(S) URL.",
)
def is_http_url(value: Any) -> tuple[bool, str | None]:
    return validate_url(value)


@guidance_for("is_http_url")
def is_http_url_guidance() -> Dict[str, Any]:
    return {
        "message": "Provide a complete http:// or https:// URL.",
        "modality": "url",
    }


__all__ = ["validate_url", "is_http_url", "is_http_url_guidance"]
