from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

from ._globals import (
    Q_MESSAGE_LEVELS,
)

from ._surface_specs import (
    DatumQEvalV1,
)


def _message_v1(
    raw: Any,
    *,
    default_level: str = "info",
    default_text: str = "",
) -> Dict[str, str]:
    if isinstance(raw, Mapping):
        level = str(
            raw.get("level") or default_level
        ).strip().lower()
        text = str(
            raw.get("text")
            or raw.get("message")
            or default_text
        )
    else:
        level = default_level
        text = str(raw or default_text)

    if level not in Q_MESSAGE_LEVELS:
        level = (
            default_level
            if default_level in Q_MESSAGE_LEVELS
            else "info"
        )

    return {
        "level": level,
        "text": text,
    }


def _messages_v1(
    raw: Any,
    *,
    default_level: str = "info",
    default_text: str = "",
) -> List[Dict[str, str]]:
    """
    Normalize widget result message surface.

    Public compatibility law:

        return {"message": {...}}      # old/singular form
        return {"messages": [{...}]}   # new/plural form

    Engine law:

        result["messages"] is always the normalized plural list.
        result["message"] remains a compatibility alias for the last message,
        or the default message when the list is empty.

    A string is a single message, not a sequence of characters.
    """

    if raw is None:
        return [
            _message_v1(
                None,
                default_level=default_level,
                default_text=default_text,
            )
        ]

    if isinstance(raw, Mapping):
        return [
            _message_v1(
                raw,
                default_level=default_level,
                default_text=default_text,
            )
        ]

    if isinstance(raw, (str, bytes, bytearray)):
        return [
            _message_v1(
                raw,
                default_level=default_level,
                default_text=default_text,
            )
        ]

    if isinstance(raw, Sequence):
        out: List[Dict[str, str]] = []
        for item in list(raw):
            out.append(
                _message_v1(
                    item,
                    default_level=default_level,
                    default_text=default_text,
                )
            )
        return out

    return [
        _message_v1(
            raw,
            default_level=default_level,
            default_text=default_text,
        )
    ]


def _primary_message_v1(
    messages: Sequence[Mapping[str, Any]],
    *,
    default_level: str = "info",
    default_text: str = "",
) -> Dict[str, str]:
    if messages:
        return _message_v1(
            messages[-1],
            default_level=default_level,
            default_text=default_text,
        )

    return _message_v1(
        None,
        default_level=default_level,
        default_text=default_text,
    )


def _eval_messages_v1(
    ev: DatumQEvalV1,
) -> Tuple[Dict[str, str], ...]:
    """
    Internal bridge while DatumQEvalV1 keeps the singular .message field for
    compatibility with nearby code/tests.

    Prefer ev.messages when present; fall back to ev.message for older
    construction sites.
    """
    if ev.messages:
        return tuple(dict(x) for x in ev.messages)

    if ev.message:
        return (dict(ev.message),)

    return ()


__all__ = [
    "_message_v1",
    "_messages_v1",
    "_primary_message_v1",
    "_eval_messages_v1",
]