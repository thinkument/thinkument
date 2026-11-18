
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping

from _thinkprogram._iomicrosTM.tiny_helpers import DeadJSONError, assert_dead_json

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from __exceptions.engine import AppTableParserValidatorError


@dataclass(frozen=True)
class StepSpec:
    public_step_name: str
    step_fn: str
    fn_args: Dict[str, Any]


def _coerce_step(obj: Any, idx: int) -> StepSpec:
    if not isinstance(obj, Mapping):
        raise AppTableParserValidatorError(f"step[{idx}] must be an object")

    public_step_name = str(obj.get("public_step_name", "")).strip()
    step_fn = str(obj.get("step_fn", "")).strip()
    fn_args = obj.get("fn_args", {})

    if not public_step_name:
        raise AppTableParserValidatorError(f"step[{idx}].public_step_name must be non-empty")
    if not step_fn:
        raise AppTableParserValidatorError(f"step[{idx}].step_fn must be non-empty")
    if not isinstance(fn_args, dict):
        raise AppTableParserValidatorError(f"step[{idx}].fn_args must be an object")

    # Membrane: fn_args must be dead JSON (portable + persistable).
    try:
        assert_dead_json(fn_args, path=f"manifest.steps[{idx}].fn_args")
    except DeadJSONError as e:
        raise AppTableParserValidatorError(str(e)) from e

    return StepSpec(public_step_name=public_step_name, step_fn=step_fn, fn_args=dict(fn_args))


def parse_and_validate_app_table(manifest: Any) -> List[StepSpec]:
    """
    Accepts an app table manifest in any of these shapes:
      - list[StepSpec-like dict]
      - {"steps": [...]}  (common wrapper form)

    Returns:
      list[StepSpec] with validated fn args against registry.
    """
    # Membrane: manifest must be dead JSON (portable + persistable).
    try:
        assert_dead_json(manifest, path="manifest")
    except DeadJSONError as e:
        raise AppTableParserValidatorError(str(e)) from e

    steps_raw: Any = manifest
    if isinstance(manifest, Mapping) and "steps" in manifest:
        steps_raw = manifest["steps"]

    if not isinstance(steps_raw, list):
        raise AppTableParserValidatorError("app table manifest must be a list (or {'steps': list})")

    steps: List[StepSpec] = []
    for i, obj in enumerate(steps_raw):
        steps.append(_coerce_step(obj, i))

    # public_step_name uniqueness (O(n))
    seen = set()
    dupes = set()
    for s in steps:
        if s.public_step_name in seen:
            dupes.add(s.public_step_name)
        seen.add(s.public_step_name)
    if dupes:
        raise AppTableParserValidatorError(f"duplicate step public_step_name(s): {sorted(dupes)}")

    # step_fn existence + arg validation
    for i, s in enumerate(steps):
        try:
            spec = StepFnregistry.get(s.step_fn)
        except KeyError as e:
            raise AppTableParserValidatorError(f"step[{i}] references unknown step_fn: {s.step_fn}") from e
        try:
            spec.validate_args(s.fn_args)
        except Exception as e:
            raise AppTableParserValidatorError(f"step[{i}] fn_args invalid for {s.step_fn}: {e}") from e

    return steps


def build_program_map(steps: List[StepSpec]) -> Dict[str, Any]:
    """
    Cheap introspection map returned at create_VM_session(get_map=True).

    This is intentionally stable, JSON-only, and fast to compute.
    """
    return {
        "kind": "app_table",
        "version": 1,
        "step_fns_registered": StepFnregistry.list_names(),
        "app_steps": [
            {"public_step_name": s.public_step_name, "step_fn": s.step_fn, "fn_args": dict(s.fn_args)}
            for s in steps
        ],
    }
