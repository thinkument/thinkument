"""Attempt correlation and trusted Layer A vendor execution adapters."""
from dataclasses import dataclass
from threading import RLock, get_ident
from JSONfnchainTM import FlowInterceptor

@dataclass(frozen=True)
class VendorBinding:
    """Host-owned preparation/projection. Neither callable is selectable by JSON.

    prepare(args) returns kwargs for widget.execute_vendor_operation_v1, including
    prepared, client and maximum_units. Cost reconciliation is a host-side background
    responsibility. project maps VendorResult to the exact vocabulary result contract.
    """
    prepare: object
    project: object
    expected_vendor: str | None = None
    expected_operation: str | None = None

    def execute(self, ctx, args):
        interceptor = ctx.host_context.get('vendor_interceptor') if isinstance(ctx.host_context, dict) else getattr(ctx.host_context, 'vendor_interceptor', None)
        if callable(interceptor):
            op_id = ctx.host_context.get('operation_id', 'op') if isinstance(ctx.host_context, dict) else getattr(ctx.host_context, 'operation_id', 'op')
            call_key = str(op_id) + ':' + str(ctx.attempt_id)
            expected_op = self.expected_operation or 'vendor.llm.chat_completion'
            modality = expected_op.split('.')[1] if '.' in expected_op else 'general'
            inv_dict = {
                'operation': expected_op,
                'modality': modality,
                'args': dict(args or {}),
                'call_key': call_key,
                'vendor': self.expected_vendor,
                'context': {
                    'widget': ctx.host_context.get('widget_name') if isinstance(ctx.host_context, dict) else getattr(ctx.host_context, 'widget_name', None),
                    'node_path': getattr(ctx, 'node_path', None),
                    'attempt_id': ctx.attempt_id,
                },
            }
            return interceptor(inv_dict)

        options = dict(self.prepare(args))
        options['call_key'] = ctx.host_context['operation_id'] + ':' + ctx.attempt_id
        prepared = options.get('prepared')
        if self.expected_vendor is not None or self.expected_operation is not None:
            descriptor = getattr(prepared, 'descriptor', None)
            operation = getattr(getattr(prepared, 'prepared', None), 'operation_id', None)
            if (descriptor is None or descriptor.vendor != self.expected_vendor or
                    descriptor.operation != self.expected_operation or operation != self.expected_operation):
                raise ValueError('Prepared vendor call does not match its trusted route binding.')
        try:
            result = ctx.host_context['widget'].execute_vendor_operation_v1(**options)
            return self.project(result)
        finally:
            owner_thread = ctx.host_context.get('owner_thread') if isinstance(ctx.host_context, dict) else getattr(ctx.host_context, 'owner_thread', None)
            if owner_thread is not None and get_ident() != owner_thread:
                cleanup_hook = ctx.host_context.get('cleanup_hook') if isinstance(ctx.host_context, dict) else getattr(ctx.host_context, 'cleanup_hook', None)
                if callable(cleanup_hook):
                    try:
                        cleanup_hook()
                    except Exception:
                        pass
                else:
                    try:
                        from django.conf import settings
                        if settings.configured:
                            from django.db import connections
                            connections.close_all()
                    except Exception:
                        pass

class WidgetEconomicFlowInterceptor(FlowInterceptor):
    """Track settled attempts; Layer A owns reservations and authoritative usage.

    No second reservation is made here: execute_vendor_operation_v1 reserves
    before dispatch, settles before returning, and cleans up on failure.
    """
    def __init__(self, widget):
        self.widget = widget
        self._attempts = {}
        self._lock = RLock()

    @property
    def pending_attempts(self):
        with self._lock:
            return dict(self._attempts)

    def before_step(self, ctx, args):
        with self._lock:
            self._attempts[ctx.attempt_id] = ctx.node_path

    def after_step(self, ctx, args, result):
        with self._lock:
            self._attempts.pop(ctx.attempt_id, None)

    def on_step_error(self, ctx, args, error):
        with self._lock:
            self._attempts.pop(ctx.attempt_id, None)


class AsyncWorkFlowInterceptor(FlowInterceptor):
    """Lifecycle interceptor for asynchronous JSONic flows on QUEUE_ASYNCWORK.

    Emits live asyncwork.progress epsilines after every completed DAG step,
    maintains pending vendor attempt tracking for host-side economics,
    and isolates exceptions without failing fork-join settlement.
    """
    def __init__(self, widget=None, progress_callback=None, announcement_ref=None, total_steps=None, target_name="jsonfnchain.execute_transition"):
        self.widget = widget
        self.progress_callback = progress_callback
        self.announcement_ref = announcement_ref
        self.total_steps = total_steps
        self.target_name = target_name
        self._step_count = 0
        self._attempts = {}
        self._lock = RLock()

    @property
    def pending_attempts(self):
        with self._lock:
            return dict(self._attempts)

    def before_step(self, ctx, args):
        with self._lock:
            self._attempts[ctx.attempt_id] = ctx.node_path

    def after_step(self, ctx, args, result):
        with self._lock:
            self._step_count += 1
            current_step = self._step_count
            self._attempts.pop(ctx.attempt_id, None)

        step_name = str(ctx.node_path[-1]) if ctx.node_path else f"step_{current_step}"
        pct = None
        if self.total_steps and self.total_steps > 0:
            pct = min(100.0, round((current_step / self.total_steps) * 100.0, 1))

        if self.progress_callback is not None:
            try:
                self.progress_callback(
                    percent=pct,
                    step_name=step_name,
                    step_index=current_step,
                    total_steps=self.total_steps,
                    details={"node_path": list(ctx.node_path)},
                )
            except Exception:
                pass
        elif self.announcement_ref:
            try:
                from epsilinesTM_serveragnostic import ASYNCWORK_PROGRESS_CHANNEL, emit_eps_v1
                emit_eps_v1(
                    channel=ASYNCWORK_PROGRESS_CHANNEL,
                    payload={
                        "target": self.target_name,
                        "percent": pct,
                        "step_name": step_name,
                        "step_index": current_step,
                        "total_steps": self.total_steps,
                        "details": {"node_path": list(ctx.node_path)},
                    },
                    parent_ref=self.announcement_ref,
                )
            except Exception:
                pass

    def on_step_error(self, ctx, args, error):
        with self._lock:
            self._attempts.pop(ctx.attempt_id, None)


def create_gateway_vendor_binding(ops, operation_id, *, request, project):
    """Adapt a trusted GatewayOperations route to an approved JSON function.

    request(args) returns prepare_gateway_vendor_call keyword arguments. The
    gateway supplies the quoted maximum and authoritative read-only cost lookup.
    """
    if not isinstance(operation_id, str) or not operation_id:
        raise ValueError('A configured Vendor Hub operation ID is required.')
    try:
        operation = ops.get_operation(operation_id)
    except (KeyError, ValueError, TypeError, LookupError) as exc:
        raise ValueError(f'Vendor Hub operation {operation_id!r} is unavailable.') from exc
    if operation.get('eligibility') != 'configured':
        raise ValueError(f'Vendor Hub operation {operation_id!r} is unavailable.')

    def prepare(args):
        from gateway_lab.thinkwidget_economics import prepare_gateway_vendor_call
        call = prepare_gateway_vendor_call(ops, operation_id, **request(args))
        return {'prepared':call, 'client':ops, 'maximum_units':call.maximum_units}
    return VendorBinding(prepare, project, ops.api_provider_id, operation_id)
