from __future__ import annotations

"""Storagics epsilon subapp (storage usage and managed delivery)."""

from .channels import (
    AUDIT_STORAGE_USAGE_CHANNEL,
    AUDIT_STORAGE_USAGE_SCHEMA_V1,
)
try:
    from .delivery import execute_managed_delivery
except ImportError:  # storagics is an optional financial-core provider
    execute_managed_delivery = None

__all__ = [
    "AUDIT_STORAGE_USAGE_CHANNEL",
    "AUDIT_STORAGE_USAGE_SCHEMA_V1",
    "execute_managed_delivery",
]
