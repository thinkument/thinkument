from __future__ import annotations

import unittest
from typing import Any, Dict, Optional

from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry, register_step_fn
from __exceptions.engine import (
    AppTableParserValidatorError,
    ProgramStartReachedError,
)
from _thinkengine.runme.runme_offline_debug_against_actionscript import SessionProgramScriptedHeadlessRunner


from _thinkengine._parsing._higher_lang_grammars._langs_registrations import ensure_default_program_languages_registered
ensure_default_program_languages_registered()


@register_step_fn("emit_profile_form", required_args=set(), optional_args={"prefill_age"})
def emit_profile_form(state: Dict[str, Any], prefill_age: Optional[int] = None) -> Dict[str, Any]:
    fills = {}
    if prefill_age is not None:
        fills["AGE"] = {"value": int(prefill_age)}

    multiframespec = {
        "datums": [
            {
                "id": "NAME",
                "title": "Full name",
                "micros": [
                    {
                        "name": "first",
                        "type": "text",
                        "required": True,
                        "validators": ["app_table_test_validators:is_nonempty_str"],
                    },
                    {
                        "name": "last",
                        "type": "text",
                        "required": True,
                        "validators": ["app_table_test_validators:is_nonempty_str"],
                    },
                ],
            },
            {
                "id": "AGE",
                "title": "Age",
                "micros": [
                    {
                        "name": "value",
                        "type": "number",
                        "required": True,
                        "validators": ["app_table_test_validators:is_positive_int"],
                    }
                ],
            },
        ],
        "frames": [
            {
                "id": "PROFILE",
                "title": "Profile",
                "spans": [{"id": "S_NAME", "owns": ["NAME"]}],
            },
            {
                "id": "CONFIRM",
                "title": "Confirm",
                "tags": ["no-skip"],
                "spans": [{"id": "S_AGE", "owns": ["AGE"]}],
            },
        ],
        "fills": fills,
    }

    return {"profile_started": True, "multiframespec": multiframespec}


@register_step_fn("emit_name_prefill_last", required_args=set(), optional_args=set())
def emit_name_prefill_last(state: Dict[str, Any]) -> Dict[str, Any]:
    multiframespec = {
        "datums": [
            {
                "id": "NAME",
                "title": "Full name",
                "micros": [
                    {"name": "first", "type": "text", "required": True, "validators": ["app_table_test_validators:is_nonempty_str"]},
                    {"name": "last", "type": "text", "required": True, "validators": ["app_table_test_validators:is_nonempty_str"]},
                ],
            }
        ],
        "frames": [
            {"id": "PROFILE", "title": "Profile", "spans": [{"id": "S_NAME", "owns": ["NAME"]}]},
        ],
        "fills": {"NAME": {"last": "Lovelace"}},
    }
    return {"multiframespec": multiframespec}


@register_step_fn("commit_profile", required_args=set(), optional_args=set())
def commit_profile(state: Dict[str, Any]) -> Dict[str, Any]:
    pref = state.get("form_prefills") or {}
    fills = state.get("form_fills") or {}
    merged = dict(pref)
    merged.update(fills)

    name = merged.get("NAME") or {}
    age = merged.get("AGE") or {}

    return {
        "committed_name": f"{name.get('first','')} {name.get('last','')}".strip(),
        "committed_age": int(age.get("value")) if isinstance(age, dict) and "value" in age else None,
        "committed": True,
    }


def _install_validators_module() -> None:
    import sys
    import types

    mod = types.ModuleType("app_table_test_validators")

    def _unwrap(v):
        if isinstance(v, dict) and "value" in v:
            return v["value"]
        return v

    def is_nonempty_str(v):
        vv = _unwrap(v)
        ok = isinstance(vv, str) and len(vv.strip()) > 0
        return ok, (None if ok else "must be non-empty")

    def is_positive_int(v):
        try:
            ok = int(_unwrap(v)) > 0
        except Exception:
            ok = False
        return ok, (None if ok else "must be a positive integer")

    mod.is_nonempty_str = is_nonempty_str
    mod.is_positive_int = is_positive_int
    sys.modules["app_table_test_validators"] = mod


class TestAppTableSessionsFullStack(unittest.TestCase):
    def setUp(self) -> None:
        _install_validators_module()

        # Isolate registry across tests
        StepFnregistry.clear()
        StepFnregistry.register(name="emit_profile_form", fn=emit_profile_form, required_args=set(), optional_args={"prefill_age"})
        StepFnregistry.register(name="emit_name_prefill_last", fn=emit_name_prefill_last, required_args=set(), optional_args=set())
        StepFnregistry.register(name="commit_profile", fn=commit_profile, required_args=set(), optional_args=set())


    def test_parse_validation_rejects_unknown_step_fn(self):
        api = get_concrete_session_api()
        bad_manifest = [{"public_step_name": "x", "step_fn": "does_not_exist", "fn_args": {}}]
        with self.assertRaises(AppTableParserValidatorError):
            api.create_VM_session(manifest=bad_manifest, initial_parameter_overrides={}, session_metadata={}, get_map=False)  # type: ignore[arg-type]

    def test_parse_validation_rejects_duplicate_public_step_names(self):
        api = get_concrete_session_api()
        bad_manifest = [
            {"public_step_name": "dup", "step_fn": "emit_profile_form", "fn_args": {}},
            {"public_step_name": "dup", "step_fn": "commit_profile", "fn_args": {}},
        ]
        with self.assertRaises(AppTableParserValidatorError):
            api.create_VM_session(manifest=bad_manifest, initial_parameter_overrides={}, session_metadata={}, get_map=False)  # type: ignore[arg-type]

    def test_language_create_VM_session_from_program_app_table_equivalent(self):
        api = get_concrete_session_api()

        manifest = [
            {"public_step_name": "profile", "step_fn": "emit_profile_form", "fn_args": {"prefill_age": 30}},
            {"public_step_name": "commit", "step_fn": "commit_profile", "fn_args": {}},
        ]

        # baseline
        st1 = api.create_VM_session(manifest=manifest, initial_parameter_overrides={}, session_metadata={}, get_map=False)  # type: ignore[arg-type]
        sid1 = st1["session_id"]

        # language path
        st2 = api.create_VM_session_from_program(
            program=manifest,
            program_language="app_table",
            initial_parameter_overrides={},
            session_metadata={},
            get_map=False,
        )  # type: ignore[arg-type]
        sid2 = st2["session_id"]

        self.assertNotEqual(sid1, sid2)

    def test_partial_micro_fill_merges_with_prefills(self):
        api = get_concrete_session_api()

        manifest = [
            {"public_step_name": "name", "step_fn": "emit_name_prefill_last", "fn_args": {}},
            {"public_step_name": "commit", "step_fn": "commit_profile", "fn_args": {}},
        ]
        state = api.create_VM_session(manifest=manifest, initial_parameter_overrides={}, session_metadata={}, get_map=False)  # type: ignore[arg-type]
        sid = state["session_id"]
        r = SessionProgramScriptedHeadlessRunner(sid)

        c1 = r.step_until_stop()
        self.assertEqual(c1["kind"], "MANUALFILLNEEDEDSTEP")
        self.assertEqual(c1["step"]["span_id"], "S_NAME")

        _ = r.step(fill={"NAME": {"first": "Ada"}})

        c3 = r.step_until_stop()
        self.assertEqual(c3["kind"], "ATCOMPLETION")

        out = api.get_outputs(sid)
        self.assertEqual(out["form_prefills"]["NAME"]["last"], "Lovelace")
        self.assertEqual(out["form_fills"]["NAME"]["first"], "Ada")
        self.assertEqual(out["form_fills"]["NAME"]["last"], "Lovelace")

    def test_undo_collapses_dynamic_manual_steps(self):
        api = get_concrete_session_api()

        manifest = [
            {"public_step_name": "profile", "step_fn": "emit_profile_form", "fn_args": {"prefill_age": 30}},
            {"public_step_name": "commit", "step_fn": "commit_profile", "fn_args": {}},
        ]
        state = api.create_VM_session(manifest=manifest, initial_parameter_overrides={}, session_metadata={}, get_map=False)  # type: ignore[arg-type]
        sid = state["session_id"]
        r = SessionProgramScriptedHeadlessRunner(sid)

        c1 = r.step_until_stop()
        self.assertEqual(c1["kind"], "MANUALFILLNEEDEDSTEP")

        u1 = r.undo()
        self.assertIn(u1["kind"], ("FORMEXPANSIONSTEP", "STEPFNSTEP", "ATSTART"))

        while True:
            try:
                _ = r.undo()
            except ProgramStartReachedError:
                break
        self.assertEqual(r.ctx()["kind"], "ATSTART")


if __name__ == "__main__":
    unittest.main()