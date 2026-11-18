from copy import deepcopy
from .authoring import check_draft,validation_receipt,AuthoringError
PROFILE_ID='strict_ports.v1'
from .contracts import widget_catalogue

class TypedAuthoringProfile:
    def __init__(self,pack_id,*,profile_id,widget_ids):
        self.pack_id=pack_id;self.profile_id=profile_id;self.widget_ids=tuple(widget_ids)
    def describe(self):
        d={'profile_id':self.profile_id,'version':1,'pack_id':self.pack_id,
           'base_surfaces':{'W':'registered ThinkWidget','P':'think_program_v1','SM':'session metadata','C':'initial_parameter_overrides'},
           'capabilities':{'validate':True,'compile':True},
           'draft_schema':{'type':'object','required':['profile_id','W','P','SM','C'],'additionalProperties':False,
               'properties':{'profile_id':{'const':self.profile_id},'W':{'type':'array','items':{'type':'string'}},'P':{'type':'object'},'SM':{'type':'object'},'C':{'type':['object','null']}}}}
        d.update(refined_surfaces=['W','P'],passthrough_surfaces=['SM','C'],binding_operations=['value','ref','text','list','dict','map','item'],type_schemas={'version':1,'kinds':['str','int','float','bool','nullable','list','dict','map'],'exact_types':True,'closed_records':True},restrictions=['All selected widgets must have registered strict ports.','Output ports are closed records; every transition writes every key.','Sources select the latest earlier appearance; no same-step or future references.','Source caps cover mounting rows of the entire source step; inherited history costs remain.','Expressions contain inert JSON only; no callables, import paths, casts or arbitrary computation.','SM and C use ordinary validation/routing; no additional guarantees.','Platform admission and exhaustion policies remain ordinary framework policies.','Inputs must remain stable during synchronous evaluation.','Schema nesting is bounded to 64 and expression/JSON nesting to 128.','Parameter args obey ordinary P authoring-key restrictions.','Program, flow and logical widget IDs are nonempty literals without dollar signs or surrounding whitespace.','Typed parameter defaults must satisfy declarations before separately checking effective C.','Calling another wrapped lifecycle handler inside a handler is unsupported by ordinary analytics.','Changing profiles requires revalidation.'])
        d['schemas']={'input_ports':{'type':'object','additionalProperties':{'$ref':'#/$defs/type'}},'binding_expression':{'oneOf':[{'type':'object','required':['op',*keys],'additionalProperties':False,'properties':{'op':{'const':op},**{key:{} for key in keys}}} for op,keys in [('value',['value']),('ref',['source','path']),('text',['parts']),('list',['items']),('dict',['fields']),('map',['sequence','body']),('item',['path'])]]},'$defs':{'type':{'oneOf':[{'type':'object','required':['kind',*keys],'additionalProperties':False,'properties':{'kind':{'const':kind},**{key:({'$ref':'#/$defs/type'} if key=='item' else {'type':'object','additionalProperties':{'$ref':'#/$defs/type'}}) for key in keys}}} for kind,keys in [('str',[]),('int',[]),('float',[]),('bool',[]),('nullable',['item']),('list',['item']),('dict',['fields']),('map',['item'])]]}}}
        return d
    def describe_widgets(self):
        return widget_catalogue(self.widget_ids)
    def validate(self,draft): return validation_receipt(self,draft)
    def compile(self,draft):
        check_draft(draft,self.profile_id)
        draft = deepcopy(draft)
        pocket = draft['SM'].setdefault('app_pack_mould', {})
        if not isinstance(pocket, dict):
            raise AuthoringError('session_metadata', ['SM', 'app_pack_mould'])
        chosen = pocket.setdefault('app_pack', self.pack_id)
        if chosen != self.pack_id and not (isinstance(chosen, str) and chosen.startswith('$')):
            raise AuthoringError('pack_selection_mismatch', ['SM', 'app_pack_mould', 'app_pack'])
        pocket.setdefault('app_args', {})
        from _thinksessions.sesh_metadata.__sesh_meta_dynamic_augmentation_by_apps import SessionMetadataSurfaceRegistry
        pockets = getattr(SessionMetadataSurfaceRegistry, "_registered_pockets", None)
        if isinstance(pockets, dict) and "app_pack_mould" in pockets:
            enum_list = pockets["app_pack_mould"].get("fields", {}).get("app_pack", {}).get("enum")
            if isinstance(enum_list, list) and self.pack_id not in enum_list:
                enum_list.append(self.pack_id)
        from .program import compile_strict_tape
        export=compile_strict_tape(draft['P'],draft['SM'],draft['C'],profile_id=self.profile_id)
        if sorted(draft['W'])!=export['widget_ids']: raise AuthoringError('widget_selection_mismatch',['W'])
        if set(export['widget_ids'])-{w['widget_id'] for w in self.describe_widgets()}: raise AuthoringError('unsupported_widget',['W'])
        from .authoring import validate_launch_surfaces
        from _thinksessions.sesh_metadata.sesh_metadata_surface_puppeteering import bind_session_metadata_symbols_v1
        effective = validate_launch_surfaces(export['P'], export['SM'], export['C'])
        metadata = bind_session_metadata_symbols_v1(effective['session_metadata'])
        if metadata['app_pack_mould']['app_pack'] != self.pack_id:
            raise AuthoringError('pack_selection_mismatch', ['C'])
        return export

