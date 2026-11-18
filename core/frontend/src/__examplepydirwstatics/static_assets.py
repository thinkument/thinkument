from __future__ import annotations

"""__examplepydirwstatics-owned static-root declaration."""

from pathlib import Path


STATIC_ROOT = Path(__file__).resolve().parent / "anystaticsdirname"


__all__ = ["STATIC_ROOT"]