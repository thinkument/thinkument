from __future__ import annotations

import unittest

import _thinkprogram._iomicrosTM.validators  # noqa: F401
from _thinkprogram._iomicrosTM.core.micro_validator_registry import (
    all_validators,
    assert_registered_validator_integrity,
    get_callable_by_path,
    run_validation_by_path,
)


class TestValidationRegistry(unittest.TestCase):
    def test_registry_integrity(self) -> None:
        validators = all_validators()
        self.assertGreaterEqual(len(validators), 20)
        assert_registered_validator_integrity()

    def test_every_example_and_guidance(self) -> None:
        for meta in all_validators():
            validator_fn = get_callable_by_path(meta.dotted_path)
            module, name = meta.dotted_path.split(":", 1)
            guidance_fn = get_callable_by_path(f"{module}:{name}_guidance")

            for combo in meta.arg_combos:
                for value in combo.valid_examples:
                    self.assertEqual(
                        run_validation_by_path(meta.dotted_path, value, **combo.args),
                        (True, None),
                        msg=f"{meta.dotted_path} valid example {value!r}",
                    )
                for value in combo.invalid_examples:
                    ok, message = run_validation_by_path(
                        meta.dotted_path,
                        value,
                        **combo.args,
                    )
                    self.assertIs(ok, False, f"{meta.dotted_path}: {value!r}")
                    self.assertIsInstance(message, str)
                    self.assertTrue(message.strip())

                guidance = guidance_fn(**combo.args)
                self.assertIsInstance(guidance, dict)
                self.assertIsInstance(guidance.get("message"), str)
                self.assertTrue(guidance["message"].strip())

            self.assertTrue(callable(validator_fn))

    def test_representative_paths_are_stable(self) -> None:
        paths = [
            "_thinkprogram._iomicrosTM.validators.text:min_words",
            "_thinkprogram._iomicrosTM.validators.number:is_finite_number",
            "_thinkprogram._iomicrosTM.validators.number:is_integer",
            "_thinkprogram._iomicrosTM.validators.choice:all_in_allowed",
            "_thinkprogram._iomicrosTM.validators.date:is_iso_datetime",
            "_thinkprogram._iomicrosTM.validators.url:is_http_url",
            "_thinkprogram._iomicrosTM.validators.file:local_filepath",
            "_thinkprogram._iomicrosTM.validators.image:image_url",
            "_thinkprogram._iomicrosTM.validators.object_json:is_dead_json",
        ]
        for path in paths:
            self.assertTrue(callable(get_callable_by_path(path)), path)


if __name__ == "__main__":
    unittest.main()
