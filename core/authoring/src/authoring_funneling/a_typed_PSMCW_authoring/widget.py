"""Typed transitions execute inside the existing analytics operation."""
from copy import deepcopy
import json
from bindings2bindingsTM import BindingPlan, RuntimeValueError, normalize, validate
from epsilinesTM_serveragnostic.subapps.base import ServiceReadyWidget
from epsilinesTM_serveragnostic.subapps.analytics import analytica_signal_catcher
from _thinkprogram.thinkwidgetTM.types import Reexplode
from .contracts import RECIPE, PARAMETERS, SOURCES, CONTRACT

OUTPUT_STATE='strict_outputs_v1'
MOUTH_STATE='strict_mouths_v1'
CONFIG_STATE='strict_configuration_v1'

def _fail(code,path=(),expected=None,actual=None): raise RuntimeValueError(code,path,expected,actual)

class _Reads:
    def __init__(self, values, schemas): self._values=values;self._schemas=schemas
    def read(self,port):
        if port not in self._values: _fail('missing_input',('W','inputs',port))
        return deepcopy(self._values[port])
    def read_or(self,port,fallback):
        value=self.read(port)
        if value is None: validate(fallback,self._schemas[port],('W','inputs',port,'fallback'))
        return deepcopy(fallback) if value is None else value
    def require_value(self,port):
        value=self.read(port)
        if value is None: _fail('null_required',('W','inputs',port))
        return value

class _Outputs:
    def __init__(self, widget): self._widget=widget
    def _type(self,port,key=None):
        ports=self._widget._strict_schemas_v1['outputs']
        if port not in ports: _fail('unknown_port',('W','outputs',port))
        schema=ports[port]
        if key is None: return schema
        if schema.kind == 'promise':
            from bindings2bindingsTM import Str, Nullable, Map
            if key in ('ref', 'status'): return Str
            if key == 'result': return Nullable(schema.item)
            if key == 'schema': return Map(Str)
            if hasattr(schema.item, 'field_type'):
                try: return schema.item.field_type(key)
                except (KeyError, TypeError): pass
            _fail('unknown_output',('W','outputs',port,key))
        try: return schema.field_type(key)
        except (KeyError,TypeError): _fail('unknown_output',('W','outputs',port,key))

    def write(self,port,key,value):
        validate(value,self._type(port,key),('W','outputs',port,key))
        self._widget._strict_staged.setdefault(port,{})[key]=deepcopy(value)
    def write_port(self,port,values): self.write_many({port:values})
    def write_many(self,values):
        if type(values) is not dict: _fail('invalid_output_batch')
        for port,value in values.items(): validate(value,self._type(port),('W','outputs',port))
        copies={}
        for port,value in values.items():
            if hasattr(value, 'ref'):
                copies[port] = {'ref': str(value.ref), 'status': getattr(value, 'status', 'ongoing'), 'schema': self._type(port).item.to_json()}
            else:
                copies[port] = deepcopy(value)
        for port,value in copies.items(): self._widget._strict_staged[port]=value
    def read(self,port,key):
        self._type(port,key)
        accepted=self._widget._state.get(OUTPUT_STATE,{})
        if port not in accepted or key not in accepted[port]: _fail('no_accepted_output',('W','outputs',port,key))
        return deepcopy(accepted[port][key])
    def keep(self,port,key): self.write(port,key,self.read(port,key))
    def keep_port(self,port):
        t = self._type(port)
        if t.kind == 'dict':
            for key,field_t in t.fields: self.keep(port,key)
        else:
            self._widget._strict_staged[port] = deepcopy(self._widget._state.get(OUTPUT_STATE,{}).get(port,{}))

    def write_null(self,port,key): self.write(port,key,None)
    def read_or(self,port,key,fallback):
        value=self.read(port,key)
        if value is None: validate(fallback,self._type(port,key),('W','outputs',port,key,'fallback'))
        return deepcopy(fallback) if value is None else value
    def require_value(self,port,key):
        value=self.read(port,key)
        if value is None: _fail('null_required',('W','outputs',port,key))
        return value

class StrictServiceWidget(ServiceReadyWidget):
    def __setattr__(self,name,value):
        if not name.startswith('_'): _fail('undeclared_state_assignment',('W',name))
        super().__setattr__(name,value)
    def __delattr__(self,name):
        if not name.startswith('_'): _fail('state_deletion_unsupported',('W',name))
        super().__delattr__(name)
    def __getattr__(self,name):
        if not name.startswith('_'): raise AttributeError(name)
        return super().__getattr__(name)
    @property
    def outputs(self): return _Outputs(self)
    @property
    def mouth(self): return _Reads(self._state.get(MOUTH_STATE,{}),self._strict_schemas_v1['inputs'])
    @property
    def configuration(self): return deepcopy(self._state.get(CONFIG_STATE,{}))
    @staticmethod
    def replacement_shell(prior, *, title, micros):
        shell=deepcopy({k:v for k,v in prior.items() if k!='args'})
        shell['args']=deepcopy({k:v for k,v in prior.get('args',{}).items() if k not in ('__kernel',RECIPE,PARAMETERS)})
        shell.update(title=title,micros=deepcopy(micros))
        return shell
    def _capture_mouths(self,fill_data):
        args=fill_data['fill_shell'].get('args',{})
        try: bundle=json.loads(args[RECIPE])
        except (KeyError,ValueError,TypeError) as exc: raise RuntimeValueError('invalid_binding_bundle',('W','inputs')) from exc
        if type(bundle) is not dict or set(bundle)!={'version','inputs','sources','parameter_types'} or type(bundle['version']) is not int or bundle['version'] not in (1, 2) or any(type(bundle[k]) is not dict for k in ('inputs','sources','parameter_types')): _fail('invalid_binding_bundle')
        contracts=self.get_class_static_decorated_config()[CONTRACT]
        if bundle['inputs'].keys()!=contracts['inputs'].keys(): _fail('input_ports_mismatch')
        parameters=args.get(PARAMETERS,{})
        validate(parameters,{'kind':'dict','fields':bundle['parameter_types']},('P','parameters'))
        raw=args.get('__kernel',{}).get('past_wires',{}).get(SOURCES,[])
        rows=raw if type(raw) is list else [raw]
        index={}
        for row in rows:
            if type(row) is not dict: _fail('invalid_source_row',('P','sources'))
            index.setdefault((row.get('public_step_name'),row.get('key')),[]).append(row)
        values={'parameters':parameters}
        for alias,spec in bundle['sources'].items():
            if type(spec) is not dict or set(spec)!={'widget','port','step'} or not all(type(v) is str for v in spec.values()): _fail('invalid_source_spec',('P','sources',alias))
            selected=index.get((spec['step'],spec['widget']),[])
            if len(selected)!=1: _fail('source_unavailable',('P','sources',alias),1,len(selected))
            try: values[alias]=selected[0]['value']['state'][OUTPUT_STATE][spec['port']]
            except (KeyError,TypeError) as exc: raise RuntimeValueError('source_output_unavailable',('P','sources',alias)) from exc
        mouths={}
        for port,recipe in bundle['inputs'].items():
            plan=BindingPlan.from_json(recipe)
            if plan.target_type!=self._strict_schemas_v1['inputs'][port]: _fail('input_contract_changed',('W','inputs',port))
            mouths[port]=plan.evaluate(values)
        self._state[MOUTH_STATE]=mouths
        self._state[CONFIG_STATE]=deepcopy({k:v for k,v in args.items() if k not in ('__kernel',RECIPE,PARAMETERS)})
    def _run_analytica_operation_v1(self, *, trigger, fill_data, signal, invoke):
        before={k:self._state[k] for k in (OUTPUT_STATE,MOUTH_STATE,CONFIG_STATE) if k in self._state}
        def transition():
            self._strict_staged={}
            if trigger=='mount':
                self._state.pop(OUTPUT_STATE,None)
                self._capture_mouths(fill_data)
            result=invoke()
            if result is not True and not isinstance(result,Reexplode): _fail('strict_transition_outcome',('W','return'),'True or Reexplode',type(result).__name__)
            ports=self.get_class_static_decorated_config()[CONTRACT]['outputs']
            for port,schema in ports.items():
                if schema['kind'] == 'dict':
                    missing=set(schema['fields'])-self._strict_staged.get(port,{}).keys()
                    if missing: _fail('incomplete_outputs',('W','outputs',port),sorted(schema['fields']),sorted(self._strict_staged.get(port,{})))
                elif schema['kind'] == 'promise':
                    if port not in self._strict_staged: _fail('incomplete_outputs',('W','outputs',port),['promise'],[])
            self._state[OUTPUT_STATE]={port:deepcopy(self._strict_staged[port]) for port in ports}

            return result
        try: return super()._run_analytica_operation_v1(trigger=trigger,fill_data=fill_data,signal=signal,invoke=transition)
        except Exception:
            for k in (OUTPUT_STATE,MOUTH_STATE,CONFIG_STATE):
                self._state.pop(k,None)
            self._state.update(before)
            raise
        finally: self._strict_staged={}
