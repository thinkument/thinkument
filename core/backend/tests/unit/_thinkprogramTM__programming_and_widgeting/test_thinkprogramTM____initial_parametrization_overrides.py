from __future__ import annotations

from copy import deepcopy
import unittest

from _thinkprogram.thinkprogramTM.api import (
    PUPPETEERING_OVERLAY_KEY_V1,
    PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
    PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
    bind_think_program_symbols_v1,
    normalize_initial_parameter_overrides_v1,
    overlay_initial_parameter_overrides_onto_program_v1,
)


def _program() -> dict:
    """
    Representative ThinkProgramTM source exercising:

    - parametrized and locked symbols;
    - dotted symbol names;
    - nested symbol lookup;
    - list-index lookup;
    - authored puppeteering;
    - references in mappings and lists;
    - whole-value substitution for scalar and structured values.
    """
    return {
        "kind": "think_program_v1",
        "surface_version": "v1",
        "symbols": {
            "tenant": {
                "value": "default-tenant",
                "parametrize": True,
            },
            "profile": {
                "value": {
                    "label": "Profile",
                    "theme": {
                        "density": "comfortable",
                    },
                    "roles": [
                        "reader",
                        "author",
                    ],
                },
                "parametrize": True,
            },
            "profile.label": {
                "value": "Profile",
                "parametrize": True,
            },
            "payload": {
                "value": {
                    "enabled": True,
                    "limits": {
                        "soft": 10,
                        "hard": 20,
                    },
                    "tags": [
                        "default",
                    ],
                },
                "parametrize": True,
            },
            "locked.label": {
                "value": "Locked",
                "parametrize": False,
            },
            "literal.reference": {
                "value": "$tenant",
                "parametrize": True,
            },
        },
        "puppeteering": {
            "profile.label": "Authored Profile",
            "payload": {
                "enabled": True,
                "limits": {
                    "soft": 25,
                    "hard": 50,
                },
                "tags": [
                    "authored",
                ],
            },
        },
        "run": {
            "program": {
                "info": {
                    "id": "task_b_overlay_test",
                    "title": "$profile.label",
                    "tenant": "$tenant",
                    "locked": "$locked.label",
                    "profile": "$profile",
                    "profile_theme": "$profile.theme",
                    "profile_density": "$profile.theme.density",
                    "first_role": "$profile.roles.0",
                    "payload": "$payload",
                    "payload_soft_limit": "$payload.limits.soft",
                    "literal_reference": "$literal.reference",
                },
                "items": [
                    "$tenant",
                    "$profile.label",
                    "$payload.tags",
                ],
            }
        },
    }


def _merge_overlay(
    **values: object,
) -> dict:
    return {
        PUPPETEERING_OVERLAY_KEY_V1: {
            "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
            "strict": True,
        },
        **values,
    }


def _take_over_overlay(
    **values: object,
) -> dict:
    return {
        PUPPETEERING_OVERLAY_KEY_V1: {
            "mode": PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
            "strict": True,
        },
        **values,
    }


def _non_strict_merge_overlay(
    **values: object,
) -> dict:
    return {
        PUPPETEERING_OVERLAY_KEY_V1: {
            "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
            "strict": False,
        },
        **values,
    }


class ThinkProgramInitialParameterOverridesTests(unittest.TestCase):
    # ------------------------------------------------------------------
    # Normalization contract
    # ------------------------------------------------------------------

    def test_normalize_defaults_to_strict_merge_onto(self) -> None:
        normalized = normalize_initial_parameter_overrides_v1(
            {
                "tenant": "acme",
            }
        )

        self.assertEqual(
            normalized,
            {
                "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
                "strict": True,
                "values": {
                    "tenant": "acme",
                },
            },
        )

    def test_normalize_extracts_control_and_excludes_it_from_values(self) -> None:
        normalized = normalize_initial_parameter_overrides_v1(
            {
                PUPPETEERING_OVERLAY_KEY_V1: {
                    "mode": PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
                    "strict": False,
                },
                "tenant": "acme",
                "profile.label": "Launch Profile",
            }
        )

        self.assertEqual(
            normalized,
            {
                "mode": PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
                "strict": False,
                "values": {
                    "tenant": "acme",
                    "profile.label": "Launch Profile",
                },
            },
        )

        self.assertNotIn(
            PUPPETEERING_OVERLAY_KEY_V1,
            normalized["values"],
        )

    def test_normalize_empty_overlay_has_no_values(self) -> None:
        normalized = normalize_initial_parameter_overrides_v1({})

        self.assertEqual(
            normalized,
            {
                "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
                "strict": True,
                "values": {},
            },
        )

    def test_unknown_control_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "control has unknown keys"):
            normalize_initial_parameter_overrides_v1(
                {
                    PUPPETEERING_OVERLAY_KEY_V1: {
                        "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
                        "strict": True,
                        "extra": "bad",
                    },
                    "tenant": "acme",
                }
            )

    def test_control_mode_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "control.mode"):
            normalize_initial_parameter_overrides_v1(
                {
                    PUPPETEERING_OVERLAY_KEY_V1: {
                        "mode": "replace_kind_of_maybe",
                    },
                    "tenant": "acme",
                }
            )

    def test_control_strict_must_be_boolean(self) -> None:
        with self.assertRaisesRegex(ValueError, "control.strict"):
            normalize_initial_parameter_overrides_v1(
                {
                    PUPPETEERING_OVERLAY_KEY_V1: {
                        "strict": "true",
                    },
                    "tenant": "acme",
                }
            )

    def test_control_value_must_be_a_mapping(self) -> None:
        with self.assertRaises(ValueError):
            normalize_initial_parameter_overrides_v1(
                {
                    PUPPETEERING_OVERLAY_KEY_V1: "merge_onto",
                    "tenant": "acme",
                }
            )

    # ------------------------------------------------------------------
    # Merge-onto behavior
    # ------------------------------------------------------------------

    def test_merge_onto_shallow_assigns_into_existing_puppeteering(self) -> None:
        source = _program()

        effective = overlay_initial_parameter_overrides_onto_program_v1(
            source,
            initial_parameter_overrides=_merge_overlay(
                tenant="acme",
            ),
        )

        self.assertEqual(
            effective["puppeteering"],
            {
                "profile.label": "Authored Profile",
                "payload": {
                    "enabled": True,
                    "limits": {
                        "soft": 25,
                        "hard": 50,
                    },
                    "tags": [
                        "authored",
                    ],
                },
                "tenant": "acme",
            },
        )

    def test_merge_onto_launch_value_wins_over_authored_value(self) -> None:
        effective = overlay_initial_parameter_overrides_onto_program_v1(
            _program(),
            initial_parameter_overrides=_merge_overlay(
                **{
                    "profile.label": "Launch Profile",
                }
            ),
        )

        self.assertEqual(
            effective["puppeteering"]["profile.label"],
            "Launch Profile",
        )

    def test_merge_onto_is_shallow_whole_symbol_assignment(self) -> None:
        launch_payload = {
            "enabled": False,
            "replacement": True,
        }

        effective = overlay_initial_parameter_overrides_onto_program_v1(
            _program(),
            initial_parameter_overrides=_merge_overlay(
                payload=launch_payload,
            ),
        )

        self.assertEqual(
            effective["puppeteering"]["payload"],
            {
                "enabled": False,
                "replacement": True,
            },
        )

        self.assertNotIn(
            "limits",
            effective["puppeteering"]["payload"],
        )
        self.assertNotIn(
            "tags",
            effective["puppeteering"]["payload"],
        )

    def test_merge_onto_preserves_unmentioned_authored_values(self) -> None:
        effective = overlay_initial_parameter_overrides_onto_program_v1(
            _program(),
            initial_parameter_overrides=_merge_overlay(
                tenant="acme",
            ),
        )

        self.assertEqual(
            effective["puppeteering"]["profile.label"],
            "Authored Profile",
        )
        self.assertEqual(
            effective["puppeteering"]["payload"]["tags"],
            [
                "authored",
            ],
        )

    # ------------------------------------------------------------------
    # Take-over behavior
    # ------------------------------------------------------------------

    def test_take_over_replaces_existing_puppeteering(self) -> None:
        effective = overlay_initial_parameter_overrides_onto_program_v1(
            _program(),
            initial_parameter_overrides=_take_over_overlay(
                tenant="acme",
            ),
        )

        self.assertEqual(
            effective["puppeteering"],
            {
                "tenant": "acme",
            },
        )

    def test_take_over_discards_all_unmentioned_authored_values(self) -> None:
        effective = overlay_initial_parameter_overrides_onto_program_v1(
            _program(),
            initial_parameter_overrides=_take_over_overlay(
                **{
                    "profile.label": "Launch Profile",
                }
            ),
        )

        self.assertEqual(
            effective["puppeteering"],
            {
                "profile.label": "Launch Profile",
            },
        )
        self.assertNotIn(
            "payload",
            effective["puppeteering"],
        )

    def test_take_over_with_empty_values_removes_authored_puppeteering(self) -> None:
        effective = overlay_initial_parameter_overrides_onto_program_v1(
            _program(),
            initial_parameter_overrides={
                PUPPETEERING_OVERLAY_KEY_V1: {
                    "mode": PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
                    "strict": True,
                },
            },
        )

        self.assertTrue(
            "puppeteering" not in effective
            or effective["puppeteering"] == {}
        )

    # ------------------------------------------------------------------
    # Strictness and symbol admission
    # ------------------------------------------------------------------

    def test_strict_true_rejects_unknown_symbol(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown symbol"):
            overlay_initial_parameter_overrides_onto_program_v1(
                _program(),
                initial_parameter_overrides={
                    "does.not.exist": "bad",
                },
            )

    def test_strict_true_rejects_non_parametrized_symbol(self) -> None:
        with self.assertRaisesRegex(ValueError, "not parametrized"):
            overlay_initial_parameter_overrides_onto_program_v1(
                _program(),
                initial_parameter_overrides={
                    "locked.label": "bad",
                },
            )

    def test_strict_true_is_atomic_when_any_value_is_invalid(self) -> None:
        source = _program()
        before = deepcopy(source)

        with self.assertRaises(ValueError):
            overlay_initial_parameter_overrides_onto_program_v1(
                source,
                initial_parameter_overrides={
                    "tenant": "acme",
                    "does.not.exist": "bad",
                },
            )

        self.assertEqual(
            source,
            before,
        )

    def test_strict_false_ignores_unknown_and_non_parametrized_symbols(
        self,
    ) -> None:
        effective = overlay_initial_parameter_overrides_onto_program_v1(
            _program(),
            initial_parameter_overrides=_non_strict_merge_overlay(
                tenant="acme",
                **{
                    "locked.label": "ignored",
                    "does.not.exist": "ignored",
                },
            ),
        )

        self.assertEqual(
            effective["puppeteering"],
            {
                "profile.label": "Authored Profile",
                "payload": {
                    "enabled": True,
                    "limits": {
                        "soft": 25,
                        "hard": 50,
                    },
                    "tags": [
                        "authored",
                    ],
                },
                "tenant": "acme",
            },
        )

    def test_strict_false_applies_valid_values_while_dropping_invalid_values(
        self,
    ) -> None:
        effective = overlay_initial_parameter_overrides_onto_program_v1(
            _program(),
            initial_parameter_overrides=_non_strict_merge_overlay(
                tenant="acme",
                **{
                    "profile.label": "Launch Profile",
                    "locked.label": "ignored",
                    "does.not.exist": "ignored",
                },
            ),
        )

        self.assertEqual(
            effective["puppeteering"]["tenant"],
            "acme",
        )
        self.assertEqual(
            effective["puppeteering"]["profile.label"],
            "Launch Profile",
        )
        self.assertNotIn(
            "locked.label",
            effective["puppeteering"],
        )
        self.assertNotIn(
            "does.not.exist",
            effective["puppeteering"],
        )

    def test_strict_false_take_over_keeps_only_valid_launch_values(
        self,
    ) -> None:
        effective = overlay_initial_parameter_overrides_onto_program_v1(
            _program(),
            initial_parameter_overrides={
                PUPPETEERING_OVERLAY_KEY_V1: {
                    "mode": PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
                    "strict": False,
                },
                "tenant": "acme",
                "locked.label": "ignored",
                "does.not.exist": "ignored",
            },
        )

        self.assertEqual(
            effective["puppeteering"],
            {
                "tenant": "acme",
            },
        )

    # ------------------------------------------------------------------
    # Purity, copying, and source provenance
    # ------------------------------------------------------------------

    def test_overlay_does_not_mutate_source_program(self) -> None:
        source = _program()
        before = deepcopy(source)

        effective = overlay_initial_parameter_overrides_onto_program_v1(
            source,
            initial_parameter_overrides=_merge_overlay(
                tenant="acme",
                **{
                    "profile.label": "Launch Profile",
                },
            ),
        )

        self.assertEqual(
            source,
            before,
        )
        self.assertIsNot(
            effective,
            source,
        )
        self.assertEqual(
            source["puppeteering"]["profile.label"],
            "Authored Profile",
        )

    def test_overlay_does_not_alias_structured_launch_values(self) -> None:
        source = _program()
        launch_payload = {
            "enabled": False,
            "nested": {
                "value": 1,
            },
        }

        effective = overlay_initial_parameter_overrides_onto_program_v1(
            source,
            initial_parameter_overrides=_merge_overlay(
                payload=launch_payload,
            ),
        )

        launch_payload["nested"]["value"] = 999

        self.assertEqual(
            effective["puppeteering"]["payload"],
            {
                "enabled": False,
                "nested": {
                    "value": 1,
                },
            },
        )

    def test_bind_does_not_mutate_source_program(self) -> None:
        source = _program()
        before = deepcopy(source)

        run = bind_think_program_symbols_v1(
            source,
            initial_parameter_overrides={
                "tenant": "acme",
                "profile.label": "Launch Profile",
            },
        )

        self.assertEqual(
            source,
            before,
        )
        self.assertIsNot(
            run,
            source["run"],
        )

    def test_empty_overlay_does_not_invent_puppeteering(self) -> None:
        source = _program()
        source.pop("puppeteering")

        effective = overlay_initial_parameter_overrides_onto_program_v1(
            source,
            initial_parameter_overrides={},
        )

        self.assertNotIn(
            "puppeteering",
            effective,
        )

    def test_empty_merge_overlay_preserves_existing_authored_puppeteering(
        self,
    ) -> None:
        source = _program()

        effective = overlay_initial_parameter_overrides_onto_program_v1(
            source,
            initial_parameter_overrides={},
        )

        self.assertEqual(
            effective["puppeteering"],
            source["puppeteering"],
        )

    # ------------------------------------------------------------------
    # Dead-JSON membrane
    # ------------------------------------------------------------------

    def test_overlay_accepts_all_dead_json_value_categories(self) -> None:
        values = [
            None,
            True,
            False,
            0,
            1,
            1.5,
            "",
            "acme",
            [],
            [
                1,
                "two",
                None,
                {
                    "nested": True,
                },
            ],
            {},
            {
                "nested": {
                    "items": [
                        1,
                        2,
                        3,
                    ],
                },
            },
        ]

        for value in values:
            with self.subTest(value=value):
                effective = overlay_initial_parameter_overrides_onto_program_v1(
                    _program(),
                    initial_parameter_overrides={
                        "tenant": value,
                    },
                )

                self.assertEqual(
                    effective["puppeteering"]["tenant"],
                    value,
                )

    def test_overlay_values_must_be_dead_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "dead JSON"):
            overlay_initial_parameter_overrides_onto_program_v1(
                _program(),
                initial_parameter_overrides={
                    "tenant": object(),
                },
            )

    def test_nested_overlay_values_must_be_dead_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "dead JSON"):
            overlay_initial_parameter_overrides_onto_program_v1(
                _program(),
                initial_parameter_overrides={
                    "payload": {
                        "valid": [
                            1,
                            2,
                        ],
                        "invalid": object(),
                    },
                },
            )

    # ------------------------------------------------------------------
    # Reserved control-key behavior
    # ------------------------------------------------------------------

    def test_control_key_is_reserved_as_symbol_name(self) -> None:
        program = _program()
        program["symbols"][PUPPETEERING_OVERLAY_KEY_V1] = {
            "value": "bad",
            "parametrize": True,
        }

        with self.assertRaisesRegex(ValueError, "reserved"):
            overlay_initial_parameter_overrides_onto_program_v1(
                program,
                initial_parameter_overrides={
                    "tenant": "acme",
                },
            )

    def test_control_key_never_enters_effective_puppeteering(self) -> None:
        effective = overlay_initial_parameter_overrides_onto_program_v1(
            _program(),
            initial_parameter_overrides=_merge_overlay(
                tenant="acme",
            ),
        )

        self.assertNotIn(
            PUPPETEERING_OVERLAY_KEY_V1,
            effective["puppeteering"],
        )

    # ------------------------------------------------------------------
    # Binding semantics
    # ------------------------------------------------------------------

    def test_bind_resolves_effective_puppeteering_values(self) -> None:
        run = bind_think_program_symbols_v1(
            _program(),
            initial_parameter_overrides={
                "tenant": "acme",
                "profile.label": "Launch Profile",
            },
        )

        info = run["program"]["info"]

        self.assertEqual(
            info["id"],
            "task_b_overlay_test",
        )
        self.assertEqual(
            info["title"],
            "Launch Profile",
        )
        self.assertEqual(
            info["tenant"],
            "acme",
        )
        self.assertEqual(
            info["locked"],
            "Locked",
        )

    def test_bind_uses_authored_puppeteering_when_launch_has_no_replacement(
        self,
    ) -> None:
        run = bind_think_program_symbols_v1(
            _program(),
            initial_parameter_overrides={
                "tenant": "acme",
            },
        )

        self.assertEqual(
            run["program"]["info"]["title"],
            "Authored Profile",
        )
        self.assertEqual(
            run["program"]["info"]["tenant"],
            "acme",
        )

    def test_bind_take_over_falls_back_to_symbol_defaults_for_discarded_values(
        self,
    ) -> None:
        run = bind_think_program_symbols_v1(
            _program(),
            initial_parameter_overrides=_take_over_overlay(
                tenant="acme",
            ),
        )

        info = run["program"]["info"]

        self.assertEqual(
            info["tenant"],
            "acme",
        )
        self.assertEqual(
            info["title"],
            "Profile",
        )
        self.assertEqual(
            info["payload"],
            {
                "enabled": True,
                "limits": {
                    "soft": 10,
                    "hard": 20,
                },
                "tags": [
                    "default",
                ],
            },
        )

    def test_bind_replaces_whole_scalar_values(self) -> None:
        run = bind_think_program_symbols_v1(
            _program(),
            initial_parameter_overrides={
                "tenant": 42,
            },
        )

        self.assertEqual(
            run["program"]["info"]["tenant"],
            42,
        )
        self.assertIsInstance(
            run["program"]["info"]["tenant"],
            int,
        )

    def test_bind_replaces_whole_structured_values_without_stringification(
        self,
    ) -> None:
        launch_payload = {
            "enabled": False,
            "limits": {
                "soft": 100,
                "hard": 200,
            },
            "tags": [
                "launch",
                "e2e",
            ],
        }

        run = bind_think_program_symbols_v1(
            _program(),
            initial_parameter_overrides={
                "payload": launch_payload,
            },
        )

        self.assertEqual(
            run["program"]["info"]["payload"],
            launch_payload,
        )
        self.assertIsInstance(
            run["program"]["info"]["payload"],
            dict,
        )

    def test_bind_resolves_nested_mapping_lookup(self) -> None:
        run = bind_think_program_symbols_v1(
            _program(),
            initial_parameter_overrides={
                "profile": {
                    "label": "Launch Nested Profile",
                    "theme": {
                        "density": "compact",
                    },
                    "roles": [
                        "operator",
                        "reviewer",
                    ],
                },
            },
        )

        info = run["program"]["info"]

        self.assertEqual(
            info["profile_theme"],
            {
                "density": "compact",
            },
        )
        self.assertEqual(
            info["profile_density"],
            "compact",
        )

    def test_bind_resolves_list_index_lookup(self) -> None:
        run = bind_think_program_symbols_v1(
            _program(),
            initial_parameter_overrides={
                "profile": {
                    "label": "Launch Nested Profile",
                    "theme": {
                        "density": "compact",
                    },
                    "roles": [
                        "operator",
                        "reviewer",
                    ],
                },
            },
        )

        self.assertEqual(
            run["program"]["info"]["first_role"],
            "operator",
        )

    def test_bind_prefers_longest_declared_symbol_name(self) -> None:
        run = bind_think_program_symbols_v1(
            _program(),
            initial_parameter_overrides={
                "profile": {
                    "label": "Nested Profile",
                    "theme": {
                        "density": "compact",
                    },
                    "roles": [
                        "operator",
                    ],
                },
                "profile.label": "Exact Dotted Symbol",
            },
        )

        self.assertEqual(
            run["program"]["info"]["title"],
            "Exact Dotted Symbol",
        )

    def test_bind_resolves_references_inside_lists(self) -> None:
        run = bind_think_program_symbols_v1(
            _program(),
            initial_parameter_overrides={
                "tenant": "acme",
                "profile.label": "Launch Profile",
            },
        )

        self.assertEqual(
            run["program"]["items"],
            [
                "acme",
                "Launch Profile",
                [
                    "authored",
                ],
            ],
        )

    def test_symbol_values_are_not_recursively_expanded(self) -> None:
        run = bind_think_program_symbols_v1(
            _program(),
            initial_parameter_overrides={
                "tenant": "acme",
            },
        )

        self.assertEqual(
            run["program"]["info"]["literal_reference"],
            "$tenant",
        )


    def test_missing_nested_lookup_is_rejected(self) -> None:
        program = _program()
        program["run"]["program"]["info"]["missing"] = (
            "$profile.theme.does_not_exist"
        )

        with self.assertRaises(ValueError):
            bind_think_program_symbols_v1(program)

    def test_unresolvable_symbol_reference_is_rejected(self) -> None:
        program = _program()
        program["run"]["program"]["info"]["missing"] = "$missing.symbol"

        with self.assertRaises(ValueError):
            bind_think_program_symbols_v1(program)

    # ------------------------------------------------------------------
    # Full concept-level E2E pipeline
    # ------------------------------------------------------------------

    def test_e2e_normalize_overlay_bind_merge_onto(self) -> None:
        source = _program()
        before = deepcopy(source)

        launch_overrides = {
            PUPPETEERING_OVERLAY_KEY_V1: {
                "mode": PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
                "strict": True,
            },
            "tenant": "acme",
            "profile.label": "Launch Profile",
            "payload": {
                "enabled": False,
                "limits": {
                    "soft": 100,
                    "hard": 200,
                },
                "tags": [
                    "launch",
                ],
            },
        }

        normalized = normalize_initial_parameter_overrides_v1(
            launch_overrides
        )

        self.assertEqual(
            normalized["mode"],
            PUPPETEERING_OVERLAY_MODE_MERGE_ONTO_V1,
        )
        self.assertIs(
            normalized["strict"],
            True,
        )
        self.assertEqual(
            normalized["values"],
            {
                "tenant": "acme",
                "profile.label": "Launch Profile",
                "payload": {
                    "enabled": False,
                    "limits": {
                        "soft": 100,
                        "hard": 200,
                    },
                    "tags": [
                        "launch",
                    ],
                },
            },
        )

        effective = overlay_initial_parameter_overrides_onto_program_v1(
            source,
            initial_parameter_overrides=launch_overrides,
        )

        self.assertEqual(
            effective["puppeteering"],
            {
                "profile.label": "Launch Profile",
                "payload": {
                    "enabled": False,
                    "limits": {
                        "soft": 100,
                        "hard": 200,
                    },
                    "tags": [
                        "launch",
                    ],
                },
                "tenant": "acme",
            },
        )

        run_from_effective = bind_think_program_symbols_v1(effective)
        run_from_direct_launch = bind_think_program_symbols_v1(
            source,
            initial_parameter_overrides=launch_overrides,
        )

        self.assertEqual(
            run_from_direct_launch,
            run_from_effective,
        )

        info = run_from_direct_launch["program"]["info"]

        self.assertEqual(
            info["title"],
            "Launch Profile",
        )
        self.assertEqual(
            info["tenant"],
            "acme",
        )
        self.assertEqual(
            info["locked"],
            "Locked",
        )
        self.assertEqual(
            info["payload"],
            {
                "enabled": False,
                "limits": {
                    "soft": 100,
                    "hard": 200,
                },
                "tags": [
                    "launch",
                ],
            },
        )
        self.assertEqual(
            info["payload_soft_limit"],
            100,
        )

        self.assertEqual(
            source,
            before,
        )
        self.assertNotIn(
            PUPPETEERING_OVERLAY_KEY_V1,
            effective["puppeteering"],
        )

    def test_e2e_normalize_overlay_bind_take_over(self) -> None:
        source = _program()
        before = deepcopy(source)

        launch_overrides = _take_over_overlay(
            tenant="take-over-tenant",
        )

        normalized = normalize_initial_parameter_overrides_v1(
            launch_overrides
        )

        self.assertEqual(
            normalized,
            {
                "mode": PUPPETEERING_OVERLAY_MODE_TAKE_OVER_V1,
                "strict": True,
                "values": {
                    "tenant": "take-over-tenant",
                },
            },
        )

        effective = overlay_initial_parameter_overrides_onto_program_v1(
            source,
            initial_parameter_overrides=launch_overrides,
        )

        self.assertEqual(
            effective["puppeteering"],
            {
                "tenant": "take-over-tenant",
            },
        )

        run = bind_think_program_symbols_v1(
            source,
            initial_parameter_overrides=launch_overrides,
        )

        info = run["program"]["info"]

        self.assertEqual(
            info["tenant"],
            "take-over-tenant",
        )
        self.assertEqual(
            info["title"],
            "Profile",
        )
        self.assertEqual(
            info["payload"],
            {
                "enabled": True,
                "limits": {
                    "soft": 10,
                    "hard": 20,
                },
                "tags": [
                    "default",
                ],
            },
        )

        self.assertEqual(
            source,
            before,
        )

    def test_e2e_non_strict_launch_applies_valid_subset(self) -> None:
        source = _program()

        launch_overrides = _non_strict_merge_overlay(
            tenant="acme",
            **{
                "profile.label": "Launch Profile",
                "locked.label": "must-not-cross",
                "does.not.exist": "must-not-cross",
            },
        )

        effective = overlay_initial_parameter_overrides_onto_program_v1(
            source,
            initial_parameter_overrides=launch_overrides,
        )
        run = bind_think_program_symbols_v1(
            source,
            initial_parameter_overrides=launch_overrides,
        )

        self.assertEqual(
            effective["puppeteering"]["tenant"],
            "acme",
        )
        self.assertEqual(
            effective["puppeteering"]["profile.label"],
            "Launch Profile",
        )
        self.assertNotIn(
            "locked.label",
            effective["puppeteering"],
        )
        self.assertNotIn(
            "does.not.exist",
            effective["puppeteering"],
        )

        self.assertEqual(
            run["program"]["info"]["tenant"],
            "acme",
        )
        self.assertEqual(
            run["program"]["info"]["title"],
            "Launch Profile",
        )
        self.assertEqual(
            run["program"]["info"]["locked"],
            "Locked",
        )

    def test_e2e_launch_control_is_consumed_and_never_becomes_program_data(
        self,
    ) -> None:
        source = _program()

        launch_overrides = _merge_overlay(
            tenant="acme",
        )

        effective = overlay_initial_parameter_overrides_onto_program_v1(
            source,
            initial_parameter_overrides=launch_overrides,
        )
        run = bind_think_program_symbols_v1(
            source,
            initial_parameter_overrides=launch_overrides,
        )

        self.assertNotIn(
            PUPPETEERING_OVERLAY_KEY_V1,
            effective.get("puppeteering", {}),
        )
        self.assertNotIn(
            PUPPETEERING_OVERLAY_KEY_V1,
            run,
        )
        self.assertNotIn(
            PUPPETEERING_OVERLAY_KEY_V1,
            run["program"],
        )
        self.assertNotIn(
            PUPPETEERING_OVERLAY_KEY_V1,
            run["program"]["info"],
        )


if __name__ == "__main__":
    unittest.main()