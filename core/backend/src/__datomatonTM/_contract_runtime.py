from __future__ import annotations

from typing import Any, Dict, Mapping

from _thinkprogram._iomicrosTM.tiny_helpers import (
    DeadJSONError,
    assert_dead_json,
)

from __exceptions.engine import (
    DatumLifecycleContractError,
)

from ._globals import (
    Q_STATUS_BLOCKED,
    Q_STATUS_DONE,
    Q_STATUS_REEXPLODE,
)

from ._messages import (
    _messages_v1,
    _primary_message_v1,
)

from ._surface_specs import (
    DATUM_WIDGET_INPUT_REQUIRED_KEYS_V1,
    DATUM_WIDGET_RESULT_STATUSES_V1,
)


def ensure_widget_input_contract_v1(
    q_input_dead: Mapping[str, Any],
) -> Dict[str, Any]:
    """
    Engine -> widget boundary contract.

    This validates the dead-json observation packet before the live emit
    callable is attached. The public contract includes "emit", but "emit" is
    intentionally excluded from dead-json validation because it is callable.
    """
    if not isinstance(q_input_dead, Mapping):
        raise DatumLifecycleContractError(
            "datum widget input must be a mapping"
        )

    missing = [
        key
        for key in DATUM_WIDGET_INPUT_REQUIRED_KEYS_V1
        if key != "emit" and key not in q_input_dead
    ]
    if missing:
        raise DatumLifecycleContractError(
            f"datum widget input missing required keys: {missing}"
        )

    out = dict(q_input_dead)

    try:
        assert_dead_json(
            out,
            path="datum_widget_input",
        )
    except DeadJSONError as exc:
        raise DatumLifecycleContractError(str(exc)) from exc

    return out


def normalize_q_result_v1(
    result: Any,
) -> Dict[str, Any]:
    if not isinstance(result, Mapping):
        raise DatumLifecycleContractError(
            "datum widget must return a mapping; "
            f"got {type(result).__name__}"
        )

    out = dict(result)
    status = str(out.get("status") or "").strip().lower()

    if status not in set(DATUM_WIDGET_RESULT_STATUSES_V1):
        raise DatumLifecycleContractError(
            f"datum widget returned invalid status {status!r}; "
            f"expected one of "
            f"{list(DATUM_WIDGET_RESULT_STATUSES_V1)}"
        )

    out["status"] = status

    default_message_level = (
        "success"
        if status == Q_STATUS_DONE
        else "error"
        if status == Q_STATUS_BLOCKED
        else "info"
    )

    raw_messages = (
        out.get("messages")
        if "messages" in out
        else out.get("message")
    )
    messages = _messages_v1(
        raw_messages,
        default_level=default_message_level,
    )

    out["messages"] = [
        dict(x)
        for x in messages
    ]
    out["message"] = _primary_message_v1(
        out["messages"],
        default_level=default_message_level,
    )

    state = out.get("state")
    if state is None:
        state = {}
    if not isinstance(state, Mapping):
        raise DatumLifecycleContractError(
            "datum widget result.state must be a mapping/dict"
        )
    out["state"] = dict(state)

    try:
        assert_dead_json(
            out["state"],
            path="datum_widget_result.state",
        )
        assert_dead_json(
            out["message"],
            path="datum_widget_result.message",
        )
        assert_dead_json(
            out["messages"],
            path="datum_widget_result.messages",
        )
    except DeadJSONError as exc:
        raise DatumLifecycleContractError(str(exc)) from exc

    if status == Q_STATUS_REEXPLODE:
        datum = out.get("datum")
        if not isinstance(datum, Mapping):
            raise DatumLifecycleContractError(
                "reexplode result must include datum: dict"
            )
        out["datum"] = dict(datum)
        try:
            assert_dead_json(
                out["datum"],
                path="datum_widget_result.datum",
            )
        except DeadJSONError as exc:
            raise DatumLifecycleContractError(str(exc)) from exc

    return out


__all__ = [
    "ensure_widget_input_contract_v1",
    "normalize_q_result_v1",
]