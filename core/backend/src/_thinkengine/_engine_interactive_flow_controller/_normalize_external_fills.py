from __future__ import annotations

from typing import Any, Dict


# ---------------------------------------------------------------------------
# Submitted-fill normalization
# ---------------------------------------------------------------------------


def _collapse_composite_keys(
    user_fill: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Collapse dotted micro-field keys into one macro mapping.

    Example
    -------
        {
            "person.first": "Ada",
            "person.last": "Lovelace",
            "age": "42",
        }

    becomes:

        {
            "person": {
                "first": "Ada",
                "last": "Lovelace",
            },
            "age": "42",
        }

    Laws
    ----
    - Non-dotted keys pass through unchanged.
    - If both ``fid`` and ``fid.sub`` are present, dotted entries win and the
      scalar or non-mapping ``fid`` value is replaced by a mapping.
    - Only macro datum IDs reach the strict engine boundary.
    """
    if not user_fill:
        return {}

    grouped: Dict[str, Any] = {}

    for key, value in user_fill.items():
        if not isinstance(key, str) or "." not in key:
            grouped[key] = value
            continue

        datum_id, micro_name = key.split(".", 1)

        bucket = grouped.get(datum_id)
        if not isinstance(bucket, dict):
            bucket = {}

        bucket[micro_name] = value
        grouped[datum_id] = bucket

    return grouped


def _normalize_repeated_submit_values(
    user_fill: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Normalize already-parsed form values without altering repeated values.

    HTTP form parsers commonly represent repeated field names as list values.
    Those lists are preserved exactly so checkbox and other repeated-input
    renderers remain micro-agnostic at this boundary.
    """
    if not user_fill:
        return {}

    return {
        str(key): value
        for key, value in dict(user_fill).items()
    }


def _normalize_for_composite_platform(
    user_fill: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Apply unconditional dotted-key collapse before engine submission.

    No single-micro unwrapping occurs. Each datum ID reaches the engine as one
    macro value, and composite macro values remain mappings.
    """
    if not user_fill:
        return {}

    return _collapse_composite_keys(user_fill)


__all__ = [
    "_collapse_composite_keys",
    "_normalize_repeated_submit_values",
    "_normalize_for_composite_platform",
]