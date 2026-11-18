# tests/engine/test_app_table_invariants.py
import pytest

from _thinkengine._parsing.app_table_program_parser import parse_and_validate_app_table
from __exceptions.engine import AppTableParserValidatorError, FatalEngineError
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api


# def test_registry_step_fns_disallows_duplicate_by_default():
#     def fn(_state, **_kwargs):
#         return {}

#     StepFnregistry.register(name="test.registry.dup", fn=fn, overwrite=True)
#     with pytest.raises(ValueError):
#         StepFnregistry.register(name="test.registry.dup", fn=fn)


def test_manifest_rejects_non_dead_json_fn_args():
    def fn(_state, **_kwargs):
        return {}

    StepFnregistry.register(name="test.step.deadjson", fn=fn, overwrite=True, optional_args={"x"})

    manifest = [
        {
            "public_step_name": "S1",
            "step_fn": "test.step.deadjson",
            "fn_args": {"x": lambda: 1},  # callable is not dead JSON
        }
    ]
    with pytest.raises(AppTableParserValidatorError):
        parse_and_validate_app_table(manifest)


def test_create_VM_session_rejects_non_dead_json_initial_parameter_overrides():
    api = get_concrete_session_api()

    def fn(_state, **_kwargs):
        return {}

    StepFnregistry.register(name="test.step.globals", fn=fn, overwrite=True)

    manifest = [{"public_step_name": "S1", "step_fn": "test.step.globals", "fn_args": {}}]
    with pytest.raises(ValueError):
        api.create_VM_session(manifest=manifest, initial_parameter_overrides={"bad": object()}, get_map=False)


def test_engine_rejects_reserved_patch_keys():
    api = get_concrete_session_api()

    def bad_patch(_state, **_kwargs):
        # Step fns must not patch engine-owned keys like pending_multiframespec/form_fills/etc.
        return {"pending_multiframespec": {"oops": 1}}

    StepFnregistry.register(name="test.step.reserved", fn=bad_patch, overwrite=True)

    st = api.create_VM_session(
        manifest=[{"public_step_name": "S1", "step_fn": "test.step.reserved", "fn_args": {}}],
        initial_parameter_overrides={},
        get_map=False,
    )
    sid = st["session_id"]
    with pytest.raises(FatalEngineError):
        api.step_session(sid)


def test_engine_rejects_non_json_patch_values():
    api = get_concrete_session_api()

    def bad_patch(_state, **_kwargs):
        return {"x": object()}  # non-JSON

    StepFnregistry.register(name="test.step.nonjson", fn=bad_patch, overwrite=True)

    st = api.create_VM_session(
        manifest=[{"public_step_name": "S1", "step_fn": "test.step.nonjson", "fn_args": {}}],
        initial_parameter_overrides={},
        get_map=False,
    )
    sid = st["session_id"]
    with pytest.raises(FatalEngineError):
        api.step_session(sid)


def test_prefill_addressing_is_validated_even_when_prefill_value_validation_disabled():
    """
    The directive multiframespec_PREFILL_VALIDATE_VALUES controls *value* validation,
    but unknown datum ids / unknown micro keys must still fail fast.

    This prevents silent typos in prefills from leaking into later steps.
    """
    api = get_concrete_session_api()

    def emit_bad_prefill(_state, **_kwargs):
        patch = {"multiframespec_PREFILL_VALIDATE_VALUES": False}
        multiframespec = {
            "datums": [
                {"id": "KNOWN", "title": "Known", "micros": [{"name": "value", "type": "text", "required": True}]}
            ],
            "frames": [{"id": "F", "title": "F", "spans": []}],
            "fills": {"UNKNOWN": {"value": "oops"}},  # bad datum id
        }
        return patch, multiframespec

    StepFnregistry.register(name="test.step.bad_prefill_addressing", fn=emit_bad_prefill, overwrite=True)

    st = api.create_VM_session(
        manifest=[{"public_step_name": "S1", "step_fn": "test.step.bad_prefill_addressing", "fn_args": {}}],
        initial_parameter_overrides={},
        get_map=False,
    )
    sid = st["session_id"]

    with pytest.raises(FatalEngineError):
        api.step_session(sid)
