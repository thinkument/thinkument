"""Pure configuration contract shared by provisioning, readiness and clients."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Mapping


class CredentialError(ValueError):
    """Safe diagnostic containing field/check names, never configured values."""


@dataclass(frozen=True)
class AccountSpec:
    holder: str
    password: bool = False
    api_key: bool = False
    admin: bool = False

    def __post_init__(self):
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.holder):
            raise CredentialError("Invalid managed account holder")

    @property
    def fields(self):
        fields = ["USER_NAME", "USER_EMAIL"]
        if self.password:
            fields.append("PASSWORD")
        if self.api_key:
            fields.extend(("APIKEY_PUBLIC", "APIKEY_SECRET", "APIKEY_EXPIRES_AT"))
        return tuple(f"CUSKEY_{self.holder}__{name}" for name in fields)


@dataclass(frozen=True)
class Credentials:
    spec: AccountSpec
    username: str = field(repr=False)
    email: str = field(repr=False)
    password: str | None = field(default=None, repr=False)
    public: str | None = field(default=None, repr=False)
    secret: str | None = field(default=None, repr=False)
    expires_at: datetime | None = field(default=None, repr=False)


def load_credentials(spec: AccountSpec, values: Mapping[str, str], *, now=None):
    prefix = f"CUSKEY_{spec.holder}__"
    for key in spec.fields:
        value = values.get(key)
        if not isinstance(value, str) or not value.strip():
            raise CredentialError(f"Missing or empty managed credential field: {key}")
        if any(character in value for character in ("\n", "\r", "\0")):
            raise CredentialError(f"Invalid managed credential field: {key}")
    username = values[prefix + "USER_NAME"]
    email = values[prefix + "USER_EMAIL"]
    if len(username) > 150 or "@" not in email or len(email) > 254:
        raise CredentialError(f"Invalid managed account identity: {spec.holder}")
    expiry = None
    if spec.api_key:
        public = values[prefix + "APIKEY_PUBLIC"]
        secret = values[prefix + "APIKEY_SECRET"]
        if len(public) > 64 or any(c.isspace() or c == ":" for c in public + secret):
            raise CredentialError(f"Invalid API credential format: {spec.holder}")
        raw = values[prefix + "APIKEY_EXPIRES_AT"]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", raw):
            raise CredentialError(f"Expected explicit UTC timestamp: {prefix}APIKEY_EXPIRES_AT")
        try:
            expiry = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            raise CredentialError(f"Invalid UTC timestamp: {prefix}APIKEY_EXPIRES_AT") from None
        if expiry <= (now or datetime.now(timezone.utc)):
            raise CredentialError(f"Expired managed API credential: {spec.holder}")
    return Credentials(spec, username, email,
                       values[prefix + "PASSWORD"] if spec.password else None,
                       values[prefix + "APIKEY_PUBLIC"] if spec.api_key else None,
                       values[prefix + "APIKEY_SECRET"] if spec.api_key else None, expiry)
