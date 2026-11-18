from __future__ import annotations

"""
Implementation-agnostic roleless session scripting.

Layering law
------------
- ``api_concrete`` owns concrete App Table session creation, stepping,
  undo/redo, context/output access, persistence, and selected form inspection.
- this module owns only:
    - script iteration;
    - stop/progress control around public API calls;
    - response history shaping;
    - script assertions.

This module must not import from concrete engine packages, parser internals,
``concrete_choices``, or UI/role-aware modules.
"""

from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from _thinkengine._engine_interactive_flow_controller import (
    UserAction,
)
from _thinkengine._engine_interactive_flow_controller.dispatch_UFU_automaton import (
    dispatch_page_flow_controller_automaton,
)
from _thinkengine.runme.runme_interactive_raw import (
    AbstractSessionAPI,
    get_concrete_session_api,
)

from _thinkengine._app_table_engine._engine_runtime_data_book.runtime_reading import (
    get_form_fill_info,
)

from _thinkengine.runme._runme_progress_contract import (
    derived_program_budget_from_api_v1,
    program_progress_signature_v1,
)

from _thinkengine.runme._script_contract import (
    normalize_session_fill_json_v1,
    slim_ctx_for_script_result_v1,
)

_DEFAULT_SESSION_API: "AbstractSessionAPI" = (
    get_concrete_session_api()
)

_STOP_KINDS_DEFAULT = (
    "MANUALFILLNEEDEDSTEP",
    "ATCOMPLETION",
)

_SCRIPT_CONFIG_KEY_V1 = "config"
_SCRIPT_ACTIONS_KEY_V1 = "actions"


@dataclass(frozen=True)
class OfflineScriptRunConfig:
    """
    Optional script-level execution config.

    Defaults preserve the historical offline scripting path exactly:

        use_controller=False

    When true, each STEP/UNDO/REDO is routed through the page-flow controller
    using the same roleless session API as the injected session_ops object.
    """

    use_controller: bool = False


def normalize_offline_script_config_v1(
    raw: Any,
) -> OfflineScriptRunConfig:
    if raw is None:
        return OfflineScriptRunConfig()

    if not isinstance(raw, Mapping):
        raise TypeError("script config must be a mapping")

    allowed = {"use_controller"}
    unknown = sorted(
        str(k)
        for k in raw.keys()
        if str(k) not in allowed
    )
    if unknown:
        raise ValueError(
            "unknown offline script config keys: "
            f"{unknown!r}; allowed={sorted(allowed)!r}"
        )

    return OfflineScriptRunConfig(
        use_controller=bool(raw.get("use_controller", False)),
    )


def normalize_offline_script_spec_v1(
    script: Any,
) -> tuple[OfflineScriptRunConfig, list[Mapping[str, Any]]]:
    """
    Normalize the public script parameter.

    Back-compatible shape:

        [{"action": "STEP"}, ...]

    New configured shape:

        {
            "config": {"use_controller": true},
            "actions": [{"action": "STEP"}, ...],
        }

    The config is deliberately script-level, not an action. It is not counted
    in script_count and is not visible to action loops.
    """
    if isinstance(script, Mapping):
        raw_config = script.get(_SCRIPT_CONFIG_KEY_V1)
        raw_actions = script.get(_SCRIPT_ACTIONS_KEY_V1, [])

        config = normalize_offline_script_config_v1(raw_config)

        if not isinstance(raw_actions, Sequence) or isinstance(
            raw_actions,
            (str, bytes, bytearray),
        ):
            raise TypeError("script.actions must be a sequence of mappings")

        raw_actions_list = list(raw_actions)
        actions = [
            item
            for item in raw_actions_list
            if isinstance(item, Mapping)
        ]

        if len(actions) != len(raw_actions_list):
            raise TypeError("every script action must be a mapping")

        return config, actions

    if isinstance(script, Sequence) and not isinstance(
        script,
        (str, bytes, bytearray),
    ):
        raw_actions_list = list(script)
        actions = [
            item
            for item in raw_actions_list
            if isinstance(item, Mapping)
        ]

        if len(actions) != len(raw_actions_list):
            raise TypeError("every script action must be a mapping")

        return OfflineScriptRunConfig(), actions

    raise TypeError(
        "script must be either a sequence of action mappings or "
        "{'config': ..., 'actions': [...]}"
    )


def _pp(
    obj: Any,
) -> str:
    try:
        import json

        return json.dumps(
            obj,
            indent=2,
            sort_keys=True,
            default=str,
        )
    except Exception:
        return repr(obj)


def _startswith_check(
    actual: Any,
    prefix: str,
) -> bool:
    return (
        isinstance(actual, str)
        and actual.startswith(prefix)
    )


def _contains_all(
    hay: Iterable[Any],
    needles: Sequence[Any],
) -> bool:
    haystack = list(hay)
    return all(
        needle in haystack
        for needle in needles
    )


def _match_value(
    actual: Any,
    expected: Any,
) -> Tuple[bool, str]:
    if (
        isinstance(expected, Mapping)
        and "startswith" in expected
    ):
        prefix = str(expected["startswith"])
        ok = _startswith_check(
            actual,
            prefix,
        )
        return (
            ok,
            "expected startswith "
            f"{prefix!r}, got {actual!r}",
        )

    ok = actual == expected
    return (
        ok,
        f"expected {expected!r}, got {actual!r}",
    )


def _match_subset_shallow(
    actual: Any,
    expected_subset: Mapping[str, Any],
    *,
    path: str,
) -> List[str]:
    if not isinstance(actual, Mapping):
        return [
            f"{path}: expected mapping, "
            f"got {type(actual).__name__}"
        ]

    errors: List[str] = []

    for key, expected_value in expected_subset.items():
        if key not in actual:
            errors.append(
                f"{path}.{key}: missing key"
            )
            continue

        ok, message = _match_value(
            actual.get(key),
            expected_value,
        )

        if not ok:
            errors.append(
                f"{path}.{key}: {message}"
            )

    return errors


def _match_subset_deep(
    actual: Any,
    expected: Any,
    *,
    path: str,
) -> List[str]:
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return [
                f"{path}: expected mapping, "
                f"got {type(actual).__name__}"
            ]

        errors: List[str] = []

        for key, expected_value in expected.items():
            if key not in actual:
                errors.append(
                    f"{path}.{key}: missing key"
                )
                continue

            errors.extend(
                _match_subset_deep(
                    actual.get(key),
                    expected_value,
                    path=f"{path}.{key}",
                )
            )

        return errors

    ok, message = _match_value(
        actual,
        expected,
    )

    return (
        []
        if ok
        else [f"{path}: {message}"]
    )


def _ctx_fingerprint(
    ctx: Mapping[str, Any],
) -> str:
    return _pp(
        program_progress_signature_v1(ctx)
    )


def _prune_snapshot_like_history_values(
    obj: Any,
) -> Any:
    """
    Remove large/spec-snapshot values from slim public runner history.

    Live session ctx may expose "multiframespec" for inspection/debug helpers.
    Runner history with keep_full_history=False must not retain repeated form
    snapshots, because long Q/reexplode scripts should scale with public
    actions, not accumulated snapshot payload size.

    This is deliberately applied only after slim_ctx_for_script_result_v1().
    It does not change live ctx returned to callers.
    """
    if isinstance(obj, Mapping):
        out: Dict[str, Any] = {}

        for key, value in obj.items():
            key_str = str(key)

            # The scale test intentionally searches keys and values for this
            # substring. Any such key in history means a full/spec-like snapshot
            # escaped the slimming wall.
            if "multiframespec" in key_str:
                continue

            # Be defensive around common aliases if lower layers add them.
            if key_str in {
                "forms_emitted",
                "forms_emitted_order",
                "pending_multiframespec",
                "pending_form",
                "multiframespec_ref",
            }:
                continue

            out[key] = _prune_snapshot_like_history_values(value)

        return out

    if isinstance(obj, list):
        return [
            _prune_snapshot_like_history_values(item)
            for item in obj
        ]

    if isinstance(obj, tuple):
        return tuple(
            _prune_snapshot_like_history_values(item)
            for item in obj
        )

    if isinstance(obj, set):
        return {
            _prune_snapshot_like_history_values(item)
            for item in obj
        }

    if isinstance(obj, frozenset):
        return frozenset(
            _prune_snapshot_like_history_values(item)
            for item in obj
        )

    return obj


def _ctx_history_slim(
    ctx: Mapping[str, Any],
) -> Dict[str, Any]:
    slim = slim_ctx_for_script_result_v1(ctx)

    if not isinstance(slim, Mapping):
        return {}

    pruned = _prune_snapshot_like_history_values(slim)

    return (
        dict(pruned)
        if isinstance(pruned, Mapping)
        else {}
    )


def _program_budget_from_api_v1(
    api: "AbstractSessionAPI",
    session_id: str,
    *,
    floor: int = 32,
    per_program_step: int = 6,
    cap: int = 2048,
) -> int:
    return derived_program_budget_from_api_v1(
        api=api,
        session_id=session_id,
        default_max_steps=floor,
        floor=floor,
        per_program_step=per_program_step,
        cap=cap,
        reject_excessive_explicit=False,
    )


@dataclass
class SessionScriptedRunResultHeadless:
    session_id: str
    ctx: Dict[str, Any]
    history: List[Dict[str, Any]]
    config: OfflineScriptRunConfig


class SessionProgramScriptedHeadlessRunner:
    """
    Drive one session through the roleless abstract session contract.
    """

    def __init__(
        self,
        session_id: str,
        *,
        api: Optional["AbstractSessionAPI"] = None,
        keep_full_history: bool = False,
        use_controller: bool = False,
    ) -> None:
        self.session_id = str(session_id)
        self.api = (
            api
            if api is not None
            else _DEFAULT_SESSION_API
        )
        self.keep_full_history = bool(
            keep_full_history
        )
        self.use_controller = bool(use_controller)
        self.history: List[Dict[str, Any]] = []

    def _history_ctx(
        self,
        ctx: Mapping[str, Any],
    ) -> Dict[str, Any]:
        if self.keep_full_history:
            return dict(ctx)

        return _ctx_history_slim(ctx)

    def ctx(
        self,
    ) -> Dict[str, Any]:
        ctx = self.api.get_session_context(
            self.session_id
        )

        if not isinstance(ctx, dict):
            raise TypeError(
                "get_session_context returned "
                f"{type(ctx).__name__}, "
                "expected dict"
            )

        return ctx

    def step(
        self,
        *,
        fill: Optional[Dict[str, Any]] = None,
        signal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self.use_controller:
            return self._controller_dispatch(
                action=UserAction.STEP,
                fill=fill,
                signal=signal,
            )

        normalized_fill = normalize_session_fill_json_v1(
            fill
        )
        ctx = self.api.step_session(
            self.session_id,
            fill=normalized_fill,
            signal=(
                dict(signal)
                if isinstance(signal, Mapping)
                else None
            ),
        )

        if not isinstance(ctx, dict):
            raise TypeError(
                "step_session returned "
                f"{type(ctx).__name__}, "
                "expected dict"
            )

        self.history.append(
            {
                "mode": "ENGINE",
                "action": "STEP",
                "ctx": self._history_ctx(ctx),
            }
        )

        return ctx

    def _controller_dispatch(
        self,
        *,
        action: UserAction,
        fill: Optional[Dict[str, Any]] = None,
        signal: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute one script action through the real page-flow controller.

        The script runner does not reimplement controller normalization,
        routing, or action-packet semantics. It passes the script fill/signal
        to the controller as user-facing values and unwraps packet["ctx"] only
        so existing script assertions continue to inspect the same ctx shape.
        """
        packet = dispatch_page_flow_controller_automaton(
            session_id=self.session_id,
            action=action,
            user_fill=(
                dict(fill)
                if isinstance(fill, Mapping)
                else {}
            ),
            user_signal=(
                dict(signal)
                if isinstance(signal, Mapping)
                else None
            ),
            session_ops=self.api,
        )

        if isinstance(packet, str):
            raise RuntimeError(packet)

        if not isinstance(packet, Mapping):
            raise TypeError(
                "controller dispatch returned "
                f"{type(packet).__name__}, expected mapping"
            )

        ctx = packet.get("ctx")
        if not isinstance(ctx, dict):
            raise TypeError(
                "controller dispatch packet missing dict ctx; "
                f"got {type(ctx).__name__}"
            )

        self.history.append(
            {
                "mode": "CONTROLLER",
                "action": action.name,
                "event_kind": packet.get("event_kind"),
                "ui_mode": packet.get("ui_mode"),
                "ctx": self._history_ctx(ctx),
            }
        )

        return ctx

    def undo(
        self,
    ) -> Dict[str, Any]:
        if self.use_controller:
            return self._controller_dispatch(
                action=UserAction.UNDO,
            )

        ctx = self.api.undo_last_step(
            self.session_id
        )

        if not isinstance(ctx, dict):
            raise TypeError(
                "undo_last_step returned "
                f"{type(ctx).__name__}, "
                "expected dict"
            )

        self.history.append(
            {
                "mode": "ENGINE",
                "action": "UNDO",
                "ctx": self._history_ctx(ctx),
            }
        )

        return ctx

    def redo(
        self,
    ) -> Dict[str, Any]:
        if self.use_controller:
            return self._controller_dispatch(
                action=UserAction.REDO,
            )

        ctx = self.api.redo_last_step(
            self.session_id
        )

        if not isinstance(ctx, dict):
            raise TypeError(
                "redo_last_step returned "
                f"{type(ctx).__name__}, "
                "expected dict"
            )

        self.history.append(
            {
                "mode": "ENGINE",
                "action": "REDO",
                "ctx": self._history_ctx(ctx),
            }
        )

        return ctx

    def step_until_stop(
        self,
        *,
        fill: Optional[Dict[str, Any]] = None,
        signal: Optional[Dict[str, Any]] = None,
        stop_kinds: Sequence[str] = _STOP_KINDS_DEFAULT,
        max_iters: Optional[int] = None,
    ) -> Dict[str, Any]:
        stop_set = {
            str(kind)
            for kind in stop_kinds
        }
        budget = (
            int(max_iters)
            if max_iters is not None
            else _program_budget_from_api_v1(
                self.api,
                self.session_id,
            )
        )

        ctx = self.ctx()
        last_fingerprint = _ctx_fingerprint(ctx)
        repeats = 0

        for _ in range(max(1, budget)):
            kind = str(ctx.get("kind") or "")

            if kind in stop_set:
                return ctx

            if kind == "MANUALFILLNEEDEDSTEP":
                if fill is not None:
                    ctx = self.step(
                        fill=fill,
                        signal=signal,
                    )
                    fill = None
                    signal = None
                elif "MANUALFILLNEEDEDSTEP" in stop_set:
                    return ctx
                else:
                    raise RuntimeError(
                        "step_until_stop encountered "
                        "MANUALFILLNEEDEDSTEP without a fill "
                        "and without that kind in stop_kinds"
                    )
            else:
                ctx = self.step(
                    fill=None,
                    signal=signal,
                )
                signal = None

            fingerprint = _ctx_fingerprint(ctx)

            if fingerprint == last_fingerprint:
                repeats += 1

                if repeats >= 2:
                    raise RuntimeError(
                        "step_until_stop detected no progress"
                        "\n\nLast context:\n"
                        f"{_pp(ctx)}"
                    )
            else:
                repeats = 0
                last_fingerprint = fingerprint

        raise RuntimeError(
            "step_until_stop exceeded "
            f"max_iters={budget}"
            "\n\nLast context:\n"
            f"{_pp(ctx)}"
        )

    def redo_until_stop(
        self,
        stop_kinds: Sequence[str] = _STOP_KINDS_DEFAULT,
        *,
        budget: Optional[int] = None,
    ) -> Dict[str, Any]:
        stop_set = {
            str(kind)
            for kind in stop_kinds
        }
        limit = (
            int(budget)
            if budget is not None
            else _program_budget_from_api_v1(
                self.api,
                self.session_id,
            )
        )

        ctx = self.redo()
        last_fingerprint = _ctx_fingerprint(ctx)
        repeats = 0

        for _ in range(max(1, limit)):
            kind = str(ctx.get("kind") or "")

            if kind in stop_set:
                return ctx

            ctx = self.step(fill=None)
            fingerprint = _ctx_fingerprint(ctx)

            if fingerprint == last_fingerprint:
                repeats += 1

                if repeats >= 2:
                    raise RuntimeError(
                        "redo_until_stop detected no progress"
                        "\n\nLast context:\n"
                        f"{_pp(ctx)}"
                    )
            else:
                repeats = 0
                last_fingerprint = fingerprint

        raise RuntimeError(
            "redo_until_stop exceeded "
            f"budget={limit}"
            "\n\nLast context:\n"
            f"{_pp(ctx)}"
        )

    def undo_until_stop(
        self,
        stop_kinds: Optional[Sequence[str]] = None,
        *,
        budget: int = 10_000,
    ) -> Dict[str, Any]:
        """
        Undo at least one API operation and stop at a requested boundary.

        When a manual-fill state is not a requested stop, the runner still
        avoids consuming the entire manual history in one call. From completion,
        it may cross one immediately exposed manual-fill boundary to unwind the
        final committed fill.
        """
        stop_set = {
            str(kind)
            for kind in (
                stop_kinds
                or (
                    "MANUALFILLNEEDEDSTEP",
                    "ATSTART",
                    "ATCOMPLETION",
                )
            )
        }
        manual_is_stop = (
            "MANUALFILLNEEDEDSTEP"
            in stop_set
        )

        before = self.ctx()
        before_kind = str(
            before.get("kind") or ""
        )

        if before_kind == "ATSTART":
            return before

        ctx = self.undo()

        for index in range(max(1, int(budget))):
            kind = str(ctx.get("kind") or "")

            if (
                kind == "ATSTART"
                or kind in stop_set
            ):
                return ctx

            if (
                kind == "MANUALFILLNEEDEDSTEP"
                and not manual_is_stop
            ):
                if (
                    before_kind == "ATCOMPLETION"
                    and index == 0
                ):
                    ctx = self.undo()
                    continue

                return ctx

            ctx = self.undo()

        raise AssertionError(
            "undo_until_stop exceeded "
            f"budget={budget}; "
            f"last_context={ctx!r}"
        )

    def assert_ctx(
        self,
        ctx: Dict[str, Any],
        expect: Mapping[str, Any],
    ) -> None:
        errors: List[str] = []

        if "kind" in expect:
            ok, message = _match_value(
                ctx.get("kind"),
                expect["kind"],
            )

            if not ok:
                errors.append(f"kind: {message}")

        if "step" in expect:
            errors.extend(
                _match_subset_shallow(
                    ctx.get("step") or {},
                    expect["step"],
                    path="step",
                )
            )

        if "current_span" in expect:
            ok, message = _match_value(
                ctx.get("current_span"),
                expect["current_span"],
            )

            if not ok:
                errors.append(
                    f"current_span: {message}"
                )

        if "form_id" in expect:
            ok, message = _match_value(
                ctx.get("form_id"),
                expect["form_id"],
            )

            if not ok:
                errors.append(f"form_id: {message}")

        if "cursor_subset" in expect:
            errors.extend(
                _match_subset_deep(
                    ctx.get("cursor") or {},
                    expect["cursor_subset"],
                    path="cursor",
                )
            )

        if "datum_widgets_on_this_span_contains" in expect:
            required = list(
                expect.get("datum_widgets_on_this_span_contains")
                or []
            )
            actual = list(
                ctx.get("datum_widgets_on_this_span") or []
            )

            if not _contains_all(actual, required):
                errors.append(
                    "datum_widgets_on_this_span_contains: "
                    f"expected {required!r} "
                    f"in {actual!r}"
                )

        if "last_error_has_keys" in expect:
            required = list(
                expect.get("last_error_has_keys")
                or []
            )
            last_error = ctx.get("last_error") or {}
            actual = (
                list(last_error.keys())
                if isinstance(last_error, Mapping)
                else []
            )

            if not _contains_all(actual, required):
                errors.append(
                    "last_error_has_keys: "
                    f"expected {required!r} "
                    f"in {actual!r}"
                )

        if "keys_present" in expect:
            required = list(
                expect.get("keys_present") or []
            )
            missing = [
                key
                for key in required
                if key not in ctx
            ]

            if missing:
                errors.append(
                    "keys_present: missing "
                    f"{missing!r}"
                )

        if "globals_subset" in expect:
            expected_globals = (
                expect.get("globals_subset") or {}
            )
            actual_globals = ctx.get("globals") or {}

            if not isinstance(actual_globals, Mapping):
                errors.append(
                    "globals_subset: "
                    "ctx.globals is not a mapping"
                )
            elif isinstance(expected_globals, Mapping):
                errors.extend(
                    _match_subset_deep(
                        actual_globals,
                        expected_globals,
                        path="globals",
                    )
                )

        if errors:
            raise AssertionError(
                "headless session assertion failed:\n"
                + "\n".join(
                    f"- {error}"
                    for error in errors
                )
                + "\n\nCTX:\n"
                + _pp(ctx)
                + "\n\nEXPECT:\n"
                + _pp(expect)
            )

    def _build_state_view_for_helpers(
        self,
        ctx: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """
        Build the state view expected by the façade-selected form inspection
        helper.

        Public outputs provide accumulated prefill and manual-fill state. The
        current context may additionally expose the active emitted multiframespec.

        When the requested form is not current, snapshot export is used only
        when the selected session API supports it. Snapshot access remains an
        optional extension, not a requirement of the abstract roleless contract.
        """
        outputs = self.api.get_outputs(
            self.session_id
        )

        form_prefills = (
            outputs.get("form_prefills") or {}
            if isinstance(outputs, Mapping)
            else {}
        )
        form_fills = (
            outputs.get("form_fills") or {}
            if isinstance(outputs, Mapping)
            else {}
        )

        forms_emitted: Dict[str, Any] = {}

        current_form_id = ctx.get("form_id")
        current_multiframespec = ctx.get("multiframespec")

        if (
            isinstance(current_form_id, str)
            and current_form_id
            and isinstance(current_multiframespec, Mapping)
        ):
            forms_emitted[current_form_id] = dict(
                current_multiframespec
            )
        else:
            exporter = getattr(
                self.api,
                "export_session_snapshot",
                None,
            )

            if callable(exporter):
                try:
                    snapshot = exporter(
                        self.session_id
                    )
                except Exception:
                    snapshot = {}

                state = (
                    snapshot.get("state")
                    if isinstance(snapshot, Mapping)
                    else None
                )
                emitted = (
                    state.get("forms_emitted")
                    if isinstance(state, Mapping)
                    else None
                )

                if isinstance(emitted, Mapping):
                    forms_emitted = {
                        str(key): dict(value)
                        for key, value in emitted.items()
                        if isinstance(value, Mapping)
                    }

        return {
            "forms_emitted": forms_emitted,
            "form_prefills": (
                dict(form_prefills)
                if isinstance(form_prefills, Mapping)
                else {}
            ),
            "form_fills": (
                dict(form_fills)
                if isinstance(form_fills, Mapping)
                else {}
            ),
        }

    def assert_form(
        self,
        ctx: Mapping[str, Any],
        form_expect: Mapping[str, Any],
    ) -> None:
        """
        Assert enriched form state through the façade-selected inspection helper.

        Supported expectations:

        - ``datum_sources`` for source-provenance flags;
        - ``micro_merged`` for merged values addressed as ``DATUM.micro``;
        - ``datum_subset`` for arbitrary enriched datum subsets.
        """
        requested_form_id = form_expect.get(
            "form_id",
            "CURRENT",
        )
        current_form_id = ctx.get("form_id")

        if requested_form_id == "CURRENT":
            if (
                not isinstance(current_form_id, str)
                or not current_form_id
            ):
                raise AssertionError(
                    "form_expect requested CURRENT, "
                    "but ctx.form_id was "
                    f"{current_form_id!r}"
                )

            form_id = current_form_id
        else:
            form_id = str(requested_form_id)

        state_view = self._build_state_view_for_helpers(
            ctx
        )
        info = get_form_fill_info(
            state_view,
            form_id,
        )
        datums = info.get("datums") or {}

        if not isinstance(datums, Mapping):
            raise AssertionError(
                "selected form inspection helper "
                "returned invalid datums for form "
                f"{form_id!r}: "
                f"{_pp(info)}"
            )

        errors: List[str] = []

        datum_sources = form_expect.get(
            "datum_sources"
        )

        if isinstance(datum_sources, Mapping):
            for field_id, expected_sources in datum_sources.items():
                datum = datums.get(str(field_id))

                if not isinstance(datum, Mapping):
                    errors.append(
                        "datum_sources."
                        f"{field_id}: datum missing"
                    )
                    continue

                sources = datum.get("sources") or {}

                if not isinstance(sources, Mapping):
                    errors.append(
                        "datum_sources."
                        f"{field_id}: sources missing or invalid"
                    )
                    continue

                errors.extend(
                    _match_subset_deep(
                        sources,
                        expected_sources,
                        path=(
                            "datum_sources."
                            f"{field_id}"
                        ),
                    )
                )

        micro_merged = form_expect.get(
            "micro_merged"
        )

        if isinstance(micro_merged, Mapping):
            for key, expected_value in micro_merged.items():
                qualified_key = str(key)

                if "." in qualified_key:
                    field_id, micro_name = qualified_key.split(
                        ".",
                        1,
                    )
                else:
                    field_id = qualified_key
                    micro_name = "value"

                datum = datums.get(field_id)

                if not isinstance(datum, Mapping):
                    errors.append(
                        "micro_merged."
                        f"{qualified_key}: datum missing"
                    )
                    continue

                micros = datum.get("micros") or {}

                if not isinstance(micros, Mapping):
                    errors.append(
                        "micro_merged."
                        f"{qualified_key}: micros missing or invalid"
                    )
                    continue

                micro = micros.get(micro_name)

                if not isinstance(micro, Mapping):
                    errors.append(
                        "micro_merged."
                        f"{qualified_key}: micro missing"
                    )
                    continue

                ok, message = _match_value(
                    micro.get("merged"),
                    expected_value,
                )

                if not ok:
                    errors.append(
                        "micro_merged."
                        f"{qualified_key}: "
                        f"{message}"
                    )

        datum_subset = form_expect.get(
            "datum_subset"
        )

        if isinstance(datum_subset, Mapping):
            for field_id, expected_datum in datum_subset.items():
                datum = datums.get(str(field_id))

                if not isinstance(datum, Mapping):
                    errors.append(
                        "datum_subset."
                        f"{field_id}: datum missing"
                    )
                    continue

                errors.extend(
                    _match_subset_deep(
                        datum,
                        expected_datum,
                        path=(
                            "datum_subset."
                            f"{field_id}"
                        ),
                    )
                )

        if errors:
            raise AssertionError(
                "headless form assertion failed:\n"
                + "\n".join(
                    f"- {error}"
                    for error in errors
                )
                + "\n\nFORM_INFO:\n"
                + _pp(info)
                + "\n\nFORM_EXPECT:\n"
                + _pp(form_expect)
            )

    def run_script(
        self,
        script: Any,
    ) -> SessionScriptedRunResultHeadless:
        config, actions = normalize_offline_script_spec_v1(script)

        # Script-level config wins, so callers can choose the scripting artery
        # inside the script payload itself.
        self.use_controller = bool(config.use_controller)

        ctx = self.ctx()

        for index, spec in enumerate(actions):
            action = str(
                spec.get("action") or "STEP"
            ).upper()
            until_stop = bool(
                spec.get("until_stop", False)
            )
            stop_kinds = spec.get("stop_kinds")
            fill = spec.get("fill")
            signal = spec.get("signal")
            expect = spec.get("expect")
            form_expect = spec.get("form_expect")

            normalized_stop_kinds = (
                tuple(stop_kinds)
                if isinstance(stop_kinds, (list, tuple))
                else _STOP_KINDS_DEFAULT
            )
            normalized_fill = (
                fill
                if isinstance(fill, dict)
                else None
            )
            normalized_signal = (
                signal
                if isinstance(signal, dict)
                else None
            )

            if action == "STEP":
                ctx = (
                    self.step_until_stop(
                        fill=normalized_fill,
                        signal=normalized_signal,
                        stop_kinds=normalized_stop_kinds,
                    )
                    if until_stop
                    else self.step(
                        fill=normalized_fill,
                        signal=normalized_signal,
                    )
                )
            elif action == "UNDO":
                ctx = (
                    self.undo_until_stop(
                        stop_kinds=normalized_stop_kinds
                    )
                    if until_stop
                    else self.undo()
                )
            elif action == "REDO":
                ctx = (
                    self.redo_until_stop(
                        stop_kinds=normalized_stop_kinds
                    )
                    if until_stop
                    else self.redo()
                )
            else:
                raise ValueError(
                    f"script[{index}]: "
                    f"unknown action {action!r}"
                )

            if isinstance(expect, Mapping):
                self.assert_ctx(
                    ctx,
                    expect,
                )

            if isinstance(form_expect, Mapping):
                self.assert_form(
                    ctx,
                    form_expect,
                )

        return SessionScriptedRunResultHeadless(
            session_id=self.session_id,
            ctx=ctx,
            history=list(self.history),
            config=OfflineScriptRunConfig(
                use_controller=self.use_controller,
            ),
        )


def run_session_against_script_headless(
    *,
    manifest: Any,
    initial_parameter_overrides: Optional[Dict[str, Any]] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
    script: Any,
    api: Optional["AbstractSessionAPI"] = None,
    keep_full_history: bool = False,
) -> SessionScriptedRunResultHeadless:
    config, actions = normalize_offline_script_spec_v1(script)

    session_api = (
        api
        if api is not None
        else _DEFAULT_SESSION_API
    )

    created = session_api.create_VM_session(
        manifest=manifest,
        initial_parameter_overrides=dict(initial_parameter_overrides or {}),
        session_metadata=dict(session_metadata or {}),
        get_map=False,
    )

    if isinstance(created, Mapping):
        state = created
    elif (
        isinstance(created, tuple)
        and created
        and isinstance(created[0], Mapping)
    ):
        state = created[0]
    else:
        raise TypeError(
            "create_VM_session must return "
            "a session-state mapping or "
            "(session-state, program-map)"
        )

    session_id = str(
        state["session_id"]
    )

    runner = SessionProgramScriptedHeadlessRunner(
        session_id,
        api=session_api,
        keep_full_history=keep_full_history,
        use_controller=config.use_controller,
    )

    return runner.run_script(
        {
            "config": {
                "use_controller": config.use_controller,
            },
            "actions": actions,
        }
    )


__all__ = [
    "OfflineScriptRunConfig",
    "SessionProgramScriptedHeadlessRunner",
    "SessionScriptedRunResultHeadless",
    "normalize_offline_script_config_v1",
    "normalize_offline_script_spec_v1",
    "run_session_against_script_headless",
]