from __future__ import annotations

from copy import deepcopy

import pytest

from epsilinesTM_serveragnostic.subapps.analytics import (
    AUDIT_ERROR_CHANNEL,
    AUDIT_INS_CHANNEL,
    AUDIT_OUTS_CHANNEL,
    AUDIT_VENDOR_USAGE_CHANNEL,
    AUDIT_WARNING_CHANNEL,
    AnalyticaOperationStreamValidatorV1,
    AnalyticaPoweredDatumLifecycleWidget,
    AnalyticaProtocolError,
    analytica_signal_catcher,
)


def _fill_data(
    *,
    fills=None,
    wires=None,
):
    return {
        "fill_shell": {
            "id": "probe",
            "args": {
                "policy": "strict",
                "__kernel": {
                    "past_wires": dict(
                        wires or {}
                    )
                },
            },
            "micros": [],
            "lifecycle": {},
        },
        "current_fills": dict(
            fills or {}
        ),
    }


def _event_emitter():
    events = []

    def emit(
        payload,
        *,
        name,
        record_in_session_queue=True,
        **kwargs,
    ):
        events.append(
            {
                "name": str(name),
                "payload": deepcopy(payload),
            }
        )

        # Match the framework's annotated emitter contract.
        return {}

    return events, emit


class ProbeWidget(
    AnalyticaPoweredDatumLifecycleWidget
):
    def _on_mount(
        self,
        position,
        fill_data,
        limits,
        stats,
    ):
        del position, fill_data, limits, stats
        self.mounted = True
        return True

    def _on_fill(
        self,
        signal,
        position,
        fill_data,
        limits,
        stats,
    ):
        del signal, position, fill_data, limits, stats

        with self.audit_vendor_usage_v1(
            vendor="vendor-a",
            operation="complete",
            request={
                "prompt_tokens": 10,
            },
            attributes={
                "model": "test",
            },
        ) as span:
            span.set_usage(
                {
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "cost_usd_micros": 4,
                }
            )

        self.audit_warning_v1(
            "pedagogical warning",
            details={
                "severity": "low",
            },
        )

        self.audit_event_v1(
            channel="audit-probe-fact",
            schema="tests.audit-probe-fact.v1",
            event="fact",
            body={
                "value": 42,
            },
        )

        self.items.append(2)
        self.answer = 42

        return True

    @analytica_signal_catcher(
        "refresh"
    )
    def refresh(
        self,
        signal,
        position,
        fill_data,
        limits,
        stats,
    ):
        del signal, position, fill_data, limits, stats

        self.refresh_count = (
            int(
                getattr(
                    self,
                    "refresh_count",
                    0,
                )
            )
            + 1
        )

        return None


class ErrorWidget(
    AnalyticaPoweredDatumLifecycleWidget
):
    def _on_fill(
        self,
        signal,
        position,
        fill_data,
        limits,
        stats,
    ):
        del signal, position, fill_data, limits, stats

        self.partial = {
            "written": True,
        }

        raise RuntimeError(
            "boom"
        )


def _new_probe():
    events, emit = _event_emitter()

    widget = ProbeWidget(
        q={
            "state": {},
        },
        emit=emit,
    )

    object.__setattr__(
        widget,
        "_events",
        events,
    )

    widget.items = [1]

    return widget


def _new_error():
    events, emit = _event_emitter()

    widget = ErrorWidget(
        q={
            "state": {},
        },
        emit=emit,
    )

    object.__setattr__(
        widget,
        "_events",
        events,
    )

    return widget


def test_fill_is_input_middle_events_terminal_output() -> None:
    widget = _new_probe()

    assert widget._on_fill(
        None,
        {},
        _fill_data(
            fills={
                "choice": "alpha",
            }
        ),
        {},
        {},
    ) is True

    channels = [
        row["name"]
        for row in widget._events
    ]

    assert channels == [
        AUDIT_INS_CHANNEL,
        AUDIT_VENDOR_USAGE_CHANNEL,
        AUDIT_WARNING_CHANNEL,
        "audit-probe-fact",
        AUDIT_OUTS_CHANNEL,
    ]

    envelopes = [
        row["payload"]
        for row in widget._events
    ]

    operation_ids = {
        row["operation_id"]
        for row in envelopes
    }

    assert len(
        operation_ids
    ) == 1

    assert [
        row["event_index"]
        for row in envelopes
    ] == [
        0,
        1,
        2,
        3,
        4,
    ]

    input_body = envelopes[0][
        "body"
    ]

    assert input_body == {
        "trigger": "fill",
        "authored_args": {
            "policy": "strict",
        },
        "history_wires": {},
        "current_fills": {
            "choice": "alpha",
        },
        "signal": None,
    }

    output = envelopes[-1][
        "body"
    ]

    assert output[
        "outcome"
    ] == {
        "kind": "satisfied",
    }

    # In-place mutation is captured.
    assert output[
        "state_writes"
    ][
        "items"
    ] == [
        1,
        2,
    ]

    # Direct assignment is captured.
    assert output[
        "state_writes"
    ][
        "answer"
    ] == 42

    validator = (
        AnalyticaOperationStreamValidatorV1()
    )

    for row in widget._events:
        validator.accept_v1(
            row["name"],
            row["payload"],
        )

    validator.assert_closed_v1()


def test_mount_is_automatically_audited() -> None:
    widget = _new_probe()

    widget._on_mount(
        {},
        _fill_data(),
        {},
        {},
    )

    assert [
        row["name"]
        for row in widget._events
    ] == [
        AUDIT_INS_CHANNEL,
        AUDIT_OUTS_CHANNEL,
    ]

    assert (
        widget._events[
            0
        ][
            "payload"
        ][
            "body"
        ][
            "trigger"
        ]
        == "mount"
    )

    assert (
        widget._events[
            -1
        ][
            "payload"
        ][
            "body"
        ][
            "state_writes"
        ][
            "mounted"
        ]
        is True
    )


def test_signal_operation_is_automatically_audited() -> None:
    widget = _new_probe()

    widget.refresh(
        {
            "kind": "refresh",
            "info": {
                "source": "test",
            },
        },
        {},
        _fill_data(),
        {},
        {},
    )

    assert [
        row["name"]
        for row in widget._events
    ] == [
        AUDIT_INS_CHANNEL,
        AUDIT_OUTS_CHANNEL,
    ]

    assert (
        widget._events[
            0
        ][
            "payload"
        ][
            "body"
        ][
            "trigger"
        ]
        == "signal:refresh"
    )

    assert (
        widget._events[
            -1
        ][
            "payload"
        ][
            "body"
        ][
            "state_writes"
        ][
            "refresh_count"
        ]
        == 1
    )


def test_exception_produces_error_and_never_output() -> None:
    widget = _new_error()

    with pytest.raises(
        RuntimeError,
        match="boom",
    ):
        widget._on_fill(
            None,
            {},
            _fill_data(),
            {},
            {},
        )

    assert [
        row["name"]
        for row in widget._events
    ] == [
        AUDIT_INS_CHANNEL,
        AUDIT_ERROR_CHANNEL,
    ]

    assert [
        row["payload"][
            "event_index"
        ]
        for row in widget._events
    ] == [
        0,
        1,
    ]

    assert (
        widget._events[
            -1
        ][
            "payload"
        ][
            "body"
        ][
            "message"
        ]
        == "boom"
    )


def test_unpersisted_live_epsilon_cannot_impersonate_analytica() -> None:
    widget = _new_probe()

    with pytest.raises(
        AnalyticaProtocolError,
    ):
        widget.emit_live_unpersisted_v1(
            "audit-not-allowed-here",
            {
                "x": 1,
            },
        )