# think-backend/tests/wippp/test_datum_lifecycle_semantic_validators_e2e.py

from __future__ import annotations


# think-backend/tests/wippp/test_datum_lifecycle_semantic_validators_e2e.py

from __future__ import annotations

"""
Datum Lifecycle Semantic Validators E2E
=======================================

This sheet documents and proves the interface between:

    - datum shells,
    - micro shells,
    - lifecycle widget input/output packets,
    - mount explosions,
    - fill-time reexplosions,
    - current-effective datum specs,
    - micro validators,
    - macro validators,
    - structural satisfaction,
    - semantic validity,
    - and final commit.

The core mental model
---------------------

A datum is not only a render declaration.

A datum shell is also the semantic contract for the data that may be accepted
for that datum.

Concretely, a datum shell can contain:

    {
        "id": "D",
        "title": "Some datum",
        "micros": [
            {
                "name": "email",
                "type": "text",
                "required": True,
                "validators": [
                    {"path": "pkg.mod:validator_fn", "args": {...}},
                ],
            }
        ],
        "macro_validation_lambdas": [
            {"path": "pkg.mod:whole_datum_validator", "args": {...}},
        ],
        "lifecycle": {...},
    }

The micros describe the datum-local fields.

The micro validators describe semantic rules for one micro value.

The macro validators describe semantic rules for the whole datum fill mapping,
especially cross-micro rules such as:

    - password == confirm_password
    - start_date <= end_date
    - email domain matches selected organization
    - country/state/postal_code are mutually coherent

Validator ownership
-------------------

The active validator set belongs to the concrete datum shell.

The micro-type registry may define which validators are legal for a type, but
runtime validation does not auto-pull validators from the registry.

The separation is:

    micro type registry
        declares the allowed/capable validator universe

    datum shell / micro shell
        declares the active validator subset for this particular datum usage

    runtime transition
        enforces the validators attached to the current-effective datum shell

Therefore:

    If a validator is not attached to the current-effective datum shell, it does
    not run merely because the micro type exists.

    If a validator is attached to the current-effective datum shell, it is part
    of that datum's data contract.

Validator shape
---------------

At the core DatumFillValidator seam, validators may be expressed in several
forms, including dotted paths, direct callables, and shorthand mappings.

For lifecycle E2E datum shells, the cleanest durable/dead-JSON authoring form is:

    {"path": "pkg.mod:validator_fn", "args": {...}}

The accepted dotted alias is:

    {"dotted": "pkg.mod:validator_fn", "args": {...}}

The accepted shorthand is:

    {"pkg.mod:validator_fn": {...}}

Direct callable validators are useful for lower-level unit tests, but they are
not the preferred lifecycle shell authoring style because lifecycle datum
surfaces should remain dead-JSON-like and serializable.

Validator return contract
-------------------------

Every semantic validator must return exactly:

    tuple[bool, str | None]

Examples:

    return True, None
    return False, "must contain @"

Invalid return shapes are system-level contract errors:

    return True
    return (True,)
    return ("yes", {"bad": "shape"})

Those failures are not user validation failures. They mean the validator itself
violated the engine contract.

Structural satisfaction vs semantic validity
--------------------------------------------

The engine deliberately separates two ideas:

    structural satisfaction
        required micros are present and non-blank

    semantic validity
        attached micro and macro validators pass

Structural satisfaction is computed with datum/micro blank semantics:

    - None is blank
    - "" and whitespace-only strings are blank
    - empty list/tuple/dict are blank
    - supported boxed leaf wrappers around blank values are blank

Semantic validity is computed by DatumFillValidator.

This distinction matters because a lifecycle widget receives:

    q["structurally_satisfied"]

That boolean is an observation about required micro presence. It is not a
guarantee that arbitrary semantic rules passed.

However, along the normal manual transition path, the engine semantically
validates the candidate fill before calling the lifecycle widget. Therefore,
when a lifecycle widget is invoked from manual fill transition, its
q["partial_fill"] has already passed the attached partial semantic validator
pass for provided nonblank values.

Transition-time validator pipeline
----------------------------------

For a touched datum on a manual span transition, the engine effectively performs:

    existing fill + submitted fill
        -> candidate datum-local macro fill
        -> partial semantic validation
        -> dead-JSON membrane
        -> datum-widget fill coercion
        -> dead-JSON membrane
        -> structural micros-shell satisfaction
        -> lifecycle widget invocation, if the datum has a lifecycle
        -> full semantic validation before commit, unless forced_done

The partial validation pass uses:

    enforce_required_micros=False
    enforce_micro_lambdas=True
    enforce_macro_lambdas=True

This means:

    - missing required micros are tolerated during partial span progress;
    - provided nonblank micros are still semantically validated;
    - macro validators may run against the candidate mapping when meaningful;
    - invalid provided data blocks before the widget sees it.

The final commit validation pass uses:

    enforce_required_micros=True
    enforce_micro_lambdas=True
    enforce_macro_lambdas=True

This means final accepted form fills must satisfy both:

    - required/blank structural rules;
    - attached semantic validator rules.

Initial datum shells
--------------------

A datum can carry validators before any lifecycle explosion occurs.

The initial multiframespec emitted by a step function may include validators
directly on its datums and micros.

Example:

    {
        "id": "D",
        "title": "Initial email",
        "micros": [
            {
                "name": "email",
                "type": "text",
                "required": True,
                "validators": [
                    {"path": "validators:contains_at", "args": {}},
                ],
            }
        ],
        "macro_validation_lambdas": [
            {"path": "validators:require_domain", "args": {"domain": "stanford.edu"}},
        ],
    }

That initial shell is already a complete validation contract.

No explosion is required to make validators real.

Explosion and current-effective datum shells
--------------------------------------------

A lifecycle widget does not separately register future validators with the
engine.

Instead, when it returns:

    {"status": "reexplode", "datum": replacement_datum, ...}

the replacement datum becomes the current-effective datum shell for the same
logical datum id.

That replacement shell may:

    - add micros,
    - remove micros,
    - rename micros,
    - change required flags,
    - add micro validators,
    - remove micro validators,
    - replace micro validators,
    - add macro validators,
    - remove macro validators,
    - replace macro validators,
    - update lifecycle policy fields,
    - return working fill/prefill overlays for the new shell.

The next manual fill is validated against that replacement shell.

The validator surface is therefore current-effective, not historical and not
unioned.

If the initial shell had:

    value must start with "old:"

and the reexploded shell has:

    confirm must start with "new:"

then after reexplode the authoritative rule is the confirm/new rule. The old
value/old rule no longer applies unless the widget explicitly carries it into
the replacement datum.

Mount explosion
---------------

Mount is the first concrete lifecycle signal before public render, but only when
the datum opts in:

    "lifecycle": {
        "mount_explode": True,
        ...
    }

A mount explosion receives q with:

    q["signal_kind"] == "mount"

or equivalently:

    q["signal"]["kind"] == "mount"

The widget may return a reexploded datum immediately.

That means the first public manual surface the user sees may already be a
replacement datum shell authored by the mount widget.

Therefore mount can install validators before the first user-visible input.

Example run line:

    initial multiframespec datum
        -> mount signal
        -> widget returns replacement datum with mounted_code validator
        -> first render shows mounted_code
        -> submitted mounted_code is validated against replacement shell
        -> widget sees only semantically valid mounted_code values

Fill-time reexplosion
---------------------

A fill-time lifecycle explosion happens after a user submits data for a datum
that has a lifecycle widget.

The run line is:

    submitted fill
        -> partial semantic validation against current datum shell
        -> lifecycle widget called with q["partial_fill"]
        -> widget returns blocked/done/reexplode

If the widget returns blocked:

    - the span remains open;
    - lifecycle state/messages may be recorded;
    - no replacement datum shell is committed.

If the widget returns done:

    - the engine performs full semantic validation before commit;
    - committed form_fills become the durable output surface;
    - lifecycle state/messages may be recorded.

If the widget returns reexplode:

    - the replacement datum becomes current-effective;
    - optional result["fill"] becomes working fill overlay;
    - optional result["prefill"] becomes working prefill overlay;
    - optional result["state"] becomes next lifecycle state;
    - optional result["messages"] are appended subject to bounds;
    - optional result["proc_notes"] is appended subject to bounds;
    - the same logical span remains public until the new shell is satisfied.

How to think about validators along the run lines
-------------------------------------------------

The most important law:

    Validators move with datum shells.

Not with widgets.
Not with spans.
Not with renderer declarations alone.
Not with the micro type registry alone.
Not with historical shells.

More precisely:

    current-effective datum shell
        owns current micros
        owns current micro validators
        owns current macro validators

    build_datum_validator(current_effective_datum)
        creates the validation backend

    transition
        uses that backend before widget invocation and before commit

    widget reexplode result["datum"]
        authors the next backend by authoring the next datum shell

So the correct widget-author mental model is:

    I do not call validators manually.
    I author the next datum shell.
    The engine validates future fills against that shell.

Correct authoring pattern
-------------------------

A clean lifecycle widget that wants the next phase to validate an email should
return:

    return {
        "status": "reexplode",
        "datum": {
            **dict(q["datum"]),
            "title": "Confirm email",
            "micros": [
                {
                    "name": "email",
                    "type": "text",
                    "required": True,
                    "validators": [
                        {"path": "validators:contains_at", "args": {}},
                    ],
                },
                {
                    "name": "confirm",
                    "type": "text",
                    "required": True,
                    "validators": [
                        {"path": "validators:equals", "args": {"expected": "YES"}},
                    ],
                },
            ],
            "macro_validation_lambdas": [
                {
                    "path": "validators:require_domain",
                    "args": {"field": "email", "domain": "stanford.edu"},
                }
            ],
            "lifecycle": {
                **dict(q["datum"].get("lifecycle") or {}),
                "widget": "my.widget.name",
                "max_reexplosions": 2,
            },
        },
        "fill": {"email": "", "confirm": ""},
        "prefill": {"confirm": "YES"},
        "state": {"phase": "confirm_email"},
        "message": {"level": "info", "text": "Please confirm your email."},
    }

Then the next submitted fill:

    {"D": {"email": "bad", "confirm": "YES"}}

fails before the widget sees it, because email does not pass the current
micro validator.

And:

    {"D": {"email": "person@example.com", "confirm": "YES"}}

may still fail before the widget sees it, because the datum-level macro
validator requires the stanford.edu domain.

And:

    {"D": {"email": "person@stanford.edu", "confirm": "YES"}}

passes semantic validation and may be observed by the widget.

What this test sheet proves
---------------------------

This E2E file zooms in on the validator-specific dimension of the datum
lifecycle state machine.

It proves:

    1. Initial datum shells can carry semantic validators.

    2. Plain non-lifecycle datums and lifecycle datums use the same datum/micro
       validator backend.

    3. Invalid semantic data blocks before a lifecycle widget is called.

    4. A reexplode result can inscribe validators into the replacement datum
       shell.

    5. The replacement shell is current-effective and authoritative on the next
       fill.

    6. Old validators are not unioned with new validators unless explicitly
       carried forward.

    7. Micro validators run against individual provided nonblank micro values.

    8. Macro validators run against the whole datum-local macro fill mapping.

    9. Partial validation tolerates missing required micros but still rejects
       invalid provided micros.

    10. Final commit validation requires both structural requiredness and
        semantic validity.

    11. Mount explosion can install validators before first public render.

    12. The durable, pedagogically preferred validator spec form for lifecycle
        datum shells is dotted-path JSON:

            {"path": "pkg.mod:fn", "args": {...}}

        while the accepted dotted alias and shorthand are also covered.

Why this belongs beside the lifecycle sheets
--------------------------------------------

The existing lifecycle sheets prove the mechanics of:

    - blocked,
    - done,
    - reexplode,
    - mount,
    - respan,
    - current-effective state,
    - working fills,
    - undo/redo,
    - runtime write indexing,
    - event emission,
    - sibling dirty-set isolation.

This sheet proves the semantic validation overlay on the same machine.

Together, they define the full datum lifecycle contract:

    A datum lifecycle is a current-effective state machine whose current datum
    shell is both the render/input declaration and the semantic validator
    declaration for future data accepted by that datum.
"""


import sys
import types
from typing import Any, Dict, Mapping

import pytest

from __datomatonTM import register_datum_widget_v1
from _thinkengine._app_table_engine._engine_multiframespec_from_stepfnouts_orgs_fillspans.registry_step_fns import (
    StepFnregistry,
)
from _thinkengine.runme.runme_interactive_w_controller_rolemodulator import get_concrete_session_api


# ---------------------------------------------------------------------------
# Dynamic dotted validator module
# ---------------------------------------------------------------------------

VALIDATOR_MODULE = "test_lifecycle_semantic_validators"
validators_mod = types.ModuleType(VALIDATOR_MODULE)

CALLS: Dict[str, int] = {}


def _bump(name: str) -> None:
    CALLS[name] = CALLS.get(name, 0) + 1


def _leaf(v: Any) -> Any:
    if isinstance(v, Mapping) and "value" in v:
        return v["value"]
    return v


def min_len(value: Any, *, n: int) -> tuple[bool, str | None]:
    _bump("min_len")
    s = str(_leaf(value) or "")
    if len(s) >= int(n):
        return True, None
    return False, f"must have length >= {n}"


def starts_with(value: Any, *, prefix: str) -> tuple[bool, str | None]:
    _bump("starts_with")
    s = str(_leaf(value) or "")
    if s.startswith(str(prefix)):
        return True, None
    return False, f"must start with {prefix!r}"


def equals(value: Any, *, expected: str) -> tuple[bool, str | None]:
    _bump("equals")
    if str(_leaf(value) or "") == str(expected):
        return True, None
    return False, f"must equal {expected!r}"


def contains_at(value: Any) -> tuple[bool, str | None]:
    _bump("contains_at")
    s = str(_leaf(value) or "")
    if "@" in s:
        return True, None
    return False, "must contain @"


def values_match(
    macro: Mapping[str, Any],
    *,
    left: str,
    right: str,
) -> tuple[bool, str | None]:
    _bump("values_match")
    lv = str(_leaf(macro.get(left)) or "")
    rv = str(_leaf(macro.get(right)) or "")
    if lv == rv:
        return True, None
    return False, f"{left} and {right} must match"


def require_domain(
    macro: Mapping[str, Any],
    *,
    field: str,
    domain: str,
) -> tuple[bool, str | None]:
    _bump("require_domain")
    value = str(_leaf(macro.get(field)) or "")
    suffix = "@" + str(domain)
    if value.endswith(suffix):
        return True, None
    return False, f"{field} must end with {suffix}"


validators_mod.min_len = min_len
validators_mod.starts_with = starts_with
validators_mod.equals = equals
validators_mod.contains_at = contains_at
validators_mod.values_match = values_match
validators_mod.require_domain = require_domain
sys.modules[VALIDATOR_MODULE] = validators_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_calls() -> None:
    CALLS.clear()


def _path(fn_name: str) -> str:
    return f"{VALIDATOR_MODULE}:{fn_name}"


def _text_micro(
    name: str = "value",
    *,
    required: bool = True,
    validators: Any = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "name": name,
        "type": "text",
        "required": required,
    }
    if validators is not None:
        out["validators"] = validators
    return out


def _multiframespec(
    *,
    datums: list[Mapping[str, Any]],
    owns: list[str],
    form_id: str,
    span_id: str = "S",
) -> Dict[str, Any]:
    return {
        "app_form_id": form_id,
        "datums": [dict(d) for d in datums],
        "frames": [
            {
                "id": "F",
                "spans": [
                    {
                        "id": span_id,
                        "owns": list(owns),
                    }
                ],
            }
        ],
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
    return get_concrete_session_api(enable_persistence=False)


def _start(api: Any, step_name: str) -> tuple[str, Mapping[str, Any]]:
    st = api.create_VM_session(
        manifest=[
            {
                "public_step_name": "semantic_validator_e2e",
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


def _last_error_text(ctx: Mapping[str, Any], datum_id: str = "D") -> str:
    return str((ctx.get("last_error") or {}).get(datum_id) or ctx.get("last_error") or "")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_initial_datum_shell_micro_validator_blocks_before_lifecycle_widget_runs() -> None:
    """
    A semantic validator attached to the initial datum shell runs before the
    lifecycle widget sees the fill.

    This proves the first datum shell is already validator-capable.
    """

    _reset_calls()
    calls = {"widget": 0}

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["widget"] += 1
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {},
        }

    register_datum_widget_v1("test.semantic.initial.widget", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [
            _text_micro(
                "value",
                validators=[
                    {"path": _path("min_len"), "args": {"n": 3}},
                ],
            )
        ],
        "lifecycle": {
            "widget": "test.semantic.initial.widget",
            "max_reexplosions": 0,
        },
    }

    step_name = "test.semantic.initial.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[datum],
            owns=["D"],
            form_id="semantic.initial",
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "no"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "length >= 3" in _last_error_text(ctx)
    assert CALLS["min_len"] == 1
    assert calls["widget"] == 0

    ctx = api.step_session(sid, fill={"D": {"value": "yes"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert CALLS["min_len"] >= 2
    assert calls["widget"] == 1
    assert api.get_outputs(sid)["form_fills"]["D"]["value"] == "yes"


def test_reexplode_inscribes_micro_and_macro_validators_into_next_current_effective_shell() -> None:
    """
    A widget can return result["datum"] with validators.

    The next fill is validated against that replacement current-effective shell,
    not against an out-of-band widget registry.
    """

    _reset_calls()
    calls = {"widget": 0}

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        calls["widget"] += 1
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "email" in partial and "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": "done"},
                "state": {"phase": "done"},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "title": "Validated email confirmation",
                "micros": [
                    _text_micro(
                        "email",
                        validators=[
                            {"path": _path("contains_at"), "args": {}},
                        ],
                    ),
                    _text_micro(
                        "confirm",
                        validators=[
                            {"path": _path("equals"), "args": {"expected": "YES"}},
                        ],
                    ),
                ],
                "macro_validation_lambdas": [
                    {
                        "path": _path("require_domain"),
                        "args": {"field": "email", "domain": "stanford.edu"},
                    }
                ],
                "lifecycle": {
                    **dict(datum.get("lifecycle") or {}),
                    "widget": "test.semantic.reexplode.widget",
                    "max_reexplosions": 2,
                },
            },
            "fill": {"email": "", "confirm": ""},
            "state": {"phase": "email_confirm"},
            "message": {"level": "info", "text": "now validate email"},
        }

    register_datum_widget_v1("test.semantic.reexplode.widget", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro("value")],
        "lifecycle": {
            "widget": "test.semantic.reexplode.widget",
            "max_reexplosions": 2,
        },
    }

    step_name = "test.semantic.reexplode.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[datum],
            owns=["D"],
            form_id="semantic.reexplode",
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "start"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert calls["widget"] == 1
    assert "email" in str(ctx["datum_widget_decls"]["D"])
    assert "confirm" in str(ctx["datum_widget_decls"]["D"])

    ctx = api.step_session(
        sid,
        fill={"D": {"email": "not-an-email", "confirm": "YES"}},
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "must contain @" in _last_error_text(ctx)
    assert calls["widget"] == 1
    assert CALLS["contains_at"] >= 1

    ctx = api.step_session(
        sid,
        fill={"D": {"email": "person@example.com", "confirm": "YES"}},
    )

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "stanford.edu" in _last_error_text(ctx)
    assert calls["widget"] == 1
    assert CALLS["require_domain"] >= 1

    ctx = api.step_session(
        sid,
        fill={"D": {"email": "person@stanford.edu", "confirm": "YES"}},
    )

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls["widget"] == 2
    out = api.get_outputs(sid)
    assert out["form_fills"]["D"] == {
        "email": "person@stanford.edu",
        "confirm": "YES",
    }


def test_current_effective_reexploded_shell_replaces_old_validator_surface() -> None:
    """
    Initial shell validator and reexploded shell validator are not unioned.

    Before reexplode:
        D.value must start with old:

    After reexplode:
        D.confirm must start with new:

    The old value validator does not apply to the new confirm micro unless the
    widget explicitly carries it forward.
    """

    _reset_calls()

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if "confirm" in partial:
            return {
                "status": "done",
                "message": {"level": "success", "text": "done"},
                "state": {},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [
                    _text_micro(
                        "confirm",
                        validators=[
                            {"path": _path("starts_with"), "args": {"prefix": "new:"}},
                        ],
                    )
                ],
                "lifecycle": {
                    "widget": "test.semantic.current_shell.widget",
                    "max_reexplosions": 1,
                },
            },
            "fill": {"confirm": ""},
            "state": {"phase": "new_shell"},
            "message": {"level": "info", "text": "new shell"},
        }

    register_datum_widget_v1("test.semantic.current_shell.widget", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [
            _text_micro(
                "value",
                validators=[
                    {"path": _path("starts_with"), "args": {"prefix": "old:"}},
                ],
            )
        ],
        "lifecycle": {
            "widget": "test.semantic.current_shell.widget",
            "max_reexplosions": 1,
        },
    }

    step_name = "test.semantic.current_shell.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[datum],
            owns=["D"],
            form_id="semantic.current_shell",
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "bad"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "old:" in _last_error_text(ctx)

    ctx = api.step_session(sid, fill={"D": {"value": "old:ok"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "confirm" in str(ctx["datum_widget_decls"]["D"])

    ctx = api.step_session(sid, fill={"D": {"confirm": "old:wrong-era"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "new:" in _last_error_text(ctx)

    ctx = api.step_session(sid, fill={"D": {"confirm": "new:ok"}})
    assert ctx["kind"] == "ATCOMPLETION"
    assert api.get_outputs(sid)["form_fills"]["D"]["confirm"] == "new:ok"


def test_plain_non_lifecycle_datum_uses_same_micro_and_macro_validator_backend() -> None:
    """
    Validators are datum/micro semantics, not lifecycle-only semantics.

    A plain P datum uses the same build_datum_validator backend and commit seam.
    """

    _reset_calls()

    datum = {
        "id": "D",
        "title": "D",
        "micros": [
            _text_micro("left"),
            _text_micro("right"),
        ],
        "macro_validation_lambdas": [
            {
                "path": _path("values_match"),
                "args": {"left": "left", "right": "right"},
            }
        ],
    }

    step_name = "test.semantic.plain_macro.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[datum],
            owns=["D"],
            form_id="semantic.plain_macro",
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"left": "abc", "right": "xyz"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "must match" in _last_error_text(ctx)
    assert CALLS["values_match"] >= 1

    ctx = api.step_session(sid, fill={"D": {"left": "abc", "right": "abc"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert api.get_outputs(sid)["form_fills"]["D"] == {
        "left": "abc",
        "right": "abc",
    }


def test_partial_validation_validates_provided_micro_but_tolerates_missing_required_sibling_until_commit() -> None:
    """
    Partial transition mode:
        - validates provided nonblank micros;
        - does not fail merely because another required micro is missing.

    Span satisfaction/commit still requires all required micros eventually.
    """

    _reset_calls()

    datum = {
        "id": "D",
        "title": "D",
        "micros": [
            _text_micro(
                "a",
                validators=[
                    {"path": _path("starts_with"), "args": {"prefix": "A-"}},
                ],
            ),
            _text_micro("b"),
        ],
    }

    step_name = "test.semantic.partial.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[datum],
            owns=["D"],
            form_id="semantic.partial",
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"a": "bad"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "A-" in _last_error_text(ctx)
    assert "Missing required micros" not in _last_error_text(ctx)

    ctx = api.step_session(sid, fill={"D": {"a": "A-ok"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "required fields missing" in _last_error_text(ctx)
    assert "A-" not in _last_error_text(ctx)
    assert "D" not in (ctx.get("datum_widget_fills") or {})

    ctx = api.step_session(sid, fill={"D": {"a": "A-ok", "b": "bee"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert api.get_outputs(sid)["form_fills"]["D"] == {
        "a": "A-ok",
        "b": "bee",
    }


def test_mount_explode_can_inscribe_validators_before_first_public_render() -> None:
    """
    Mount explosion may replace the datum before the first public render.

    The first user-visible shell can therefore already contain validators
    authored by the lifecycle widget.
    """

    _reset_calls()
    calls = {"mount": 0, "fill": 0}

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        signal_kind = str(q.get("signal_kind") or dict(q.get("signal") or {}).get("kind") or "fill")
        partial = dict(q.get("partial_fill") or {})

        if signal_kind == "mount":
            calls["mount"] += 1
            return {
                "status": "reexplode",
                "datum": {
                    **datum,
                    "micros": [
                        _text_micro(
                            "mounted_code",
                            validators=[
                                {"path": _path("starts_with"), "args": {"prefix": "M-"}},
                            ],
                        )
                    ],
                    "lifecycle": {
                        "widget": "test.semantic.mount.widget",
                        "mount_explode": True,
                        "max_reexplosions": 1,
                    },
                },
                "fill": {"mounted_code": ""},
                "state": {"mounted": True},
                "message": {"level": "info", "text": "mounted"},
            }

        calls["fill"] += 1
        assert "mounted_code" in partial
        return {
            "status": "done",
            "message": {"level": "success", "text": "done"},
            "state": {"done": True},
        }

    register_datum_widget_v1("test.semantic.mount.widget", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro("value")],
        "lifecycle": {
            "widget": "test.semantic.mount.widget",
            "mount_explode": True,
            "max_reexplosions": 1,
        },
    }

    step_name = "test.semantic.mount.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[datum],
            owns=["D"],
            form_id="semantic.mount",
        ),
    )

    api = _api()
    sid, ctx = _start(api, step_name)

    assert calls == {"mount": 1, "fill": 0}
    assert "mounted_code" in str(ctx["datum_widget_decls"]["D"])

    ctx = api.step_session(sid, fill={"D": {"mounted_code": "bad"}})

    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "M-" in _last_error_text(ctx)
    assert calls == {"mount": 1, "fill": 0}

    ctx = api.step_session(sid, fill={"D": {"mounted_code": "M-ok"}})

    assert ctx["kind"] == "ATCOMPLETION"
    assert calls == {"mount": 1, "fill": 1}
    assert api.get_outputs(sid)["form_fills"]["D"]["mounted_code"] == "M-ok"


def test_validator_spec_variants_path_dotted_and_shorthand_work_on_reexploded_shell() -> None:
    """
    Pedagogical variant sheet.

    E2E lifecycle shells should prefer dead-JSON dotted specs. This test proves
    the accepted dotted variants on a reexploded shell:

        {"path": "...", "args": {...}}
        {"dotted": "...", "args": {...}}
        {"pkg.mod:fn": {...}}
    """

    _reset_calls()

    def widget(q: Mapping[str, Any]) -> Mapping[str, Any]:
        datum = dict(q["datum"])
        partial = dict(q.get("partial_fill") or {})

        if {"a", "b", "c"}.issubset(partial):
            return {
                "status": "done",
                "message": {"level": "success", "text": "done"},
                "state": {},
            }

        return {
            "status": "reexplode",
            "datum": {
                **datum,
                "micros": [
                    _text_micro(
                        "a",
                        validators=[
                            {"path": _path("starts_with"), "args": {"prefix": "A-"}},
                        ],
                    ),
                    _text_micro(
                        "b",
                        validators=[
                            {"dotted": _path("starts_with"), "args": {"prefix": "B-"}},
                        ],
                    ),
                    _text_micro(
                        "c",
                        validators=[
                            {_path("starts_with"): {"prefix": "C-"}},
                        ],
                    ),
                ],
                "lifecycle": {
                    "widget": "test.semantic.variants.widget",
                    "max_reexplosions": 1,
                },
            },
            "fill": {"a": "", "b": "", "c": ""},
            "state": {"phase": "variants"},
            "message": {"level": "info", "text": "variants"},
        }

    register_datum_widget_v1("test.semantic.variants.widget", widget, overwrite=True)

    datum = {
        "id": "D",
        "title": "D",
        "micros": [_text_micro("value")],
        "lifecycle": {
            "widget": "test.semantic.variants.widget",
            "max_reexplosions": 1,
        },
    }

    step_name = "test.semantic.variants.step"
    _register_step(
        step_name,
        _multiframespec(
            datums=[datum],
            owns=["D"],
            form_id="semantic.variants",
        ),
    )

    api = _api()
    sid, _ctx = _start(api, step_name)

    ctx = api.step_session(sid, fill={"D": {"value": "start"}})
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"

    ctx = api.step_session(
        sid,
        fill={"D": {"a": "A-ok", "b": "bad", "c": "C-ok"}},
    )
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "B-" in _last_error_text(ctx)

    ctx = api.step_session(
        sid,
        fill={"D": {"a": "A-ok", "b": "B-ok", "c": "bad"}},
    )
    assert ctx["kind"] == "MANUALFILLNEEDEDSTEP"
    assert "C-" in _last_error_text(ctx)

    ctx = api.step_session(
        sid,
        fill={"D": {"a": "A-ok", "b": "B-ok", "c": "C-ok"}},
    )
    assert ctx["kind"] == "ATCOMPLETION"
    assert api.get_outputs(sid)["form_fills"]["D"] == {
        "a": "A-ok",
        "b": "B-ok",
        "c": "C-ok",
    }





