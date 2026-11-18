from __future__ import annotations

"""_vial_js-owned static-root declaration."""

from pathlib import Path


STATIC_ROOT = Path(__file__).resolve().parent / "thinkumentJS"


__all__ = ["STATIC_ROOT"]