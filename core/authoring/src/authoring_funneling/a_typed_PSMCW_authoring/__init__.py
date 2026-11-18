"""Reusable authoring API. Runtime imports do not load the Higher-P compiler."""
from bindings2bindingsTM import (
    D, Str, Int, Float, Bool, Nullable, List, Dict, Map,
    compile_binding, BindingPlan, infer_expression_type,
    reconcile_common_schema, merge_dict_schemas,
    CompilationError, RuntimeValueError
)
from .contracts import strict_widget, prepare_strict_widget
from .widget import StrictServiceWidget,analytica_signal_catcher
from ._program_language import (
    LANG_TYPED_THINK_PROGRAM_V1,
    lower_typed_think_program_v1,
    register_typed_think_program_language_v1,
)

register_typed_think_program_language_v1()

__all__=[
    'D','Str','Int','Float','Bool','Nullable','List','Dict','Map',
    'compile_binding','BindingPlan','infer_expression_type',
    'reconcile_common_schema','merge_dict_schemas',
    'CompilationError','RuntimeValueError',
    'strict_widget','prepare_strict_widget','StrictServiceWidget','analytica_signal_catcher',
    'compile_strict_program','compile_strict_tape','TypedAuthoringProfile',
    'LANG_TYPED_THINK_PROGRAM_V1','lower_typed_think_program_v1',
    'register_typed_think_program_language_v1',
]

def __getattr__(name):
    if name in ('compile_strict_program','compile_strict_tape'):
        from . import program
        return getattr(program,name)
    if name=='TypedAuthoringProfile':
        from .profile import TypedAuthoringProfile
        return TypedAuthoringProfile
    if name=='AuthoringError':
        from .authoring import AuthoringError
        return AuthoringError
    raise AttributeError(name)
