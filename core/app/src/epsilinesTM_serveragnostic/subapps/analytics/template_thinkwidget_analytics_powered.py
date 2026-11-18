from __future__ import annotations

"""Analytics-powered ThinkWidget mould.

Subclass this instead of ``DatumLifecycleWidget``.

Normal mount/fill methods are wrapped automatically. Signals use
``@analytica_signal_catcher(...)`` instead of the lower-level signal decorator.

One lifecycle invocation therefore becomes:

    audit-ins
    [audit-vendor-usage | audit-warning | custom audit-*]*
    audit-outs | audit-error

Public semantic widget state is the state owned by
``DatumLifecycleWidget._state``. The mould snapshots that state before and
after execution, so state capture does not depend on a particular state-writing
helper and covers direct assignment, deletion, and in-place mutation.
"""

from copy import deepcopy
from functools import wraps
import json
from time import perf_counter_ns
from typing import Any, Callable, Dict, Mapping
from uuid import uuid4

from _thinkprogram._iomicrosTM.tiny_helpers import assert_dead_json
from _thinkprogram.thinkwidgetTM.base import DatumLifecycleWidget
from _thinkprogram.thinkwidgetTM.decorators import (
    signal_catcher as _framework_signal_catcher,
)
from _thinkprogram.thinkwidgetTM.types import Reexplode

from .msg_emission_channels import (
    AUDIT_ERROR_CHANNEL,
    AUDIT_ERROR_SCHEMA_V1,
    AUDIT_INS_CHANNEL,
    AUDIT_INS_SCHEMA_V1,
    AUDIT_OUTS_CHANNEL,
    AUDIT_OUTS_SCHEMA_V1,
    AUDIT_VENDOR_USAGE_CHANNEL,
    AUDIT_VENDOR_USAGE_SCHEMA_V1,
    AUDIT_WARNING_CHANNEL,
    AUDIT_WARNING_SCHEMA_V1,
    AnalyticaProtocolError,
    analytica_envelope_v1,
    is_analytica_channel_v1,
)


def _dead_json_copy(
    value: Any,
    *,
    path: str,
) -> Any:
    out = deepcopy(value)
    assert_dead_json(out, path=path)
    return out


def _canonical_dead_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _authored_args_v1(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    raw = dict(fill_shell or {}).get("args")
    args = (
        dict(raw or {})
        if isinstance(raw, Mapping)
        else {}
    )
    args.pop("__kernel", None)
    return _dead_json_copy(
        args,
        path="analytica.input.authored_args",
    )


def _history_wires_v1(
    fill_shell: Mapping[str, Any],
) -> Dict[str, Any]:
    """Normalize every wire to ``wire_name -> list[prior public state]``."""

    raw_args = dict(fill_shell or {}).get("args")
    args = (
        dict(raw_args)
        if isinstance(raw_args, Mapping)
        else {}
    )
    raw_kernel = args.get("__kernel")
    kernel = (
        dict(raw_kernel)
        if isinstance(raw_kernel, Mapping)
        else {}
    )
    raw_wires = kernel.get("past_wires")
    wires = (
        dict(raw_wires)
        if isinstance(raw_wires, Mapping)
        else {}
    )

    out: Dict[str, Any] = {}
    for wire_name in sorted(wires):
        raw = wires[wire_name]

        if raw is None:
            rows = []
        elif isinstance(raw, Mapping):
            rows = [dict(raw)]
        elif isinstance(raw, list):
            if not all(
                isinstance(row, Mapping)
                for row in raw
            ):
                raise AnalyticaProtocolError(
                    f"history wire {wire_name!r} "
                    "must contain mapping rows"
                )
            rows = [
                dict(row)
                for row in raw
            ]
        else:
            raise AnalyticaProtocolError(
                f"history wire {wire_name!r} "
                "must be a mapping or list"
            )

        states: list[Dict[str, Any]] = []
        for row in rows:
            value = row.get("value")
            if not isinstance(value, Mapping):
                raise AnalyticaProtocolError(
                    f"history wire {wire_name!r} "
                    "row.value must be a mapping"
                )

            state = value.get("state")
            if not isinstance(state, Mapping):
                raise AnalyticaProtocolError(
                    f"history wire {wire_name!r} "
                    "row.value.state must be a mapping"
                )

            states.append(
                _dead_json_copy(
                    dict(state),
                    path=(
                        "analytica.input.history_wires."
                        f"{wire_name}"
                    ),
                )
            )

        out[str(wire_name)] = states

    return out


def _public_state_v1(
    widget: DatumLifecycleWidget,
) -> Dict[str, Any]:
    """Snapshot framework-owned public semantic widget state.

    ``DatumLifecycleWidget`` routes public attribute assignment through
    ``__setattr__`` into its private ``_state`` mapping. Reading ``vars(widget)``
    would therefore inspect implementation attributes rather than the actual
    public state exposed by the widget.

    Snapshotting ``_state`` also deliberately deep-copies values before the
    lifecycle executes, which makes later in-place mutations detectable.
    """

    try:
        raw_state = object.__getattribute__(
            widget,
            "_state",
        )
    except AttributeError as exc:
        raise AnalyticaProtocolError(
            "Analytica requires an initialized "
            "DatumLifecycleWidget; widget._state is missing"
        ) from exc

    if not isinstance(raw_state, Mapping):
        raise AnalyticaProtocolError(
            "DatumLifecycleWidget._state must be a mapping; "
            f"got {type(raw_state).__name__}"
        )

    out: Dict[str, Any] = {}

    for raw_name, value in raw_state.items():
        if not isinstance(raw_name, str):
            raise AnalyticaProtocolError(
                "DatumLifecycleWidget._state keys must be strings; "
                f"got {type(raw_name).__name__}"
            )

        out[raw_name] = _dead_json_copy(
            value,
            path=(
                "analytica.public_state."
                f"{raw_name}"
            ),
        )

    return out


def _public_state_delta_v1(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> Dict[str, Any]:
    writes: Dict[str, Any] = {}

    for key in sorted(after):
        if (
            key not in before
            or _canonical_dead_json(before[key])
            != _canonical_dead_json(after[key])
        ):
            writes[key] = deepcopy(after[key])

    deleted = sorted(
        key
        for key in before
        if key not in after
    )

    return {
        "state_writes": writes,
        "state_deleted": deleted,
    }


def _python_type_v1(value: Any) -> str:
    cls = type(value)
    return (
        f"{cls.__module__}."
        f"{cls.__qualname__}"
    )


def _outcome_v1(value: Any) -> Dict[str, Any]:
    if isinstance(value, Reexplode):
        return {
            "kind": "reexplode",
        }

    if value is True:
        return {
            "kind": "satisfied",
        }

    if value is False:
        return {
            "kind": "unsatisfied",
        }

    if value is None:
        return {
            "kind": "none",
        }

    out: Dict[str, Any] = {
        "kind": "other",
        "python_type": _python_type_v1(
            value
        ),
    }

    try:
        out["value"] = _dead_json_copy(
            value,
            path="analytica.output.other_return",
        )
    except Exception:
        out["representation"] = repr(value)

    return out


def _exception_details_v1(
    exc: Exception,
) -> Any:
    for attr in (
        "details",
        "receipt",
    ):
        if not hasattr(
            exc,
            attr,
        ):
            continue

        raw = getattr(
            exc,
            attr,
        )

        if raw is None:
            continue

        try:
            return _dead_json_copy(
                raw,
                path=f"analytica.error.{attr}",
            )
        except Exception:
            return {
                "python_type": _python_type_v1(
                    raw
                ),
                "representation": repr(raw),
            }

    return None


class _VendorUsageSpanV1:
    def __init__(
        self,
        widget: "AnalyticaPoweredDatumLifecycleWidget",
        *,
        vendor: str,
        operation: str,
        request: Mapping[str, Any] | None,
        attributes: Mapping[str, Any] | None,
    ) -> None:
        self._widget = widget
        self._vendor = str(
            vendor
        ).strip()
        self._operation = str(
            operation
        ).strip()

        if not self._vendor:
            raise ValueError(
                "vendor must be non-empty"
            )

        if not self._operation:
            raise ValueError(
                "operation must be non-empty"
            )

        self._request = (
            None
            if request is None
            else _dead_json_copy(
                dict(request),
                path="analytica.vendor.request",
            )
        )

        self._attributes = (
            None
            if attributes is None
            else _dead_json_copy(
                dict(attributes),
                path="analytica.vendor.attributes",
            )
        )

        self._usage: Dict[str, Any] | None = None
        self._started_ns: int | None = None

    @property
    def operation_id(self) -> str:
        """Return the ID of the enclosing Analytica widget operation."""
        operation = self._widget._require_analytica_operation_v1()
        return str(operation["operation_id"])

    def set_usage(
        self,
        usage: Mapping[str, Any] | None,
    ) -> None:
        self._usage = (
            None
            if usage is None
            else _dead_json_copy(
                dict(usage),
                path="analytica.vendor.usage",
            )
        )

    def __enter__(
        self,
    ) -> "_VendorUsageSpanV1":
        self._widget._require_analytica_operation_v1()
        self._started_ns = (
            perf_counter_ns()
        )
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> bool:
        del traceback

        started = (
            self._started_ns
            if self._started_ns is not None
            else perf_counter_ns()
        )

        elapsed_ms = (
            perf_counter_ns() - started
        ) / 1_000_000.0

        error = None
        status = "success"

        if exc is not None:
            status = "error"
            error = {
                "message": str(exc),
                "exception_type": (
                    (
                        f"{exc_type.__module__}."
                        f"{exc_type.__qualname__}"
                    )
                    if exc_type is not None
                    else _python_type_v1(exc)
                ),
            }

        self._widget._emit_analytica_v1(
            channel=AUDIT_VENDOR_USAGE_CHANNEL,
            schema=AUDIT_VENDOR_USAGE_SCHEMA_V1,
            event="vendor_usage",
            body={
                "vendor": self._vendor,
                "operation": self._operation,
                "status": status,
                "elapsed_ms": elapsed_ms,
                "request": deepcopy(
                    self._request
                ),
                "usage": deepcopy(
                    self._usage
                ),
                "attributes": deepcopy(
                    self._attributes
                ),
                "error": error,
            },
            terminal=False,
        )

        return False


class AnalyticaPoweredDatumLifecycleWidget(
    DatumLifecycleWidget
):
    """DatumLifecycleWidget with automatic operation audit envelopes."""

    def __init_subclass__(
        cls,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(
            **kwargs
        )

        mount = cls.__dict__.get(
            "_on_mount"
        )

        if (
            callable(mount)
            and not getattr(
                mount,
                "__analytica_wrapped__",
                False,
            )
        ):

            @wraps(mount)
            def wrapped_mount(
                self,
                position,
                fill_data,
                limits,
                stats,
            ):
                return self._run_analytica_operation_v1(
                    trigger="mount",
                    fill_data=fill_data,
                    signal=None,
                    invoke=lambda: mount(
                        self,
                        position,
                        fill_data,
                        limits,
                        stats,
                    ),
                )

            wrapped_mount.__analytica_wrapped__ = True

            setattr(
                cls,
                "_on_mount",
                wrapped_mount,
            )

        fill = cls.__dict__.get(
            "_on_fill"
        )

        if (
            callable(fill)
            and not getattr(
                fill,
                "__analytica_wrapped__",
                False,
            )
        ):

            @wraps(fill)
            def wrapped_fill(
                self,
                signal,
                position,
                fill_data,
                limits,
                stats,
            ):
                return self._run_analytica_operation_v1(
                    trigger="fill",
                    fill_data=fill_data,
                    signal=signal,
                    invoke=lambda: fill(
                        self,
                        signal,
                        position,
                        fill_data,
                        limits,
                        stats,
                    ),
                )

            wrapped_fill.__analytica_wrapped__ = True

            setattr(
                cls,
                "_on_fill",
                wrapped_fill,
            )

    def _widget_class_v1(
        self,
    ) -> str:
        cls = type(self)
        return (
            f"{cls.__module__}:"
            f"{cls.__qualname__}"
        )

    def _require_analytica_operation_v1(
        self,
    ) -> Dict[str, Any]:
        raw = getattr(
            self,
            "_analytica_operation_v1",
            None,
        )

        if not isinstance(
            raw,
            dict,
        ):
            raise AnalyticaProtocolError(
                "Analytica event may only be emitted while "
                "a widget lifecycle operation is active"
            )

        if raw.get(
            "terminal"
        ):
            raise AnalyticaProtocolError(
                "Analytica event may not be emitted "
                "after terminal"
            )

        return raw

    def _emit_analytica_v1(
        self,
        *,
        channel: str,
        schema: str,
        event: str,
        body: Mapping[str, Any],
        terminal: bool,
    ) -> Dict[str, Any]:
        operation = (
            self._require_analytica_operation_v1()
        )

        index = int(
            operation["next_index"]
        )

        envelope = analytica_envelope_v1(
            channel=channel,
            schema=schema,
            event=event,
            operation_id=str(
                operation["operation_id"]
            ),
            event_index=index,
            widget_class=self._widget_class_v1(),
            body=body,
            published_widget_version_id=getattr(
                type(self), "_published_widget_version_id_v1", None
            ),
            publisher_user_id=getattr(
                type(self), "_published_widget_publisher_user_id_v1", None
            ),
        )

        try:
            self._emit(
                deepcopy(envelope),
                name=str(channel),
                record_in_session_queue=False,
            )
        except TypeError:
            self._emit(
                deepcopy(envelope),
                name=str(channel),
            )

        operation["next_index"] = (
            index + 1
        )

        if terminal:
            operation["terminal"] = True

        return deepcopy(
            envelope
        )

    def _run_analytica_operation_v1(
        self,
        *,
        trigger: str,
        fill_data: Mapping[str, Any],
        signal: Any,
        invoke: Callable[[], Any],
    ) -> Any:
        if isinstance(
            getattr(
                self,
                "_analytica_operation_v1",
                None,
            ),
            dict,
        ):
            raise AnalyticaProtocolError(
                "nested widget lifecycle operations "
                "are illegal"
            )

        if not isinstance(
            fill_data,
            Mapping,
        ):
            raise AnalyticaProtocolError(
                "fill_data must be a mapping"
            )

        fill_shell = fill_data.get(
            "fill_shell"
        )

        if not isinstance(
            fill_shell,
            Mapping,
        ):
            raise AnalyticaProtocolError(
                "fill_data.fill_shell must be a mapping"
            )

        raw_fills = fill_data.get(
            "current_fills"
        )

        current_fills = (
            {}
            if raw_fills is None
            else deepcopy(
                dict(raw_fills)
            )
            if isinstance(
                raw_fills,
                Mapping,
            )
            else None
        )

        if current_fills is None:
            raise AnalyticaProtocolError(
                "fill_data.current_fills must be "
                "a mapping or null"
            )

        input_body = {
            "trigger": str(trigger),
            "authored_args": _authored_args_v1(
                fill_shell
            ),
            "history_wires": _history_wires_v1(
                fill_shell
            ),
            "current_fills": _dead_json_copy(
                current_fills,
                path="analytica.input.current_fills",
            ),
            "signal": (
                None
                if signal is None
                else _dead_json_copy(
                    signal,
                    path="analytica.input.signal",
                )
            ),
        }

        # Snapshot the real framework-owned semantic state before execution.
        # This deep copy is what lets the output delta see later in-place
        # mutations such as self.items.append(...).
        before = _public_state_v1(
            self
        )

        operation = {
            "operation_id": uuid4().hex,
            "next_index": 0,
            "terminal": False,
            "input_emitted": False,
        }

        self._analytica_operation_v1 = (
            operation
        )

        try:
            self._emit_analytica_v1(
                channel=AUDIT_INS_CHANNEL,
                schema=AUDIT_INS_SCHEMA_V1,
                event="input",
                body=input_body,
                terminal=False,
            )

            operation["input_emitted"] = True

            result = invoke()

            # Snapshot `_state` again after lifecycle execution and derive the
            # externally meaningful public-state delta.
            after = _public_state_v1(
                self
            )

            delta = (
                _public_state_delta_v1(
                    before,
                    after,
                )
            )

            self._emit_analytica_v1(
                channel=AUDIT_OUTS_CHANNEL,
                schema=AUDIT_OUTS_SCHEMA_V1,
                event="output",
                body={
                    "outcome": _outcome_v1(
                        result
                    ),
                    **delta,
                },
                terminal=True,
            )

            return result

        except Exception as exc:
            if (
                operation.get(
                    "input_emitted"
                )
                and not operation.get(
                    "terminal"
                )
            ):
                try:
                    self._emit_analytica_v1(
                        channel=AUDIT_ERROR_CHANNEL,
                        schema=AUDIT_ERROR_SCHEMA_V1,
                        event="error",
                        body={
                            "message": str(exc),
                            "exception_type": (
                                _python_type_v1(
                                    exc
                                )
                            ),
                            "details": (
                                _exception_details_v1(
                                    exc
                                )
                            ),
                        },
                        terminal=True,
                    )
                except Exception as audit_exc:
                    raise audit_exc from exc

            raise

        finally:
            self._analytica_operation_v1 = None

    def audit_vendor_usage_v1(
        self,
        *,
        vendor: str,
        operation: str,
        request: Mapping[str, Any] | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> _VendorUsageSpanV1:
        """Time one external/vendor operation inside the current lifecycle."""

        return _VendorUsageSpanV1(
            self,
            vendor=vendor,
            operation=operation,
            request=request,
            attributes=attributes,
        )

    def audit_vendor_call_v1(
        self,
        *,
        vendor: str,
        operation: str,
        call: Callable[[], Any],
        request: Mapping[str, Any] | None = None,
        attributes: Mapping[str, Any] | None = None,
        usage_from: (
            Callable[
                [Any],
                Mapping[str, Any] | None,
            ]
            | None
        ) = None,
    ) -> Any:
        """Call and time one synchronous vendor function."""

        if not callable(
            call
        ):
            raise TypeError(
                "call must be callable"
            )

        with self.audit_vendor_usage_v1(
            vendor=vendor,
            operation=operation,
            request=request,
            attributes=attributes,
        ) as span:
            result = call()

            if usage_from is not None:
                span.set_usage(
                    usage_from(result)
                )

            return result

    def audit_warning_v1(
        self,
        message: str,
        *,
        details: Any = None,
    ) -> Dict[str, Any]:
        return self._emit_analytica_v1(
            channel=AUDIT_WARNING_CHANNEL,
            schema=AUDIT_WARNING_SCHEMA_V1,
            event="warning",
            body={
                "message": str(message),
                "details": _dead_json_copy(
                    details,
                    path="analytica.warning.details",
                ),
            },
            terminal=False,
        )

    def audit_event_v1(
        self,
        *,
        channel: str,
        schema: str,
        event: str,
        body: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Emit one explicitly schematized custom Analytica fact."""

        normalized = str(
            channel
        ).strip()

        if normalized in {
            AUDIT_INS_CHANNEL,
            AUDIT_OUTS_CHANNEL,
            AUDIT_ERROR_CHANNEL,
            AUDIT_VENDOR_USAGE_CHANNEL,
            AUDIT_WARNING_CHANNEL,
        }:
            raise AnalyticaProtocolError(
                "built-in Analytica channels "
                "have dedicated APIs"
            )

        if not is_analytica_channel_v1(normalized):
            raise AnalyticaProtocolError(
                f"{normalized!r} is not an analytica channel"
            )

        return self._emit_analytica_v1(
            channel=normalized,
            schema=str(schema),
            event=str(event),
            body=body,
            terminal=False,
        )

    def emit_eps_v1(
        self,
        channel: str,
        payload: Any,
        *,
        ref: str | None = None,
        parent_ref: str | None = None,
        meta: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Emit run-level epsilon on any channel registered in eps_sheet, returning confirmed ref."""
        import uuid
        from epsilinesTM_serveragnostic import require_registered_eps_channel_v1, MODE_PERSISTENCE

        name = str(channel).strip()
        if not name:
            raise ValueError("channel must be non-empty")

        spec = require_registered_eps_channel_v1(name)
        validated = spec.validate(payload)

        assigned_ref = ref
        if assigned_ref is None and spec.mode == MODE_PERSISTENCE:
            assigned_ref = str(uuid.uuid4())

        extra_meta = dict(meta or {})
        if assigned_ref is not None:
            extra_meta["ref"] = assigned_ref
        if parent_ref is not None:
            extra_meta["parent_ref"] = parent_ref

        clean_payload = (
            _dead_json_copy(
                dict(validated),
                path="eps.payload",
            )
            if isinstance(validated, Mapping)
            else {
                "content": _dead_json_copy(
                    validated,
                    path="eps.payload",
                )
            }
        )

        emit_kwargs = dict(kwargs)
        if assigned_ref is not None:
            emit_kwargs["event_id"] = assigned_ref
            emit_kwargs["ref"] = assigned_ref
        if parent_ref is not None:
            emit_kwargs["span_id"] = parent_ref
            emit_kwargs["parent_ref"] = parent_ref
        if extra_meta:
            emit_kwargs["meta"] = extra_meta

        try:
            self._emit(
                clean_payload,
                name=name,
                record_in_session_queue=False,
                **emit_kwargs,
            )
        except TypeError:
            self._emit(
                clean_payload,
                name=name,
                record_in_session_queue=False,
            )

        return assigned_ref or ""

    def read_eps_v1(
        self,
        channel: str,
        *,
        ref: str | None = None,
        parent_ref: str | None = None,
        ref_prefix: str | None = None,
        ref_regex: str | None = None,
        meta: Mapping[str, Any] | None = None,
        all_in_run: bool = False,
        all_for_owner: bool = False,
        run_id: str | None = None,
        owner_id: str | None = None,
        app: str | None = None,
        after_seq: int = 0,
        limit: int = 100,
        caller_role: str | None = None,
        for_owner: bool = False,
        allow_all: bool = False,
        **kwargs: Any,
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """Targeted or batch read of persisted epsilon rows for this widget execution."""
        from epsilinesTM_serveragnostic import read_eps_v1 as _core_read_eps_v1

        effective_run_id = run_id
        if effective_run_id is None and not all_for_owner:
            effective_run_id = getattr(self, "run_id", None) or getattr(self, "_run_id", None)
            if effective_run_id is None and hasattr(self, "_context"):
                effective_run_id = getattr(self._context, "run_id", None)

        effective_role = caller_role
        if effective_role is None and hasattr(self, "_role"):
            effective_role = getattr(self, "_role", None)

        return _core_read_eps_v1(
            channel,
            ref=ref,
            parent_ref=parent_ref,
            ref_prefix=ref_prefix,
            ref_regex=ref_regex,
            meta=meta,
            all_in_run=all_in_run,
            all_for_owner=all_for_owner,
            run_id=effective_run_id,
            owner_id=owner_id,
            app=app,
            after_seq=after_seq,
            limit=limit,
            caller_role=effective_role,
            for_owner=for_owner,
            allow_all=allow_all,
            **kwargs,
        )

    def audit_event_v1(
        self,
        *,
        channel: str,
        schema: str,
        event: str,
        body: Mapping[str, Any],
        ref: str | None = None,
        parent_ref: str | None = None,
        meta: Mapping[str, Any] | None = None,
    ) -> str:
        """Modernized convenience compiling directly into emit_eps_v1."""
        operation = self._require_analytica_operation_v1()
        index = int(operation["next_index"])
        operation["next_index"] = index + 1

        envelope = analytica_envelope_v1(
            channel=channel,
            schema=schema,
            event=event,
            operation_id=str(operation["operation_id"]),
            event_index=index,
            widget_class=self._widget_class_v1(),
            body=body,
            published_widget_version_id=getattr(
                type(self), "_published_widget_version_id_v1", None
            ),
            publisher_user_id=getattr(
                type(self), "_published_widget_publisher_user_id_v1", None
            ),
        )
        return self.emit_eps_v1(
            channel,
            envelope,
            ref=ref,
            parent_ref=parent_ref,
            meta=meta,
        )

    def emit_live_unpersisted_v1(
        self,
        message_type: str,
        content: Any,
        **kwargs: Any,
    ) -> str:
        """Convenience compiling directly into emit_eps_v1."""
        return self.emit_eps_v1(message_type, content, **kwargs)


def analytica_signal_catcher(
    catcher_name: str,
):
    """Analytics-aware form of the normal ThinkWidget signal decorator."""

    name = str(
        catcher_name
    ).strip()

    if not name:
        raise ValueError(
            "signal catcher name must be non-empty"
        )

    def decorate(fn):
        @wraps(fn)
        def wrapped(
            self,
            signal,
            position,
            fill_data,
            limits,
            stats,
        ):
            return self._run_analytica_operation_v1(
                trigger=f"signal:{name}",
                fill_data=fill_data,
                signal=signal,
                invoke=lambda: fn(
                    self,
                    signal,
                    position,
                    fill_data,
                    limits,
                    stats,
                ),
            )

        wrapped.__analytica_wrapped__ = True

        return _framework_signal_catcher(
            name
        )(wrapped)

    return decorate


__all__ = [
    "AnalyticaPoweredDatumLifecycleWidget",
    "analytica_signal_catcher",
]
