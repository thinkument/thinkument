"""JSON transitions participate in the ordinary strict lifecycle transaction."""
from copy import deepcopy
from threading import RLock, get_ident
from JSONfnchainTM import execute_flow
from _thinkprogram.thinkwidgetTM.types import Reexplode
from ..a_typed_PSMCW_authoring.widget import StrictServiceWidget, MOUTH_STATE, OUTPUT_STATE
from .interceptor import WidgetEconomicFlowInterceptor

class JsonDefinedLibraryWidget(StrictServiceWidget):
    def _run_analytica_operation_v1(self, **kwargs):
        if '_json_telemetry_lock' not in self.__dict__:
            self._json_telemetry_lock = RLock()
        return super()._run_analytica_operation_v1(**kwargs)

    def _emit_analytica_v1(self, **kwargs):
        with self._json_telemetry_lock:
            return super()._emit_analytica_v1(**kwargs)

    def _build_root_scope(self, fill_data, signal_data, *, mount=False):
        return deepcopy({
            'mouth': self._state.get(MOUTH_STATE, {}),
            'prior_outputs': {} if mount else self._state.get(OUTPUT_STATE, {}),
            'signal': (signal_data or {}).get('info', signal_data or {}),
            'fills': (fill_data or {}).get('current_fills', {}),
            'config': self.configuration,
        })

    def _apply_outcome(self, result, fill_data):
        if type(result) is not dict or set(result) - {'done', 'reexplode', 'outputs', 'keep'}:
            raise ValueError('Invalid JSON widget outcome')
        if ('reexplode' in result) == (result.get('done') is True):
            raise ValueError('Outcome requires exactly one of done:true or reexplode')
        self.outputs.write_many(result.get('outputs', {}))
        keep = result.get('keep', [])
        if keep == '*': keep = [p for p in self._strict_schemas_v1['outputs'] if p not in result.get('outputs', {})]
        if type(keep) is not list or any(type(p) is not str for p in keep) or len(set(keep)) != len(keep):
            raise ValueError('keep must be * or unique output port names')
        if set(keep) & result.get('outputs', {}).keys(): raise ValueError('Cannot write and keep the same port')
        for port in keep: self.outputs.keep_port(port)
        if 'reexplode' not in result: return True
        shell = result['reexplode']
        if type(shell) is not dict or not {'title', 'micros'} <= shell.keys() or set(shell) - {'title','micros','pre_computed_fills','micro_placement'}:
            raise ValueError('Invalid reexplode fields')
        if type(shell['title']) is not str or type(shell['micros']) is not list:
            raise ValueError('Invalid reexplode title or micros')
        names = []
        for micro in shell['micros']:
            if type(micro) is not dict or not isinstance(micro.get('name'), str) or not micro['name'] or not isinstance(micro.get('type'), str):
                raise ValueError('Micros require name and type')
            names.append(micro['name'])
        if len(names) != len(set(names)):
            raise ValueError('Duplicate micro name')
        fills = shell.get('pre_computed_fills', {})
        if type(fills) is not dict or set(fills) - set(names):
            raise ValueError('Precomputed fills must target the replacement micros')
        replacement = self.replacement_shell(fill_data['fill_shell'], title=shell['title'], micros=shell['micros'])
        if 'micro_placement' in shell: replacement['paquete_micro_placement'] = shell['micro_placement']
        return Reexplode(next_fill_shell=replacement, pre_computed_fills=shell.get('pre_computed_fills', {}))

    def _reexplode_in_flight(self, fill_data, title):
        current_fill_shell = fill_data.get('fill_shell') or {}
        micros = current_fill_shell.get('micros') or []
        replacement = self.replacement_shell(current_fill_shell, title=title, micros=micros)
        return Reexplode(next_fill_shell=replacement)

    def _execute_transition(self, name, fill_data, signal_data):
        is_async = getattr(self, '_async_transitions', {}).get(name, False)
        if not is_async:
            plan = self._compiled_transitions[name]
            context = {'owner_thread': get_ident(), 'widget': self, 'vendor_bindings': self._vendor_bindings,
                       'operation_id': str(self._require_analytica_operation_v1()['operation_id'])}
            cleanup = getattr(self, '_cleanup_hook', None) or getattr(self, '_host_cleanup_hook', None)
            if callable(cleanup):
                context['cleanup_hook'] = cleanup
            result = execute_flow(plan, self._build_root_scope(fill_data, signal_data, mount=name=='mount'),
                                  vocab=self._vocab, interceptor=WidgetEconomicFlowInterceptor(self),
                                  host_context=context, max_concurrency=8)
            return self._apply_outcome(result, fill_data)

        # Asynchronous Flow Execution on QUEUE_ASYNCWORK:
        from authoring_w_persistence_async import submit_async_work_v1, get_async_work_handle_v1
        ref_key = f'_async_work_ref_{name}'
        active_ref = self._state.get(ref_key)

        if active_ref:
            handle = get_async_work_handle_v1(active_ref)
            if handle.is_done():
                outcome = handle.get_outcome()
                if outcome == 'success':
                    self._state.pop(ref_key, None)
                    result = handle.get_result()
                    return self._apply_outcome(result, fill_data)
                elif outcome in ('error', 'timeout'):
                    err = handle.get_error() or "Unknown error"
                    self._state.pop(ref_key, None)
                    raise RuntimeError(f"Async transition {name} failed: {err}")
                else:
                    latest = handle.get_latest_progress()
                    pct = latest.get('payload', {}).get('percent') if latest else None
                    title = f"Processing {name}... ({int(pct)}%)" if pct is not None else f"Processing {name}..."
                    return self._reexplode_in_flight(fill_data, title)
            else:
                latest = handle.get_latest_progress()
                pct = latest.get('payload', {}).get('percent') if latest else None
                title = f"Processing {name}... ({int(pct)}%)" if pct is not None else f"Processing {name}..."
                return self._reexplode_in_flight(fill_data, title)

        # Initial launch:
        root_scope = self._build_root_scope(fill_data, signal_data, mount=name=='mount')
        recipe_json = self._compiled_transitions[name].to_json()
        op_info = self._require_analytica_operation_v1()
        op_id = str(op_info['operation_id'])
        widget_id = getattr(self, '_published_widget_version_id_v1', self.__class__.__name__)

        vendor_meta = {}
        for b_name, b_inst in self._vendor_bindings.items():
            vendor_meta[b_name] = {
                'expected_vendor': b_inst.expected_vendor,
                'expected_operation': b_inst.expected_operation,
            }

        handle = submit_async_work_v1(
            target="jsonfnchain.execute_transition",
            kwargs={
                "recipe_json": recipe_json,
                "root_scope": root_scope,
                "operation_id": op_id,
                "widget_id": widget_id,
                "transition_name": name,
                "vendor_bindings": vendor_meta,
            },
            meta={
                "widget_id": widget_id,
                "transition": name,
                "operation_id": op_id,
            },
            initiator_widget=widget_id,
        )
        self._state[ref_key] = handle.ref

        # Write promise descriptors to any output ports declared with Promise, and keep existing ports
        for port_name, schema in self._strict_schemas_v1['outputs'].items():
            if getattr(schema, 'kind', None) == 'promise':
                self.outputs.write_many({port_name: {'ref': handle.ref, 'status': 'running'}})
            elif port_name in self._state.get(OUTPUT_STATE, {}):
                self.outputs.keep_port(port_name)

        return self._reexplode_in_flight(fill_data, f"Started {name}...")
