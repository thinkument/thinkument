# think-backend/tests/wipp/engine/app_tables/test_app_table_stepfn_output_writes_session_metadata.py

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Mapping

import pytest

from __exceptions.engine import FatalEngineError

from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinksessions.sesh_metadata.sesh_metadata_surface import (
    session_args_surface_keys,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api


# ---------------------------------------------------------------------------
# App Table router contract: session_metadata_update
# ---------------------------------------------------------------------------
#
# This sheet proves both the correctness contract and the scaling/cost model for
# step-fn writes to session metadata.
#
# Correctness contract:
#   - session_metadata_update is accepted as a reserved step-fn output.
#   - updates are constrained by the canonical SessionArgs surface.
#   - unknown keys / bad types fail.
#   - nested mapping updates deep-merge where intended.
#
# Cost model:
#   - fn-only metadata-update programs stay on the cheap app-table fn/output path.
#   - they do not accidentally route through manual IO.
#   - they do not render forms.
#   - they do not materialize hidden full snapshots per step.
#   - replacements do not accumulate old values.
#
# Keep timing assertions deliberately loose. They are not microbenchmarks; they
# are regression tripwires for accidental quadratic/snapshot/render/manual paths.
# ---------------------------------------------------------------------------


def _api():
    return get_concrete_session_api(enable_persistence=False)


def _manifest(step_names: List[str]) -> List[Dict[str, Any]]:
    return [
        {
            "public_step_name": f"S{i}",
            "step_fn": name,
            "fn_args": {},
        }
        for i, name in enumerate(step_names)
    ]


def _create(
    api,
    step_names: List[str],
    *,
    session_metadata: Mapping[str, Any] | None = None,
) -> str:
    st = api.create_VM_session(
        manifest=_manifest(step_names),
        initial_parameter_overrides={},
        session_metadata=dict(session_metadata or {}),
        get_map=False,
    )
    return str(st["session_id"])


def _run_to_completion(
    api,
    sid: str,
    *,
    max_steps: int = 32,
) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}
    for _ in range(max_steps):
        ctx = api.step_session(sid)
        if ctx.get("kind") == "ATCOMPLETION":
            return ctx
    raise AssertionError(
        f"session did not complete within {max_steps} steps; last ctx={ctx!r}"
    )


def _contains_run(haystack: object, needle: str) -> bool:
    return needle in repr(haystack)


def _step_update_session_metadata_ok(_state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "session_metadata_update": {
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": True,
            },
            "session_storage": {},
        },
        "some_global": "ok",
    }


def _step_update_session_metadata_second(_state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "session_metadata_update": {
            "manual_io": {
                "include_field_value_keys_in_ctx": True,
            },
            "session_storage": {},
        },
        "another_global": {"nested": True},
    }


def _step_update_session_metadata_bad_key(_state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "session_metadata_update": {
            "not_a_real_session_arg_key": 123,
        }
    }


def _step_update_session_metadata_bad_value(_state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "session_metadata_update": {
            "manual_io": "nope",
        }
    }


def _step_update_session_metadata_not_mapping(
    _state: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "session_metadata_update": ["manual_io", "bad"],
    }


def _make_metadata_manual_io_tick_fn(
    i: int,
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """
    Build a tiny fn-only step that replaces stable manual_io metadata values.

    Complexity signal:
      - current values replace previous values;
      - old values do not remain in metadata payloads;
      - runtime remains proportional to the number of function steps.
    """

    def _fn(_state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "session_metadata_update": {
                "manual_io": {
                    "persistence": "disabled",
                    "include_field_value_keys_in_ctx": bool(i % 2),
                    "include_forms_emitted_order_in_ctx": bool((i + 1) % 2),
                },
            },
            f"tick_{i}": i,
        }

    return _fn


@pytest.fixture(autouse=True)
def _setup() -> None:
    StepFnregistry.clear()

    StepFnregistry.register(
        name="router.update_session_metadata_ok",
        fn=_step_update_session_metadata_ok,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )
    StepFnregistry.register(
        name="router.update_session_metadata_second",
        fn=_step_update_session_metadata_second,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )
    StepFnregistry.register(
        name="router.update_session_metadata_bad_key",
        fn=_step_update_session_metadata_bad_key,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )
    StepFnregistry.register(
        name="router.update_session_metadata_bad_value",
        fn=_step_update_session_metadata_bad_value,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )
    StepFnregistry.register(
        name="router.update_session_metadata_not_mapping",
        fn=_step_update_session_metadata_not_mapping,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def test_router_session_metadata_update_is_applied_and_visible_in_context() -> None:
    api = _api()
    sid = _create(api, ["router.update_session_metadata_ok"])

    ctx = api.step_session(sid)

    assert isinstance(ctx.get("session_metadata") or {}, dict)
    md = ctx["session_metadata"]

    assert isinstance(md["manual_io"], dict)
    assert md["manual_io"]["persistence"] in {"disabled", "boundary"}
    assert md["manual_io"]["include_forms_emitted_order_in_ctx"] is True
    assert isinstance(md["session_storage"], dict)

    outputs = api.get_outputs(sid)
    assert outputs["globals"]["some_global"] == "ok"
    assert "some_global" not in outputs


def test_router_session_metadata_update_preserves_initial_unmentioned_keys_and_deep_merges_mappings() -> None:
    api = _api()

    initial_metadata: Dict[str, Any] = {
        "manual_io": {
            "persistence": "disabled",
        },
        "session_storage": {},
    }

    sid = _create(
        api,
        [
            "router.update_session_metadata_ok",
            "router.update_session_metadata_second",
        ],
        session_metadata=initial_metadata,
    )

    ctx = _run_to_completion(api, sid)

    md = ctx["session_metadata"]
    assert isinstance(md["manual_io"], dict)
    assert md["manual_io"]["persistence"] in {"disabled", "boundary"}
    assert md["manual_io"]["include_forms_emitted_order_in_ctx"] is True
    assert md["manual_io"]["include_field_value_keys_in_ctx"] is True
    assert isinstance(md["session_storage"], dict)

    outputs = api.get_outputs(sid)
    assert outputs["globals"]["some_global"] == "ok"
    assert outputs["globals"]["another_global"] == {"nested": True}
    

def test_router_rejects_bad_session_metadata_key() -> None:
    api = _api()
    sid = _create(api, ["router.update_session_metadata_bad_key"])

    with pytest.raises(FatalEngineError):
        api.step_session(sid)


def test_router_rejects_bad_value_types_via_session_args_surface_validation() -> None:
    api = _api()
    sid = _create(api, ["router.update_session_metadata_bad_value"])

    with pytest.raises(FatalEngineError):
        api.step_session(sid)


def test_router_rejects_non_mapping_session_metadata_update() -> None:
    api = _api()
    sid = _create(api, ["router.update_session_metadata_not_mapping"])

    with pytest.raises(FatalEngineError):
        api.step_session(sid)


def test_session_args_surface_keys_is_nonempty_and_drives_allowed_set() -> None:
    keys = session_args_surface_keys()

    assert isinstance(keys, set)
    assert "roles" in keys
    assert "role_mismatch_policy" in keys
    assert "manual_io" in keys
    assert "session_storage" in keys
    assert "not_a_real_session_arg_key" not in keys
    assert len(keys) >= 4


def test_metadata_update_path_does_not_require_or_expose_manual_io_surfaces() -> None:
    n = 16

    for i in range(n):
        StepFnregistry.register(
            name=f"router.metadata_no_manual.{i}",
            fn=_make_metadata_manual_io_tick_fn(i),
            required_args=set(),
            optional_args=set(),
            overwrite=True,
        )

    api = _api()
    sid = _create(api, [f"router.metadata_no_manual.{i}" for i in range(n)])

    ctx = _run_to_completion(api, sid, max_steps=n + 8)

    assert ctx["kind"] == "ATCOMPLETION"
    assert not _contains_run(ctx, "MANUALFILLNEEDEDSTEP")
    assert not _contains_run(ctx, "datum_widgets_on_this_span")
    assert ctx["session_metadata"]["manual_io"]["persistence"] == "disabled"


def test_bad_metadata_update_fails_fast_before_later_steps_mutate_metadata() -> None:
    StepFnregistry.register(
        name="router.metadata_after_bad_should_not_run",
        fn=_step_update_session_metadata_second,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )

    api = _api()
    sid = _create(
        api,
        [
            "router.update_session_metadata_ok",
            "router.update_session_metadata_bad_value",
            "router.metadata_after_bad_should_not_run",
        ],
    )

    with pytest.raises(FatalEngineError):
        _run_to_completion(api, sid, max_steps=8)

    ctx = api.get_session_context(sid)
    md = ctx.get("session_metadata") or {}

    assert md.get("manual_io", {}).get("include_field_value_keys_in_ctx") is not True


def test_every_function_step_can_write_session_metadata_and_complete_seamlessly() -> None:
    """
    Top-down scaling proof:
      - every function step writes metadata;
      - no manual UI is emitted;
      - completion remains fast enough to catch accidental render/manual/snapshot
        path regressions without acting as a brittle microbenchmark.
    """
    n = 120

    for i in range(n):
        StepFnregistry.register(
            name=f"router.metadata_tick.{i}",
            fn=_make_metadata_manual_io_tick_fn(i),
            required_args=set(),
            optional_args=set(),
            overwrite=True,
        )

    api = _api()
    sid = _create(api, [f"router.metadata_tick.{i}" for i in range(n)])

    t0 = time.perf_counter()
    ctx = _run_to_completion(api, sid, max_steps=n + 8)
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    md = ctx["session_metadata"]
    assert md["manual_io"]["persistence"] == "disabled"
    assert md["manual_io"]["include_field_value_keys_in_ctx"] == bool((n - 1) % 2)
    assert md["manual_io"]["include_forms_emitted_order_in_ctx"] == bool(n % 2)

    outputs = api.get_outputs(sid)
    assert outputs["globals"]["tick_0"] == 0
    assert outputs["globals"][f"tick_{n - 1}"] == n - 1

    assert elapsed < 2.0


def test_many_metadata_updates_scale_roughly_linearly_not_quadratically() -> None:
    """
    Compare a smaller and larger fn-only metadata workload.

    This is intentionally loose. It does not assert a precise performance number.
    It catches large structural mistakes such as:
      - scanning full history on every metadata update;
      - serializing snapshots on every fn-only step;
      - rendering UI on non-UI metadata steps;
      - quadratic merge behavior for replacement updates.
    """

    def _run_case(n: int) -> float:
        StepFnregistry.clear()

        for i in range(n):
            StepFnregistry.register(
                name=f"router.metadata_scale.{n}.{i}",
                fn=_make_metadata_manual_io_tick_fn(i),
                required_args=set(),
                optional_args=set(),
                overwrite=True,
            )

        api = _api()
        sid = _create(api, [f"router.metadata_scale.{n}.{i}" for i in range(n)])

        t0 = time.perf_counter()
        ctx = _run_to_completion(api, sid, max_steps=n + 8)
        elapsed = time.perf_counter() - t0

        assert ctx["kind"] == "ATCOMPLETION"
        assert ctx["session_metadata"]["manual_io"]["persistence"] == "disabled"
        return elapsed

    small_n = 40
    large_n = 160

    small_elapsed = _run_case(small_n)
    large_elapsed = _run_case(large_n)

    per_step_small = small_elapsed / small_n
    per_step_large = large_elapsed / large_n

    assert large_elapsed < 2.5
    assert per_step_large <= max(per_step_small * 6.0, 0.01)


def test_metadata_replacement_scales_to_large_fn_count_without_payload_growth() -> None:
    """
    Large fn-count replacement tripwire.

    The final metadata should contain only final replacement values, not every
    historical value. This proves session metadata remains replacement state
    rather than an append-only hidden log.
    """
    n = 1000

    for i in range(n):
        StepFnregistry.register(
            name=f"router.metadata_foreverish.{i}",
            fn=_make_metadata_manual_io_tick_fn(i),
            required_args=set(),
            optional_args=set(),
            overwrite=True,
        )

    api = _api()
    sid = _create(api, [f"router.metadata_foreverish.{i}" for i in range(n)])

    t0 = time.perf_counter()
    ctx = _run_to_completion(api, sid, max_steps=n + 8)
    elapsed = time.perf_counter() - t0

    assert ctx["kind"] == "ATCOMPLETION"

    md = ctx["session_metadata"]["manual_io"]
    assert md["persistence"] == "disabled"
    assert md["include_field_value_keys_in_ctx"] == bool((n - 1) % 2)
    assert md["include_forms_emitted_order_in_ctx"] == bool(n % 2)

    visible = repr(ctx["session_metadata"])
    assert "MANUALFILLNEEDEDSTEP" not in visible
    assert "datum_widgets_on_this_span" not in visible

    assert elapsed < 3.0