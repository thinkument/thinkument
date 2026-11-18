from __future__ import annotations

import re
from typing import Any, Dict

from _thinkprogram._iomicrosTM.core.micro_validator_registry import guidance_for, validator
from _thinkprogram._iomicrosTM.validators._common import unwrap

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@validator(
    arg_combos=[{
        "args": {},
        "valid_examples": ["user@example.com", {"__boxed__": True, "value": "a.b+c@sub.domain.io"}],
        "invalid_examples": ["not-an-email", "missing-at.com", "@no-local", "", None],
        "modality": "email",
    }],
    description="Pragmatic user-facing email syntax check; not delivery verification.",
)
def is_basic_email(value: Any) -> tuple[bool, str | None]:
    value = unwrap(value)
    ok = isinstance(value, str) and len(value) <= 320 and bool(_EMAIL_RE.fullmatch(value))
    return ok, None if ok else "must be a valid email address"


@guidance_for("is_basic_email")
def is_basic_email_guidance() -> Dict[str, Any]:
    return {
        "message": "Provide an email address such as user@example.com.",
        "modality": "email",
    }


__all__ = ["is_basic_email", "is_basic_email_guidance"]
