"""Higher P compiles explicitly into ordinary registered widget recipes."""
from copy import deepcopy
import json
from bindings2bindingsTM import normalize, compile_binding, validate, CompilationError, RuntimeValueError, D
from _thinkprogram.thinkprogramTM.api import bind_think_program_symbols_v1,lower_think_program_to_kernel_program_v1
from .authoring import fingerprint,validate_launch_surfaces,AuthoringError
from .contracts import RECIPE,PARAMETERS,SOURCES,widget_contract,widget_catalogue

from .profile import PROFILE_ID

def _portable(value):
    # A JSON string is an opaque ordinary arg; escaping every dollar protects
    # literals against recursive ordinary symbol resolution.
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).replace('$',r'\u0024')

def _binding_patch(base,patch,path):
    if type(base) is not dict or type(patch) is not dict: raise CompilationError('invalid_bindings',path)
    if (base.keys()|patch.keys())-{'sources','parameters','inputs'}: raise CompilationError('unknown_binding_field',path)
    return {key:{**base.get(key,{}),**patch.get(key,{})} for key in ('sources','parameters','inputs')}

def compile_strict_program(higher, *, prepared_json_widgets=()):
    p=deepcopy(higher)
    try: body=p['run']['program']; widgets=body['widgets']; flow=body['flow']; program_id=body['info']['id']
    except (KeyError,TypeError) as exc: raise CompilationError('invalid_program',('P',)) from exc
    if type(widgets) is not dict or type(flow) is not list: raise CompilationError('invalid_program_structure',('P',))
    def literal_id(value,path):
        if type(value) is not str or not value or value!=value.strip() or '$' in value:
            raise CompilationError('literal_topology_required',path,'nonempty literal ID without surrounding whitespace',value)
    literal_id(program_id,('P','info','id'))
    contracts={};bindings={}
    for logical,w in widgets.items():
        literal_id(logical,('P','widgets',logical))
        contracts[logical]=widget_contract(w['widget'], prepared_json_widgets=prepared_json_widgets)
        if {RECIPE,PARAMETERS}&w.get('args',{}).keys() or w.get('wires'): raise CompilationError('reserved_generated_fields',('P','widgets',logical))
        bindings[logical]=w.pop('bindings',{})
        w.setdefault('args',{})[RECIPE]='{}'
    prior={}
    for index,step in enumerate(flow):
        if type(step) is not dict: raise CompilationError('invalid_flow',('P','flow',index))
        literal_id(step.get('id'),('P','flow',index,'id'))
        overrides=step.setdefault('overrides',{})
        higher_overrides=overrides.pop('bindings',{})
        if type(higher_overrides) is not dict or set(higher_overrides)-set(step['widgets']): raise CompilationError('invalid_binding_override',('P','flow',index))
        if overrides.get('wires'): raise CompilationError('reserved_generated_fields',('P','flow',index,'wires'))
        for logical in step['widgets']:
            path=('P','flow',index,logical,'bindings')
            if logical not in contracts: raise CompilationError('unknown_widget',path)
            args=overrides.setdefault('args',{}).setdefault(logical,{})
            if {RECIPE,PARAMETERS}&args.keys(): raise CompilationError('reserved_generated_fields',path)
            b=_binding_patch(bindings[logical],higher_overrides.get(logical,{}),path)
            if set(b['inputs'])!=set(contracts[logical]['inputs']): raise CompilationError('input_ports_mismatch',(*path,'inputs'),sorted(contracts[logical]['inputs']),sorted(b['inputs']))
            source_types={};source_specs={};source_widgets=[];caps=[];used_sources=set()
            if 'parameters' in b['sources']: raise CompilationError('reserved_parameter_source',(*path,'sources'))
            for alias,s in b['sources'].items():
                if type(s) is not dict or set(s)!={'widget','port'}: raise CompilationError('invalid_source',(*path,'sources',alias))
                source=logical if s['widget']=={'self':'previous'} else s['widget']
                if type(source) is not str or source not in prior: raise CompilationError('source_not_earlier',(*path,'sources',alias))
                if s['port'] not in contracts[source]['outputs']: raise CompilationError('unknown_source_port',(*path,'sources',alias))
                out_schema = contracts[source]['outputs'][s['port']]
                # Law of Wire Typing Symmetry: Wires carrying Promise[T] expose T to downstream binding expressions
                source_types[alias] = out_schema['item'] if out_schema.get('kind') == 'promise' else out_schema
                source_specs[alias]={'widget':source,'port':s['port'],'step':prior[source]['step']}

                source_widgets.append(source);caps.append(prior[source]['cap'])
            parameters={};parameter_types={}
            for name,s in b['parameters'].items():
                if type(s) is not dict or set(s)!={'type','value'}: raise CompilationError('invalid_parameter',(*path,'parameters',name))
                parameter_types[name]=normalize(s['type']).to_json();parameters[name]=deepcopy(s['value'])
            source_types['parameters']={'kind':'dict','fields':parameter_types}
            recipes={}
            for port,t in contracts[logical]['inputs'].items():
                try:
                    plan=compile_binding(source_types,t,D.sugar(b['inputs'][port]))
                    recipes[port]=plan.to_json()
                    used_sources.update(name for name,path in plan.dependencies if name!='parameters')
                except CompilationError as exc:
                    exc.details['path']=[*path,'inputs',port,*exc.details['path']];raise
            source_specs={k:v for k,v in source_specs.items() if k in used_sources}
            source_widgets=list(dict.fromkeys(s['widget'] for s in source_specs.values()))
            caps=[prior[s]['cap'] for s in source_widgets]
            bundle={'version':1,'inputs':recipes,'sources':source_specs,'parameter_types':parameter_types}
            args[RECIPE]=_portable(bundle);args[PARAMETERS]=parameters
            if source_widgets:
                overrides.setdefault('wires',{})[logical]={SOURCES:{'from':list(dict.fromkeys(source_widgets)),'history':{'select':'latest','required':True,'max_results':max(caps)}}}
        # Every datum mounts before user dispatch. Mount records occur first and
        # materialize the selected appearance's current accepted lifecycle state.
        cap=len(step['widgets'])
        for logical in step['widgets']: prior[logical]={'step':f'{program_id}.{step["id"]}','cap':cap}
    # Lower through the public ordinary-P surface, then check effective typed
    # parameters after ordinary symbols/default puppeteering have resolved.
    _validate_parameters(p)
    lower_think_program_to_kernel_program_v1(p)
    return p

def _validate_parameters(p):
    run=bind_think_program_symbols_v1(p)
    body=run['program']
    for index,step in enumerate(body['flow']):
        for logical in step['widgets']:
            args={**body['widgets'][logical].get('args',{}),**step.get('overrides',{}).get('args',{}).get(logical,{})}
            bundle=json.loads(args[RECIPE])
            try: validate(args[PARAMETERS],{'kind':'dict','fields':bundle['parameter_types']},('P','flow',index,logical,'parameters'))
            except RuntimeValueError as exc: raise CompilationError(exc.details['code'],exc.details['path'],exc.details['expected'],exc.details['actual']) from exc

def compile_strict_tape(higher,SM=None,C=None,*,profile_id=PROFILE_ID,prepared_json_widgets=()):
    P=compile_strict_program(higher, prepared_json_widgets=prepared_json_widgets)
    SM=deepcopy(SM or {});C=deepcopy(C)
    effective=validate_launch_surfaces(P,SM,C)
    _validate_parameters(effective['program'])
    ids=sorted({w['widget'] for w in P['run']['program']['widgets'].values()})
    return {'profile_id':profile_id,'P':P,'SM':SM,'C':C,'widget_ids':ids,'contract_fingerprint':fingerprint({'profile_id':profile_id,'contracts':widget_catalogue(ids, prepared_json_widgets=prepared_json_widgets)})}
