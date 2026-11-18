# think-backend/tests/wippp/test_datum_lifecycle_Q.py
from __future__ import annotations

from typing import Any, Dict, Mapping

import pytest

from _thinkengine._app_table_engine._engine_runtime_events_emission.engine_events_mixin import (
    set_session_event_callback,
)


from __datomatonTM import (
    register_datum_widget_v1
)
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import StepFnregistry
from _thinkengine.__persistence.config import set_session_repo
from _thinkengine.__persistence.repo import SessionRepo
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api
from _thinkengine.runme.runme_offline_debug_against_actionscript import run_session_against_script_headless

from __multiframespecTM.surface import MultiframeSpec

def _text_micro(name: str = "value", *, required: bool = True) -> Dict[str, Any]:
    return {"name": name, "type": "text", "required": required}


def _multiframespec(
    *,
    datum: Mapping[str, Any],
    spans: list[Mapping[str, Any]] | None = None,
    frames: list[Mapping[str, Any]] | None = None,
    form_id: str = "q.form",
) -> Dict[str, Any]:
    if frames is None:
        frames = [
            {
                "id": "F",
                "title": "Frame",
                "spans": spans
                if spans is not None
                else [
                    {
                        "id": "S",
                        "owns": [str(datum["id"])],
                    }
                ],
            }
        ]
    return {
        "app_form_id": form_id,
        "datums": [dict(datum)],
        "frames": [dict(f) for f in frames],
    }


def _register_step(name: str, multiframespec: Mapping[str, Any]) -> None:
    def fn(_state: Mapping[str, Any]) -> Dict[str, Any]:
        return {"multiframespec": dict(multiframespec)}

    StepFnregistry.register(
        name=name,
        fn=fn,
        required_args=set(),
        optional_args=set(),
        overwrite=True,
    )


def _api():
    set_session_repo(SessionRepo)
    return get_concrete_session_api()


def _start(api, step_name: str) -> tuple[str, Dict[str, Any]]:
    st = api.create_VM_session(
        manifest=[
            {
                "public_step_name": "q_step",
                "step_fn": step_name,
                "fn_args": {},
            }
        ],
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
    )
    sid = str(st["session_id"])
    ctx = api.step_session(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    return sid, ctx


def test_legacy_p_datum_still_passes_and_commits_fill():
    """
    Baseline P law.

    A datum without explicit lifecycle remains the old fast P datum:
    validate required micros, commit the fill, complete the form.
    """
    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    _register_step("test.q.legacy", _multiframespec(datum=datum))

    api = _api()
    sid, ctx = _start(api, "test.q.legacy")

    assert ctx["datum_widgets_on_this_span"] == ["D"]

    ctx = api.step_session(sid, fill={"D": {"value": "ok"}})
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["D"]["value"] == "ok"


def test_q_blocked_stays_same_span_with_message():
    """
    Q blocked law.

    A lifecycle datum may reject a syntactically valid fill and keep the same
    span public, with a datum-local message surfaced as last_error.
    """
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "status": "blocked",
            "message": {"level": "info", "text": "not enough yet"},
            "state": dict(q.get("state") or {}),
        }

    register_datum_widget_v1("test.q.block", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {"widget": "test.q.block", "max_reexplosions": 2},
    }
    _register_step("test.q.block.step", _multiframespec(datum=datum))

    api = _api()
    sid, ctx = _start(api, "test.q.block.step")
    ctx = api.step_session(sid, fill={"D": {"value": "x"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert ctx["last_error"]["D"] == "not enough yet"


def test_q_reexplode_changes_micros_and_then_done():
    """
    Q reexplode law.

    The span does not know special widget semantics. It asks the datum to decide.
    The datum may replace its micros with a new bounded lifecycle surface, then
    later finish when that new surface is filled.
    """
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = q.get("partial_fill")
        partial_map = dict(partial or {}) if isinstance(partial, Mapping) else {}

        if "confirm" in partial_map:
            return {
                "status": "done",
                "message": {"level": "success", "text": "confirmed"},
                "state": {"confirmed": True},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.q.reexplode",
                    "max_reexplosions": 2,
                    "max_proc_notes": 3,
                },
            },
            "fill": {"confirm": ""},
            "state": {"phase": "confirm"},
            "message": {"level": "info", "text": "please confirm"},
            "proc_notes": {"seen": partial_map},
        }

    register_datum_widget_v1("test.q.reexplode", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": "test.q.reexplode",
            "max_reexplosions": 2,
            "max_proc_notes": 3,
        },
    }
    _register_step("test.q.reexplode.step", _multiframespec(datum=datum))

    api = _api()
    sid, ctx = _start(api, "test.q.reexplode.step")

    ctx = api.step_session(sid, fill={"D": {"value": "first"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert "D" in ctx["datum_widgets_on_this_span"]

    field_decl = ctx["datum_widget_decls"]["D"]
    micros = field_decl.get("micros") or field_decl.get("datum_args", {}).get("micro_input_fields") or []
    assert "confirm" in str(micros)

    ctx = api.step_session(sid, fill={"D": {"confirm": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["D"]["confirm"] == "yes"


def test_q_mount_explode_runs_before_first_render_when_opted_in():
    """
    Mount-explode law.

    Existing Q behavior remains fill-driven unless the datum explicitly asks:

        lifecycle.mount_explode = True

    With that setting, the widget receives signal.kind == "mount" before first
    public render and may replace the datum surface immediately.
    """
    calls: Dict[str, int] = {"mount": 0, "fill": 0}

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        signal = dict(q.get("signal") or {})
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if signal.get("kind") == "mount":
            calls["mount"] += 1
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "micros": [_text_micro("mounted")],
                    "lifecycle": {
                        "widget": "test.q.mount.first_render",
                        "mount_explode": True,
                        "max_reexplosions": 2,
                    },
                },
                "fill": {"mounted": ""},
                "state": {
                    "mounted_on": signal.get("info"),
                },
                "message": {
                    "level": "info",
                    "text": "mounted",
                },
            }

        calls["fill"] += 1
        assert "mounted" in partial
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {"done": True},
        }

    register_datum_widget_v1("test.q.mount.first_render", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": "test.q.mount.first_render",
            "mount_explode": True,
            "max_reexplosions": 2,
        },
    }
    _register_step("test.q.mount.first_render.step", _multiframespec(datum=datum))

    api = _api()
    sid, ctx = _start(api, "test.q.mount.first_render.step")

    assert calls == {"mount": 1, "fill": 0}
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "mounted" in str(ctx["datum_widget_decls"]["D"])

    ctx = api.step_session(sid, fill={"D": {"mounted": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"mount": 1, "fill": 1}


def test_q_without_mount_explode_does_not_run_widget_before_fill():
    """
    Back-compat law.

    Existing lifecycle datums do not run at mount unless mount_explode=True.
    """
    calls: Dict[str, int] = {"total": 0}

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["total"] += 1
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
        }

    register_datum_widget_v1("test.q.mount.off", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": "test.q.mount.off",
            "max_reexplosions": 0,
        },
    }
    _register_step("test.q.mount.off.step", _multiframespec(datum=datum))

    api = _api()
    sid, ctx = _start(api, "test.q.mount.off.step")

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls["total"] == 0

    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert calls["total"] == 1


def test_mount_explode_allows_same_logical_datum_to_reappear_on_later_span():
    """
    Respanned mount law.

    Without mount_explode, a same logical datum id that is done on S1 can make
    S2 stale and skippable.

    With mount_explode, S2 is a fresh mount signal. The datum can reexplode
    into a span-local surface instead of being tri_vially skipped.
    """
    mounted_spans: list[str] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        signal = dict(q.get("signal") or {})
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})
        info = dict(signal.get("info") or {})
        span_id = str(info.get("span_id") or q.get("span_id"))

        if signal.get("kind") == "mount":
            mounted_spans.append(span_id)
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "micros": [_text_micro(f"mounted_{span_id}")],
                    "lifecycle": {
                        "widget": "test.q.mount.respan",
                        "mount_explode": True,
                        "max_reexplosions": 10,
                    },
                },
                "fill": {f"mounted_{span_id}": ""},
                "state": {
                    "last_mounted_span": span_id,
                    "spans_mounted_on": list(mounted_spans),
                },
                "message": {"level": "info", "text": f"mounted {span_id}"},
            }

        return {
            "status": "done",
            "message": {"level": "success", "text": f"done {span_id}"},
            "state": {
                "last_done_span": span_id,
                "partial": partial,
                "spans_mounted_on": list(mounted_spans),
            },
        }

    register_datum_widget_v1("test.q.mount.respan", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": "test.q.mount.respan",
            "mount_explode": True,
            "max_reexplosions": 10,
        },
    }
    fs = _multiframespec(
        datum=datum,
        frames=[
            {"id": "F1", "spans": [{"id": "S1", "owns": ["D"]}]},
            {"id": "F2", "spans": [{"id": "S2", "owns": ["D"]}]},
        ],
        form_id="q.mount.respan",
    )
    _register_step("test.q.mount.respan.step", fs)

    api = _api()
    sid, ctx = _start(api, "test.q.mount.respan.step")

    assert ctx["current_span"] == "S1"
    assert "mounted_S1" in str(ctx["datum_widget_decls"]["D"])

    ctx = api.step_session(sid, fill={"D": {"mounted_S1": "one"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S2"
    assert "mounted_S2" in str(ctx["datum_widget_decls"]["D"])
    assert mounted_spans == ["S1", "S2"]

    ctx = api.step_session(sid, fill={"D": {"mounted_S2": "two"}})
    assert ctx["kind"] == "ATCOMPLETION"


def test_max_reexplosions_forces_satisfied_without_unbounded_loop():
    """
    Guardrail law.

    A widget that keeps asking to reexplode cannot create an unbounded loop.
    Once max_reexplosions is exhausted, the engine forces bounded progress.
    """
    def always_reexplode(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("again")],
                "lifecycle": {
                    "widget": "test.q.always_reexplode",
                    "max_reexplosions": 1,
                },
            },
            "state": {"n": int(q.get("reexplode_count", 0)) + 1},
            "message": {"level": "warning", "text": "again"},
        }

    register_datum_widget_v1("test.q.always_reexplode", always_reexplode, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": "test.q.always_reexplode",
            "max_reexplosions": 1,
        },
    }
    _register_step("test.q.max.step", _multiframespec(datum=datum))

    api = _api()
    sid, _ctx = _start(api, "test.q.max.step")

    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = api.step_session(sid, fill={"D": {"again": "x"}})
    assert ctx["kind"] == "ATCOMPLETION"


def test_multi_datum_span_preserves_working_fill_across_reexplode():
    """
    Span law.

    A span may contain both Q datums and ordinary P datums. If one Q datum
    reexplodes, already-valid sibling fills in the same span must be preserved.
    """
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})
        if "confirm" in partial:
            return {"status": "done", "message": {"level": "success", "text": ""}, "state": {}}
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {"widget": "test.q.multi.reexplode", "max_reexplosions": 2},
            },
            "fill": {"confirm": ""},
            "state": {},
            "message": {"level": "info", "text": "confirm"},
        }

    register_datum_widget_v1("test.q.multi.reexplode", widget, overwrite=True)

    datums = [
        {
            "id": "A",
            "title": "A",
            "micros": [_text_micro()],
            "lifecycle": {"widget": "test.q.multi.reexplode", "max_reexplosions": 2},
        },
        {"id": "B", "title": "B", "micros": [_text_micro()]},
    ]
    fs = {
        "app_form_id": "q.multi",
        "datums": datums,
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["A", "B"]}]}],
    }
    _register_step("test.q.multi.step", fs)

    api = _api()
    sid, _ctx = _start(api, "test.q.multi.step")

    ctx = api.step_session(sid, fill={"A": {"value": "a1"}, "B": {"value": "b1"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["datum_widget_fills"]["B"]["value"] == "b1"

    ctx = api.step_session(sid, fill={"A": {"confirm": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["confirm"] == "yes"
    assert out["form_fills"]["B"]["value"] == "b1"


def test_same_datum_respanned_later_sees_existing_p_fill_and_skips_stale_manual_step():
    """
    Top-down stale-surface law.

    Static form expansion may plan both S1(D) and S2(D) before any fill exists.
    After S1 commits D.value, S2 is stale. Entering S2 must dynamically ask
    whether D is already satisfied and skip the manual surface.
    """
    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    fs = _multiframespec(
        datum=datum,
        frames=[
            {"id": "F1", "spans": [{"id": "S1", "owns": ["D"]}]},
            {"id": "F2", "spans": [{"id": "S2", "owns": ["D"]}]},
        ],
        form_id="q.respan",
    )
    _register_step("test.q.respan.step", fs)

    api = _api()
    sid, ctx = _start(api, "test.q.respan.step")
    assert ctx["current_span"] == "S1"

    ctx = api.step_session(sid, fill={"D": {"value": "ok"}})

    assert ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(sid)
    assert out["form_fills"]["D"]["value"] == "ok"


def test_undo_after_reexplode_returns_to_pre_reexplode_surface_and_redo_replays():
    """
    Undo/redo lifecycle law.

    Reexplode is a public manual tick. Undo returns to the pre-reexplode datum
    surface. Redo replays the bounded public fill and returns to the reexploded
    surface.
    """
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})
        if "confirm" in partial:
            return {"status": "done", "message": {"level": "success", "text": ""}, "state": {}}
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {"widget": "test.q.undo.reexplode", "max_reexplosions": 2},
            },
            "fill": {"confirm": ""},
            "state": {},
            "message": {"level": "info", "text": "confirm"},
        }

    register_datum_widget_v1("test.q.undo.reexplode", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {"widget": "test.q.undo.reexplode", "max_reexplosions": 2},
    }
    _register_step("test.q.undo.step", _multiframespec(datum=datum))

    api = _api()
    sid, _ctx = _start(api, "test.q.undo.step")

    ctx = api.step_session(sid, fill={"D": {"value": "x"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "confirm" in str(ctx["datum_widget_decls"]["D"])

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    field_decl_text = str(ctx["datum_widget_decls"]["D"])
    assert "value" in field_decl_text
    assert "confirm" not in field_decl_text

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "confirm" in str(ctx["datum_widget_decls"]["D"])


def test_redo_branch_clears_after_new_step():
    """
    Redo branch law.

    Once a user undoes and then submits a new manual fill, the old redo branch
    is invalidated.
    """
    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    _register_step("test.q.redo.clear.step", _multiframespec(datum=datum))

    api = _api()
    sid, _ctx = _start(api, "test.q.redo.clear.step")

    ctx = api.step_session(sid, fill={"D": {"value": "one"}})
    assert ctx["kind"] == "ATCOMPLETION"

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = api.step_session(sid, fill={"D": {"value": "two"}})
    assert ctx["kind"] == "ATCOMPLETION"

    with pytest.raises(Exception):
        api.redo_last_step(sid)


def test_scripted_runner_can_feed_reexploding_span_to_completion_with_nested_fill_keys():
    """
    Scripted-runner happy path.

    The canonical manual-fill contract is nested by datum id:

        {"D": {"value": "..."}}
        {"D": {"confirm": "..."}}

    Dotted micro keys are a runner convenience, not the core Q lifecycle law.
    For dynamic reexplode surfaces, the stable test should exercise the same
    nested fill shape used by the UI API.
    """
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": "confirmed"},
                "state": {"phase": "done"},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.q.script.reexplode",
                    "max_reexplosions": 1,
                    "max_proc_notes": 1,
                    "max_messages": 4,
                },
            },
            "fill": {"confirm": ""},
            "state": {"phase": "confirm"},
            "message": {"level": "info", "text": "confirm"},
            "proc_notes": {"small": True},
        }

    register_datum_widget_v1("test.q.script.reexplode", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": "test.q.script.reexplode",
            "max_reexplosions": 1,
            "max_proc_notes": 1,
            "max_messages": 4,
        },
    }
    step_name = "test.q.script.reexplode.step"
    _register_step(step_name, _multiframespec(datum=datum, form_id="q.script.reexplode"))

    api = _api()
    result = run_session_against_script_headless(
        manifest=[
            {
                "public_step_name": "q_script",
                "step_fn": step_name,
                "fn_args": {},
            }
        ],
        initial_parameter_overrides={},
        session_metadata={
            "manual_io": {
                "persistence": "disabled",
                "include_forms_emitted_order_in_ctx": False,
            }
        },
        api=api,
        script=[
            {
                "action": "STEP",
                "until_stop": True,
                "expect": {
                    "kind": "MANUALFILLNEEDEDSTEP",
                    "datum_widgets_on_this_span_contains": ["D"],
                    "current_span": "S",
                },
            },
            {
                "action": "STEP",
                "fill": {"D": {"value": "draft"}},
                "expect": {
                    "kind": "MANUALFILLNEEDEDSTEP",
                    "datum_widgets_on_this_span_contains": ["D"],
                    "current_span": "S",
                },
            },
            {
                "action": "STEP",
                "fill": {"D": {"confirm": "yes"}},
                "expect": {"kind": "ATCOMPLETION"},
            },
        ],
    )

    assert result.ctx["kind"] == "ATCOMPLETION"

    out = api.get_outputs(result.session_id)
    assert out["form_fills"]["D"]["confirm"] == "yes"


def test_scripted_runner_fails_fast_when_reexploding_span_needs_another_fill_but_script_demands_completion():
    """
    Script stop-kind law.

    A Q reexplode means the same logical span needs another fill. Therefore a
    script that submits only D.value and demands ATCOMPLETION is wrong. The
    runner must fail fast and show that the current stop is still manual input.
    """
    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": "confirmed"},
                "state": {},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.q.script.stall.reexplode",
                    "max_reexplosions": 1,
                },
            },
            "fill": {"confirm": ""},
            "state": {},
            "message": {"level": "info", "text": "confirm"},
        }

    register_datum_widget_v1("test.q.script.stall.reexplode", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": "test.q.script.stall.reexplode",
            "max_reexplosions": 1,
        },
    }
    step_name = "test.q.script.stall.reexplode.step"
    _register_step(step_name, _multiframespec(datum=datum, form_id="q.script.stall"))

    api = _api()

    with pytest.raises(RuntimeError, match="MANUALFILLNEEDEDSTEP"):
        run_session_against_script_headless(
            manifest=[
                {
                    "public_step_name": "q_script_stall",
                    "step_fn": step_name,
                    "fn_args": {},
                }
            ],
            initial_parameter_overrides={},
            session_metadata={
                "manual_io": {
                    "persistence": "disabled",
                    "include_forms_emitted_order_in_ctx": False,
                }
            },
            api=api,
            script=[
                {
                    "action": "STEP",
                    "until_stop": True,
                    "fill": {"D": {"value": "draft"}},
                    "stop_kinds": ["ATCOMPLETION"],
                }
            ],
        )


def test_task_e_only_touched_q_datum_reacts_when_sibling_submits():
    """
    Task E causality law.

    In a multi-Q span, submitting A must not invoke B's widget. B should have no
    idea that A reexploded, blocked, or completed unless B itself is touched.
    """
    calls: Dict[str, int] = {"A": 0, "B": 0}

    def widget_a(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["A"] += 1
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": "A done"},
                "state": {"phase": "done"},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.q.task_e.only_touched.A",
                    "max_reexplosions": 1,
                },
            },
            "fill": {"confirm": ""},
            "state": {"phase": "confirm"},
            "message": {"level": "info", "text": "confirm A"},
        }

    def widget_b(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["B"] += 1
        return {
            "status": "done",
            "message": {"level": "success", "text": "B done"},
            "state": {"phase": "done"},
        }

    register_datum_widget_v1("test.q.task_e.only_touched.A", widget_a, overwrite=True)
    register_datum_widget_v1("test.q.task_e.only_touched.B", widget_b, overwrite=True)

    fs = {
        "app_form_id": "q.task_e.only_touched",
        "datums": [
            {
                "id": "A",
                "title": "A",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.task_e.only_touched.A",
                    "max_reexplosions": 1,
                },
            },
            {
                "id": "B",
                "title": "B",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.task_e.only_touched.B",
                    "max_reexplosions": 0,
                },
            },
        ],
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["A", "B"]}]}],
    }
    _register_step("test.q.task_e.only_touched.step", fs)

    api = _api()
    sid, ctx = _start(api, "test.q.task_e.only_touched.step")
    assert ctx["current_span"] == "S"

    ctx = api.step_session(sid, fill={"A": {"value": "draft"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert calls == {"A": 1, "B": 0}
    assert "confirm" in str(ctx["datum_widget_decls"]["A"])

    ctx = api.step_session(sid, fill={"A": {"confirm": "yes"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert calls == {"A": 2, "B": 0}

    ctx = api.step_session(sid, fill={"B": {"value": "bee"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"A": 2, "B": 1}

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["confirm"] == "yes"
    assert out["form_fills"]["B"]["value"] == "bee"


def test_task_e_partial_plain_p_submit_stays_on_span_without_touching_q_sibling():
    """
    Partial span law.

    Submitting a plain-P datum in a multi-datum span may be accepted and cached
    without forcing an untouched Q sibling to run. The same span remains public
    until the Q sibling is explicitly submitted.
    """
    calls: Dict[str, int] = {"Q": 0}

    def widget_q(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["Q"] += 1
        return {
            "status": "done",
            "message": {"level": "success", "text": "Q done"},
            "state": {},
        }

    register_datum_widget_v1("test.q.task_e.partial.Q", widget_q, overwrite=True)

    fs = {
        "app_form_id": "q.task_e.partial",
        "datums": [
            {"id": "P", "title": "P", "micros": [_text_micro()]},
            {
                "id": "Q",
                "title": "Q",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.task_e.partial.Q",
                    "max_reexplosions": 0,
                },
            },
        ],
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["P", "Q"]}]}],
    }
    _register_step("test.q.task_e.partial.step", fs)

    api = _api()
    sid, ctx = _start(api, "test.q.task_e.partial.step")
    assert ctx["current_span"] == "S"

    ctx = api.step_session(sid, fill={"P": {"value": "plain"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["current_span"] == "S"
    assert calls["Q"] == 0
    assert ctx["datum_widget_fills"]["P"]["value"] == "plain"

    ctx = api.step_session(sid, fill={"Q": {"value": "queue"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert calls["Q"] == 1

    out = api.get_outputs(sid)
    assert out["form_fills"]["P"]["value"] == "plain"
    assert out["form_fills"]["Q"]["value"] == "queue"


def test_task_e_undo_redo_preserves_partial_same_span_submit():
    """
    Partial public tick law.

    A partial accepted submit is still a public manual tick:
      - undo removes that partial fill and returns to the same span;
      - redo reapplies it and returns to the same span;
      - untouched Q sibling still is not invoked by redo of P.
    """
    calls: Dict[str, int] = {"Q": 0}

    def widget_q(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["Q"] += 1
        return {
            "status": "done",
            "message": {"level": "success", "text": "Q done"},
            "state": {},
        }

    register_datum_widget_v1("test.q.task_e.partial.redo.Q", widget_q, overwrite=True)

    fs = {
        "app_form_id": "q.task_e.partial.redo",
        "datums": [
            {"id": "P", "title": "P", "micros": [_text_micro()]},
            {
                "id": "Q",
                "title": "Q",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.task_e.partial.redo.Q",
                    "max_reexplosions": 0,
                },
            },
        ],
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["P", "Q"]}]}],
    }
    _register_step("test.q.task_e.partial.redo.step", fs)

    api = _api()
    sid, _ctx = _start(api, "test.q.task_e.partial.redo.step")

    ctx = api.step_session(sid, fill={"P": {"value": "one"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["datum_widget_fills"]["P"]["value"] == "one"
    assert calls["Q"] == 0

    ctx = api.undo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "P" not in (ctx.get("datum_widget_fills") or {})
    assert calls["Q"] == 0

    ctx = api.redo_last_step(sid)
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert ctx["datum_widget_fills"]["P"]["value"] == "one"
    assert calls["Q"] == 0

    ctx = api.step_session(sid, fill={"Q": {"value": "two"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert calls["Q"] == 1


def test_task_e_reexplode_commit_preserves_plain_p_sibling_without_revalidating_q_sibling():
    """
    Regression for the older multi-datum preservation law.

    A and B are submitted together. A reexplodes, B is carried as working fill.
    On A confirm, B should still commit at span completion, but no untouched Q
    sibling should be evaluated as collateral work.
    """
    calls: Dict[str, int] = {"A": 0, "C": 0}

    def widget_a(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["A"] += 1
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})
        if "confirm" in partial:
            return {"status": "done", "message": {"level": "success", "text": ""}, "state": {}}
        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {"widget": "test.q.task_e.preserve.A", "max_reexplosions": 1},
            },
            "fill": {"confirm": ""},
            "state": {},
            "message": {"level": "info", "text": "confirm"},
        }

    def widget_c(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["C"] += 1
        return {"status": "done", "message": {"level": "success", "text": ""}, "state": {}}

    register_datum_widget_v1("test.q.task_e.preserve.A", widget_a, overwrite=True)
    register_datum_widget_v1("test.q.task_e.preserve.C", widget_c, overwrite=True)

    fs = {
        "app_form_id": "q.task_e.preserve",
        "datums": [
            {
                "id": "A",
                "title": "A",
                "micros": [_text_micro()],
                "lifecycle": {"widget": "test.q.task_e.preserve.A", "max_reexplosions": 1},
            },
            {"id": "B", "title": "B", "micros": [_text_micro()]},
            {
                "id": "C",
                "title": "C",
                "micros": [_text_micro()],
                "lifecycle": {"widget": "test.q.task_e.preserve.C", "max_reexplosions": 0},
            },
        ],
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["A", "B", "C"]}]}],
    }
    _register_step("test.q.task_e.preserve.step", fs)

    api = _api()
    sid, _ctx = _start(api, "test.q.task_e.preserve.step")

    ctx = api.step_session(
        sid,
        fill={
            "A": {"value": "a"},
            "B": {"value": "b"},
        },
    )
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1, "C": 0}
    assert ctx["datum_widget_fills"]["B"]["value"] == "b"

    ctx = api.step_session(sid, fill={"A": {"confirm": "yes"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 2, "C": 0}

    ctx = api.step_session(sid, fill={"C": {"value": "c"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"A": 2, "C": 1}

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["confirm"] == "yes"
    assert out["form_fills"]["B"]["value"] == "b"
    assert out["form_fills"]["C"]["value"] == "c"


def test_tomorrow_widget_can_emit_immediate_events_during_reexplosion_without_persisting_them():
    """
    Tomorrow law:

    A datum lifecycle widget may call q["emit"] during its own evaluation.
    The event is delivered immediately to:
      - the engine-local transient event sink;
      - the platform callback.

    The event is not persisted into KEY_DATUM_LIFECYCLE and does not become
    part of output form_fills.
    """
    seen: list[Mapping[str, Any]] = []
    set_session_event_callback(lambda ev: seen.append(dict(ev)))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        emit = q.get("emit")
        assert callable(emit)
        emit(
            {"phase": "before-reexplode", "partial": dict(q.get("partial_fill") or {})},
            name="test.before_reexplode",
        )

        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})
        if "confirm" in partial:
            emit({"phase": "done"}, name="test.done")
            return {
                "status": "done",
                "message": {"level": "success", "text": "done"},
                "state": {"done": True},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [_text_micro("confirm")],
                "lifecycle": {
                    "widget": "test.q.tomorrow.emit.reexplode",
                    "max_reexplosions": 2,
                },
            },
            "fill": {"confirm": ""},
            "state": {"phase": "confirm"},
            "message": {"level": "info", "text": "confirm"},
        }

    register_datum_widget_v1("test.q.tomorrow.emit.reexplode", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {"widget": "test.q.tomorrow.emit.reexplode", "max_reexplosions": 2},
    }
    _register_step("test.q.tomorrow.emit.reexplode.step", _multiframespec(datum=datum))

    api = _api()
    sid, _ctx = _start(api, "test.q.tomorrow.emit.reexplode.step")

    ctx = api.step_session(sid, fill={"D": {"value": "draft"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert seen
    assert seen[-1]["name"] == "test.before_reexplode"
    assert seen[-1]["datum_id"] == "D"
    assert seen[-1]["payload"]["phase"] == "before-reexplode"

    drained = api.drain_session_events(sid)
    assert len(drained) == 1
    assert drained[0]["name"] == "test.before_reexplode"

    state_blob = str(api._get(sid).state)
    assert "test.before_reexplode" not in state_blob

    ctx = api.step_session(sid, fill={"D": {"confirm": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert seen[-1]["name"] == "test.done"

    out = api.get_outputs(sid)
    assert out["form_fills"]["D"]["confirm"] == "yes"
    assert "test.done" not in str(out)

    set_session_event_callback(None)


def test_tomorrow_widget_can_return_events_for_non_callback_style_lifecycles():
    """
    Compatibility law:

    Callback emit is canonical, but widgets that prefer dead-JSON returns may
    include result.events. Those events are delivered after the widget returns.
    """
    seen: list[Mapping[str, Any]] = []
    set_session_event_callback(lambda ev: seen.append(dict(ev)))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
            "events": [
                {
                    "name": "test.returned_event",
                    "channel": "test",
                    "payload": {"datum": q.get("datum_id")},
                }
            ],
        }

    register_datum_widget_v1("test.q.tomorrow.returned_event", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {"widget": "test.q.tomorrow.returned_event", "max_reexplosions": 0},
    }
    _register_step("test.q.tomorrow.returned_event.step", _multiframespec(datum=datum))

    api = _api()
    sid, _ctx = _start(api, "test.q.tomorrow.returned_event.step")
    ctx = api.step_session(sid, fill={"D": {"value": "ok"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert seen[-1]["name"] == "test.returned_event"
    assert seen[-1]["payload"] == {"datum": "D"}
    assert api.drain_session_events(sid)[-1]["name"] == "test.returned_event"

    set_session_event_callback(None)


def test_tomorrow_artificial_event_api_uses_same_packet_and_callback_without_state_write():
    """
    External/webhook law:

    Higher layers may legally emit onto the session without pretending a datum
    reexploded. This uses the same event packet and callback path and remains
    non-durable.
    """
    seen: list[Mapping[str, Any]] = []
    set_session_event_callback(lambda ev: seen.append(dict(ev)))

    datum = {"id": "D", "title": "D", "micros": [_text_micro()]}
    _register_step("test.q.tomorrow.external_event.step", _multiframespec(datum=datum))

    api = _api()
    sid, ctx = _start(api, "test.q.tomorrow.external_event.step")
    assert ctx["current_span"] == "S"

    before_state = str(api._get(sid).state)
    ev = api.emit_session_event(
        sid,
        datum_id="D",
        payload={"hello": "world"},
        name="test.external",
    )
    after_state = str(api._get(sid).state)

    assert ev["source"] == "external"
    assert ev["name"] == "test.external"
    assert ev["payload"] == {"hello": "world"}
    assert seen[-1]["event_id"] == ev["event_id"]
    assert api.drain_session_events(sid)[-1]["event_id"] == ev["event_id"]
    assert before_state == after_state

    set_session_event_callback(None)


def test_tomorrow_disjoint_dirty_sets_in_same_span_do_not_touch_each_other_and_emit_independently():
    """
    Disjoint dirty-set law:

    A and B are lifecycle datums on the same span. A submit only evaluates A.
    B submit only evaluates B. Their emitted events and lifecycle rows are
    independent.
    """
    calls: Dict[str, int] = {"A": 0, "B": 0}
    seen: list[str] = []
    set_session_event_callback(lambda ev: seen.append(str(ev["name"])))

    def make_widget(datum_id: str):
        def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
            calls[datum_id] += 1
            emit = q.get("emit")
            assert callable(emit)
            emit({"datum": datum_id}, name=f"test.{datum_id}.called")
            return {
                "status": "done",
                "message": {"level": "success", "text": f"{datum_id} done"},
                "state": {"done": datum_id},
            }
        return widget

    register_datum_widget_v1("test.q.tomorrow.disjoint.A", make_widget("A"), overwrite=True)
    register_datum_widget_v1("test.q.tomorrow.disjoint.B", make_widget("B"), overwrite=True)

    fs = {
        "app_form_id": "q.tomorrow.disjoint",
        "datums": [
            {
                "id": "A",
                "title": "A",
                "micros": [_text_micro()],
                "lifecycle": {"widget": "test.q.tomorrow.disjoint.A", "max_reexplosions": 0},
            },
            {
                "id": "B",
                "title": "B",
                "micros": [_text_micro()],
                "lifecycle": {"widget": "test.q.tomorrow.disjoint.B", "max_reexplosions": 0},
            },
        ],
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["A", "B"]}]}],
    }
    _register_step("test.q.tomorrow.disjoint.step", fs)

    api = _api()
    sid, ctx = _start(api, "test.q.tomorrow.disjoint.step")
    assert ctx["current_span"] == "S"

    ctx = api.step_session(sid, fill={"A": {"value": "one"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls == {"A": 1, "B": 0}
    assert seen == ["test.A.called"]

    ctx = api.step_session(sid, fill={"B": {"value": "two"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"A": 1, "B": 1}
    assert seen == ["test.A.called", "test.B.called"]

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "one"
    assert out["form_fills"]["B"]["value"] == "two"

    set_session_event_callback(None)


def test_controller_signal_only_reaches_target_datum_and_reexplodes():
    """
    Controller signal law:

    A higher API may send a signal without fill. The target datum is treated as
    dirty, its lifecycle widget receives q["signal"], and normal reexplode
    machinery handles the result.
    """
    seen: list[Mapping[str, Any]] = []

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(dict(q.get("signal") or {}))
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if q.get("signal_kind") == "refresh":
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "micros": [_text_micro("refreshed")],
                    "lifecycle": {
                        "widget": "test.q.controller.signal.refresh",
                        "max_reexplosions": 2,
                    },
                },
                "fill": {"refreshed": ""},
                "state": {"saw_signal": dict(q.get("signal") or {})},
                "message": {"level": "info", "text": "refreshed"},
            }

        assert "refreshed" in partial
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {"done": True},
        }

    register_datum_widget_v1("test.q.controller.signal.refresh", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": "test.q.controller.signal.refresh",
            "max_reexplosions": 2,
        },
    }
    _register_step("test.q.controller.signal.refresh.step", _multiframespec(datum=datum))

    api = _api()
    sid, ctx = _start(api, "test.q.controller.signal.refresh.step")
    assert ctx["current_span"] == "S"

    ctx = api.step_session(
        sid,
        signal={
            "datum_id": "D",
            "kind": "refresh",
            "info": {"reason": "test"},
        },
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "refreshed" in str(ctx["datum_widget_decls"]["D"])
    assert seen[-1]["kind"] == "refresh"
    assert seen[-1]["info"]["reason"] == "test"
    assert seen[-1]["info"]["source"] == "controller_action"

    ctx = api.step_session(sid, fill={"D": {"refreshed": "yes"}})
    assert ctx["kind"] == "ATCOMPLETION"


def test_controller_fill_plus_signal_targets_only_one_datum_in_multi_datum_span():
    """
    Single-target signal law:

    A fill packet may touch siblings, but only the signaled datum receives the
    custom signal. Siblings receive normal fill behavior and are not invoked
    unless they are themselves touched.
    """
    signals: Dict[str, list[str]] = {"A": [], "B": []}

    def make_widget(datum_id: str):
        def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
            signals[datum_id].append(str(q.get("signal_kind")))
            return {
                "status": "done",
                "message": {"level": "success", "text": f"{datum_id} done"},
                "state": {},
            }
        return widget

    register_datum_widget_v1("test.q.controller.signal.A", make_widget("A"), overwrite=True)
    register_datum_widget_v1("test.q.controller.signal.B", make_widget("B"), overwrite=True)

    fs = {
        "app_form_id": "q.controller.signal.multi",
        "datums": [
            {
                "id": "A",
                "title": "A",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.controller.signal.A",
                    "max_reexplosions": 0,
                },
            },
            {
                "id": "B",
                "title": "B",
                "micros": [_text_micro()],
                "lifecycle": {
                    "widget": "test.q.controller.signal.B",
                    "max_reexplosions": 0,
                },
            },
        ],
        "frames": [{"id": "F", "spans": [{"id": "S", "owns": ["A", "B"]}]}],
    }
    _register_step("test.q.controller.signal.multi.step", fs)

    api = _api()
    sid, _ctx = _start(api, "test.q.controller.signal.multi.step")

    ctx = api.step_session(
        sid,
        fill={
            "A": {"value": "a"},
            "B": {"value": "b"},
        },
        signal={
            "datum_id": "A",
            "kind": "refresh",
            "info": {"n": 1},
        },
    )

    assert ctx["kind"] == "ATCOMPLETION"
    assert signals == {"A": ["refresh"], "B": ["fill"]}

    out = api.get_outputs(sid)
    assert out["form_fills"]["A"]["value"] == "a"
    assert out["form_fills"]["B"]["value"] == "b"


def test_widget_emit_with_record_in_session_queue_false_delivers_strictly_to_callback():
    seen: list[Mapping[str, Any]] = []
    set_session_event_callback(lambda ev: seen.append(dict(ev)))

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        emit = q.get("emit")
        assert callable(emit)
        emit(
            {"secret": "eps-only"},
            name="audit-ins",
            record_in_session_queue=False,
        )
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
        }

    register_datum_widget_v1("test.q.eps_only_callback.widget", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro()],
        "lifecycle": {
            "widget": "test.q.eps_only_callback.widget",
            "max_reexplosions": 0,
        },
    }
    _register_step("test.q.eps_only_callback.step", _multiframespec(datum=datum))

    api = _api()
    sid, _ = _start(api, "test.q.eps_only_callback.step")
    before_seq = api._get(sid).latest_session_event_seq_v1()

    api.step_session(sid, fill={"D": {"value": "ok"}})

    after_seq = api._get(sid).latest_session_event_seq_v1()
    queued = api.drain_session_events(sid)
    assert after_seq == before_seq
    assert queued == []
    assert any(ev["name"] == "audit-ins" and "event_seq" not in ev for ev in seen)

    set_session_event_callback(None)



