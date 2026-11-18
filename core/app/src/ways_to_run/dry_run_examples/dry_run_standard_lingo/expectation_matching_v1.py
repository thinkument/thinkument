from __future__ import annotations

"""Strategy-agnostic dotted-path expectation matching for dry-run E data."""

from typing import Any, Mapping, Optional, Sequence


def path_get_v1(value: Any, dotted_path: str) -> Any:
    current = value
    for segment in str(dotted_path).split("."):
        if isinstance(current, Mapping):
            if segment not in current:
                raise KeyError(dotted_path)
            current = current[segment]
            continue
        if isinstance(current, list):
            current = current[int(segment)]
            continue
        raise KeyError(dotted_path)
    return current


def _path_parent_and_leaf_v1(value: Any, dotted_path: str) -> tuple[Any, str]:
    segments = str(dotted_path).split(".")
    if not segments or any(segment == "" for segment in segments):
        raise KeyError(dotted_path)
    current = value
    for segment in segments[:-1]:
        if isinstance(current, Mapping):
            if segment not in current:
                raise KeyError(dotted_path)
            current = current[segment]
            continue
        if isinstance(current, list):
            current = current[int(segment)]
            continue
        raise KeyError(dotted_path)
    return current, segments[-1]


def needle_mismatch_v1(
    value: Mapping[str, Any],
    needle: Mapping[str, Any],
) -> Optional[str]:
    for raw_key, expected in needle.items():
        key = str(raw_key)
        contains = key.endswith("__contains")
        absent = key.endswith("__absent")

        if contains:
            path = key[: -len("__contains")]
        elif absent:
            path = key[: -len("__absent")]
        else:
            path = key

        if absent:
            try:
                parent, leaf = _path_parent_and_leaf_v1(value, path)
            except (KeyError, IndexError, TypeError, ValueError):
                return f"missing parent path for absence assertion {path!r}"
            if not isinstance(parent, Mapping):
                return f"parent of {path!r} is not a mapping; actual={parent!r}"
            should_be_absent = bool(expected)
            is_absent = leaf not in parent
            if is_absent != should_be_absent:
                if should_be_absent:
                    return f"{path!r} expected absent, got {parent.get(leaf)!r}"
                return f"{path!r} expected present, but is absent"
            continue

        try:
            actual = path_get_v1(value, path)
        except (KeyError, IndexError, TypeError, ValueError):
            return f"missing path {path!r}"

        if contains:
            if isinstance(actual, str):
                if str(expected) not in actual:
                    return (
                        f"{path!r} does not contain {expected!r}; "
                        f"actual={actual!r}"
                    )
            elif isinstance(actual, (list, tuple, set)):
                if expected not in actual:
                    return (
                        f"{path!r} does not contain {expected!r}; "
                        f"actual={actual!r}"
                    )
            else:
                return f"{path!r} is not containable; actual={actual!r}"
            continue

        if actual != expected:
            return f"{path!r} expected {expected!r}, got {actual!r}"
    return None


def assert_needle_v1(
    value: Mapping[str, Any],
    needle: Mapping[str, Any],
    *,
    label: str,
) -> None:
    mismatch = needle_mismatch_v1(value, needle)
    if mismatch is not None:
        raise AssertionError(
            f"{label}: {mismatch}\n"
            f"needle={dict(needle)!r}\n"
            f"value={dict(value)!r}"
        )


def assert_ordered_subsequence_v1(
    values: Sequence[Mapping[str, Any]],
    needles: Sequence[Mapping[str, Any]],
    *,
    label: str,
) -> None:
    cursor = 0
    for needle_index, needle in enumerate(needles):
        while cursor < len(values):
            mismatch = needle_mismatch_v1(values[cursor], needle)
            cursor += 1
            if mismatch is None:
                break
        else:
            raise AssertionError(
                f"{label} ordered-subsequence mismatch at needle index "
                f"{needle_index}: {dict(needle)!r}; values={list(values)!r}"
            )


__all__ = [
    "assert_needle_v1",
    "assert_ordered_subsequence_v1",
    "needle_mismatch_v1",
    "path_get_v1",
]
