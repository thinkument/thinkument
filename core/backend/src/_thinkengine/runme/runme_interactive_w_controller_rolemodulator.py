from __future__ import annotations

"""
Concrete App Table role-aware interaction façade.

This module re-exports the complete generic roleless App Table session API and
owns the concrete role-aware UI interaction layer.

Layering law
------------
- The App Table session engine and generic concrete session API remain roleless.
- App Table treats non-structural span/datum role keys as opaque extensions.
- This concrete UI interaction layer interprets viewer-role extensions only
  through the role-modulation façade.
- Role-aware public grammar exists only at:
    - create_interactive_session(...)
    - get_current_ui_state(...)
    - dispatch_ui_action(...)
    - render_current_ui_state(...)
- The page-flow controller receives a role-bound liaison whose outward operation
  signatures remain roleless.

Role modulation boundary
------------------------
This interaction layer imports exactly one role-modulation façade symbol:

    role_modulation

All lower-level role mechanics live behind:

    _thinksessions.libs_read_write_augmented.rolebasedRWmodulatorTM.obfuscation_api

The main interaction layer uses only the stable façade methods:

    build_interactive_session_metadata(...)
    role_modulation.modulate(...)
    role_modulation.assert_submission_allowed(...)

Role modulation formalism
-------------------------
For one renderer-facing UI context vector ``U`` and one viewing role ``r``:

    D_s = active-span ordered datum ids
    R(d) = resolved role-set for datum d

Resolution law:

    datum.roles / datum.role override span.roles / span.role
    span.roles / span.role are defaults for owned datums
    no roles means unguarded

Read mismatch law:

    read_roles(r) = {r} ∪ roles[r].read_roles

    mismatch(r, d) = True iff
        R(d) is non-empty
        and R(d) ∩ read_roles(r) is empty

Write law:

    write_allowed(r, d) = True iff
        R(d) is empty
        or r ∈ R(d)

    roles[r].read_roles never grants write power.

Write-implies-read corollary:

    write_allowed(r, d) implies read_allowed(r, d)

because every named role reads itself:

    r ∈ read_roles(r)

Policy law
----------
Final role mismatch policy shape:

    {
        "default": "redacted",
        "role_modes": {
            "maker": "redacted",
            "reviewer": "redacted",
        },
    }

Deprecated ambiguous policy such as ``{"on_mismatch": "error"}`` and flat
role-mode policy such as ``{"maker": "redacted"}`` are rejected by the
role-modulation surface.

Security/use law
----------------
The client supplies the viewer role at the interactive boundary. Clients are
expected to guard their own handles, but the backend still guarantees:

- returned U/ctx is already role-modulated;
- mismatched datum information is obfuscated before frontend rendering;
- mismatched datums are removed from fillable ctx memberships;
- mismatched fill/signal submissions are rejected before calling the roleless
  backend.
"""

from typing import Any, Dict, Mapping, Optional, Tuple

from _thinksessions.libs_read_write_augmented.rolebasedRWmodulatorTM.obfuscation_api import role_modulation
from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    EXPLOSION_EVENTS_CALLBACK_KEY,
)
from _thinkengine.runme.runme_interactive_raw import (
    AbstractSessionAPI,
    AppTableParserValidatorError,
    checkpoint_session_runtime,
    CreateSessionReturn,
    StepFnregistry,
    create_VM_session,
    create_VM_session_from_program,
    drain_session_events,
    emit_session_event,
    evict_session_runtime,
    get_concrete_session_api,
    get_form_fill_info,
    get_latest_session_event_seq,
    get_outputs,
    get_runtime_write_index_summary,
    get_session_context,
    get_session_events,
    parse_and_validate_app_table,
    query_runtime_writes,
    redo_last_step,
    register_step_fn,
    step_session,
    undo_last_step,
)
from _thinkengine._engine_interactive_flow_controller import (
    UIMode,
    UserAction,
)
from _thinksessions.sesh_metadata.sesh_metadata_surface import (
    build_interactive_session_metadata,
    coerce_session_metadata,
)


class AppTableInteractiveSessionAPI:
    """
    Single concrete App Table role-aware interaction API.

    This class owns:
      - role-aware session creation orchestration;
      - role-bound page-flow-controller liaison behavior;
      - highest public interactive operations.

    Exact role interpretation, datum-level mismatch formalism, policy
    validation, read-side obfuscation, and write-side submission checks live
    behind ``__context_obfuscation.obfuscation_api.role_modulation``.
    """

    @staticmethod
    def build_metadata(
        ui_opts: Mapping[str, Any] | Any,
        *,
        roles: Optional[Mapping[str, Any]],
        role_mismatch_policy: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """
        Translate interactive role grammar into generic session metadata.

        The resulting metadata is still passed through the ordinary roleless
        ``AbstractSessionAPI.create_VM_session`` contract.
        """
        return build_interactive_session_metadata(
            ui_opts,
            roles=roles,
            role_mismatch_policy=role_mismatch_policy,
        )

    @staticmethod
    def _coerce_ctx_session_metadata_for_ui_release(
        ctx: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """
        Validate and canonicalize session_metadata before any public UI release.

        The roleless backend may return ctx packets from tests, old sessions,
        restored snapshots, or custom session APIs. The role-aware UI boundary is
        the last public read seam before renderer/controller callers receive a
        ctx, so registered app-owned metadata pockets must be verified here.

        Unknown unregistered app pockets remain pass-through through
        coerce_session_metadata(...), preserving the documented backcompat law.
        """
        out = dict(ctx)
        out["session_metadata"] = coerce_session_metadata(
            out.get("session_metadata") or {}
        )
        return out

    def decorate_ctx_for_ui_role(
        self,
        ctx: Mapping[str, Any],
        *,
        role: Optional[str],
    ) -> Dict[str, Any]:
        """
        Return a role-modulated copy of a generic session context.

        This is the read-side guarantee: any U/ctx returned through the
        interactive façade has already had datum-level role mismatch bookkeeping
        attached and mismatch obfuscation applied.
        """
        return role_modulation.modulate(
            self._coerce_ctx_session_metadata_for_ui_release(ctx),
            role=role,
        )

    def assert_ui_step_allowed(
        self,
        api: AbstractSessionAPI,
        session_id: str,
        *,
        role: Optional[str],
        fill: Optional[Mapping[str, Any]] = None,
        signal: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """
        Reject mismatched fill/signal submissions before the roleless backend is
        called.

        Empty fill/signal submissions are allowed so the page-flow controller
        can continue through internal/non-manual execution boundaries.
        """
        raw_ctx = api.get_session_context(session_id)
        role_modulation.assert_submission_allowed(
            raw_ctx,
            role=role,
            fill=fill,
            signal=signal,
        )

    def bind_session_ops(
        self,
        api: AbstractSessionAPI,
        *,
        role: Optional[str],
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        """
        Return a role-bound page-flow-controller liaison.

        Ordinary liaison operations return viewer-role-modulated contexts.
        Controller audit events, however, must be built from canonical raw
        engine contexts so LiveTable storage is never viewer-specific.

        To preserve both laws without a second engine read, the liaison caches
        the raw context produced by each underlying operation. The controller
        may retrieve that exact context through the optional method:

            get_unmodulated_session_context_for_controller_event(...)

        That method is event-infrastructure-only. It does not change the public
        dispatch result and does not evaluate the engine again.

        A dispatch callback may additionally expose:

            observe_unmodulated_context_v1(U)

        After a roleless step returns, the liaison presents its exact raw
        post-step context to that observer before releasing the role-modulated
        result. Provisional event projection uses this seam to retry datum
        lifecycle packets that could not be resolved from the controller-entry
        context.

        This remains observational. It performs no additional engine read,
        persistence reload, hosting transaction, or canonical event mutation.
        """
        bound_threaded_callbacks = (
            dict(threaded_callbacks)
            if isinstance(threaded_callbacks, Mapping)
            else {}
        )

        raw_context_by_session: Dict[str, Dict[str, Any]] = {}

        def remember_raw(
            session_id: str,
            raw_ctx: Mapping[str, Any],
        ) -> Dict[str, Any]:
            if not isinstance(raw_ctx, Mapping):
                raise TypeError(
                    "roleless session operation must return a mapping; "
                    f"got {type(raw_ctx)!r}"
                )

            canonical = dict(raw_ctx)
            raw_context_by_session[str(session_id)] = canonical
            return canonical

        def release_U(U: Mapping[str, Any]) -> Dict[str, Any]:
            return role_modulation.modulate(
                self._coerce_ctx_session_metadata_for_ui_release(U),
                role=role,
            )

        def assert_allowed(
            session_id: str,
            fill: Optional[Mapping[str, Any]],
            signal: Optional[Mapping[str, Any]],
        ) -> None:
            """
            Public interactive boundary preflight.

            This read is used only for write authorization. It is intentionally
            not installed as the controller-event context because the actual
            operation may subsequently produce a newer raw context.
            """
            raw_ctx = api.get_session_context(session_id)
            role_modulation.assert_submission_allowed(
                raw_ctx,
                role=role,
                fill=fill,
                signal=signal,
            )

        class _BoundOps:
            @property
            def role(self) -> Optional[str]:
                return role

            def preflight_controller_dispatch_v1(
                self,
                session_id: str,
                *,
                action: UserAction,
                submitted_fill: Mapping[str, Any],
                submitted_signal: Optional[Mapping[str, Any]],
            ) -> None:
                """
                Reject unauthorized submitted targets before controller start.

                This is the request-boundary authorization seam consumed by
                dispatch_page_flow_controller_automaton(). It deliberately
                runs after dispatcher-identity validation but before
                dispatch-id creation, entry-U evaluation, and controller event
                emission.

                The action is accepted for protocol completeness. Role write
                authorization is target-based; non-STEP fill/signal have
                already been normalized away by the controller.
                """
                del action
                assert_allowed(
                    str(session_id),
                    dict(submitted_fill),
                    (
                        dict(submitted_signal)
                        if isinstance(submitted_signal, Mapping)
                        else None
                    ),
                )

            def step_session(
                self,
                session_id: str,
                fill: Optional[Dict[str, Any]] = None,
                signal: Optional[Dict[str, Any]] = None,
                threaded_callbacks: Optional[Mapping[str, Any]] = None,
            ) -> Dict[str, Any]:
                # Defense in depth for callers that invoke the bound liaison
                # directly rather than through the controller preflight.
                assert_allowed(session_id, fill, signal)

                effective_threaded_callbacks = (
                    dict(threaded_callbacks)
                    if isinstance(threaded_callbacks, Mapping)
                    else dict(bound_threaded_callbacks)
                )

                raw_ctx = api.step_session(
                    session_id,
                    fill=fill,
                    signal=signal,
                    threaded_callbacks=effective_threaded_callbacks,
                )
                canonical = remember_raw(session_id, raw_ctx)

                datum_callback = effective_threaded_callbacks.get(
                    EXPLOSION_EVENTS_CALLBACK_KEY
                )
                context_observer = getattr(
                    datum_callback,
                    "observe_unmodulated_context_v1",
                    None,
                )

                if callable(context_observer):
                    try:
                        context_observer(dict(canonical))
                    except Exception:
                        # Provisional progress is observational and must not
                        # convert an otherwise-valid engine step into a failed
                        # dispatch. The callback adapter performs its own
                        # warning/reporting where possible.
                        pass

                return release_U(canonical)

            def undo_last_step(
                self,
                session_id: str,
            ) -> Dict[str, Any]:
                raw_ctx = api.undo_last_step(session_id)
                canonical = remember_raw(session_id, raw_ctx)
                return release_U(canonical)

            def redo_last_step(
                self,
                session_id: str,
            ) -> Dict[str, Any]:
                raw_ctx = api.redo_last_step(session_id)
                canonical = remember_raw(session_id, raw_ctx)
                return release_U(canonical)

            def get_session_context(
                self,
                session_id: str,
            ) -> Dict[str, Any]:
                raw_ctx = api.get_session_context(session_id)
                canonical = remember_raw(session_id, raw_ctx)
                return release_U(canonical)

            def get_unmodulated_session_context_for_controller_event(
                self,
                session_id: str,
            ) -> Dict[str, Any]:
                """
                Return the raw context from the immediately preceding liaison
                operation.

                This method must remain cache-only. A fallback engine read here
                could mount a datum or emit a lifecycle event outside the
                controller start/within/end ordering.
                """
                normalized_id = str(session_id)
                cached = raw_context_by_session.get(normalized_id)
                if cached is None:
                    raise RuntimeError(
                        "no raw controller-event context is cached for "
                        f"session {normalized_id!r}; the controller must call "
                        "an ordinary liaison context/step operation first"
                    )
                return dict(cached)

            def emit_controller_loop_event_to_session_v1(
                self,
                session_id: str,
                event: Mapping[str, Any],
            ) -> Dict[str, Any]:
                return api.record_session_event(session_id, event)

            def get_outputs(
                self,
                session_id: str,
            ) -> Dict[str, Any]:
                return api.get_outputs(session_id)

            def step(
                self,
                session_id: str,
                fill: Optional[Dict[str, Any]] = None,
                signal: Optional[Dict[str, Any]] = None,
                threaded_callbacks: Optional[Mapping[str, Any]] = None,
            ) -> Dict[str, Any]:
                return self.step_session(
                    session_id,
                    fill=fill,
                    signal=signal,
                    threaded_callbacks=threaded_callbacks,
                )

            def undo(
                self,
                session_id: str,
            ) -> Dict[str, Any]:
                return self.undo_last_step(session_id)

            def redo(
                self,
                session_id: str,
            ) -> Dict[str, Any]:
                return self.redo_last_step(session_id)

            def ctx(
                self,
                session_id: str,
            ) -> Dict[str, Any]:
                return self.get_session_context(session_id)

            def outputs(
                self,
                session_id: str,
            ) -> Dict[str, Any]:
                return self.get_outputs(session_id)

        return _BoundOps()

    def create_interactive_session(
        self,
        manifest: Any,
        initial_parameter_overrides: Dict[str, Any],
        *,
        ui_opts: Mapping[str, Any] | Any = None,
        roles: Optional[Mapping[str, Any]] = None,
        role_mismatch_policy: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Create one role-capable session through the roleless concrete API.

        Roles and mismatch policy are stored as ordinary session metadata. The
        returned session remains one underlying session; servers may create any
        number of role-sealed access handles pointing to it.
        """
        metadata = self.build_metadata(
            ui_opts,
            roles=roles,
            role_mismatch_policy=role_mismatch_policy,
        )

        created = create_VM_session(
            manifest=manifest,
            initial_parameter_overrides=initial_parameter_overrides,
            session_metadata=metadata,
            coercer_of_session_metadata=coerce_session_metadata,
            get_map=True,
        )

        if not isinstance(created, tuple) or len(created) != 2:
            raise TypeError(
                "create_VM_session(get_map=True) must return "
                "(session_state, program_map)"
            )

        state, program_io_map = created
        return (
            str(dict(state)["session_id"]),
            dict(program_io_map or {}),
        )

    def get_current_ui_state(
        self,
        session_id: str,
        *,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return the current role-modulated session context without rendering HTML.

        The underlying ``get_session_context`` operation remains roleless. This
        function obtains that raw context internally and releases a role-
        modulated copy for the requested viewing role.
        """
        raw_ctx = get_session_context(session_id)
        return self.decorate_ctx_for_ui_role(raw_ctx, role=role)

    def decorate_event_for_ui_role(
        self,
        event: Mapping[str, Any],
        *,
        role: Optional[str],
        context_candidates: list[Mapping[str, Any]]
        | tuple[Mapping[str, Any], ...] = (),
    ) -> Dict[str, Any]:
        """
        Return one event as visible to a role-aware caller.

        role=None is the explicit unmodulated queue view.

        For a named role, controller-loop payload.U is role-modulated exactly as
        ordinary ctx release is. Datum lifecycle event visibility is handled by
        ``project_event_for_ui_role`` because projection may drop the event.
        Non-controller events that reach this method are copied unchanged.
        """
        out = dict(event or {})

        if role is None:
            return out

        if str(out.get("kind") or "") != "controller_loop_event_v1":
            return out

        payload = out.get("payload")
        if not isinstance(payload, Mapping):
            return out

        U = payload.get("U")
        if not isinstance(U, Mapping):
            return out

        canonical_U = dict(U)
        projected_U = self.decorate_ctx_for_ui_role(
            U,
            role=role,
        )

        payload_out = dict(payload)
        payload_out["U"] = projected_U

        raw_A = payload.get("A")
        if isinstance(raw_A, Mapping):
            raw_fill = raw_A.get("fill")
            raw_signal = raw_A.get("signal")
        else:
            # Backward-compatible read of pre-A canonical packets.
            raw_fill = payload.get("fill")
            raw_signal = payload.get("signal")

        fill = dict(raw_fill) if isinstance(raw_fill, Mapping) else {}
        signal = dict(raw_signal) if isinstance(raw_signal, Mapping) else None

        # Action authority belongs to the dispatch entry scope. Callers place
        # the matching controller start U first when available. The packet's
        # own U remains a fallback for old/unpaired event streams.
        candidates = [
            dict(candidate)
            for candidate in context_candidates
            if isinstance(candidate, Mapping)
        ]
        candidates.append(canonical_U)

        visible_fill: Dict[str, Any] = {}
        original_target_ids: set[str] = set()
        visible_target_ids: set[str] = set()

        for raw_key, value in fill.items():
            key = str(raw_key)
            datum_id = key.split(".", 1)[0].strip()
            if not datum_id:
                continue
            original_target_ids.add(datum_id)
            if role_modulation.datum_readable(
                datum_id=datum_id,
                role=role,
                context_candidates=candidates,
            ):
                visible_fill[key] = value
                visible_target_ids.add(datum_id)

        visible_signal = None
        if isinstance(signal, Mapping):
            signal_datum_id = str(signal.get("datum_id") or "").strip()
            if signal_datum_id:
                original_target_ids.add(signal_datum_id)
                if role_modulation.datum_readable(
                    datum_id=signal_datum_id,
                    role=role,
                    context_candidates=candidates,
                ):
                    visible_signal = dict(signal)
                    visible_target_ids.add(signal_datum_id)

        all_targets_hidden = bool(
            original_target_ids and not visible_target_ids
        )

        raw_dispatch_context = payload.get("dispatch_context")
        if isinstance(raw_dispatch_context, Mapping):
            if all_targets_hidden:
                payload_out["dispatch_context"] = None
            elif original_target_ids == visible_target_ids:
                payload_out["dispatch_context"] = dict(raw_dispatch_context)
            else:
                projected_dispatch_context = dict(raw_dispatch_context)
                projected_dispatch_context["filler_receipt"] = None
                projected_dispatch_context["receipt_projection"] = (
                    "partial_targets_hidden"
                )
                payload_out["dispatch_context"] = (
                    projected_dispatch_context
                )

        if all_targets_hidden:
            payload_out["A"] = None
            payload_out["fill"] = None
            payload_out["signal"] = None
            out["dispatch_id"] = None
            out["dispatcher_identity_id"] = None
            out["dispatcher_role"] = None
        else:
            projected_A = {
                "fill": visible_fill,
                "signal": visible_signal,
            }
            payload_out["A"] = projected_A
            payload_out["fill"] = dict(visible_fill)
            payload_out["signal"] = (
                dict(visible_signal)
                if isinstance(visible_signal, Mapping)
                else None
            )

        # Controller end duplicates the public semantic-error surface in
        # payload.result.last_error. Keep that sibling copy derived from the
        # already-projected U so one event cannot expose two role-inconsistent
        # answers and assert_controller_loop_event_v1 remains coherent.
        result = payload.get("result")
        if isinstance(result, Mapping):
            result_out = dict(result)
            result_out["last_error"] = projected_U.get("last_error")
            payload_out["result"] = result_out

        out["payload"] = payload_out
        return out

    def project_event_for_ui_role(
        self,
        event: Mapping[str, Any],
        *,
        role: Optional[str],
        context_candidates: list[Mapping[str, Any]]
        | tuple[Mapping[str, Any], ...] = (),
    ) -> Optional[Dict[str, Any]]:
        """
        Return the event as visible to ``role``, or None when hidden.

        Queue storage remains canonical and unmodulated. This projection is
        applied only at public read/broadcast release boundaries.
        """
        out = dict(event or {})

        if role is None:
            return out

        if not role_modulation.event_visible(
            out,
            role=role,
            context_candidates=context_candidates,
        ):
            return None

        return self.decorate_event_for_ui_role(
            out,
            role=role,
            context_candidates=context_candidates,
        )

    @staticmethod
    def _controller_event_context_candidates_v1(
        events: list[Mapping[str, Any]],
    ) -> list[Dict[str, Any]]:
        """
        Extract event-time U snapshots from controller-loop packets.

        Datum lifecycle events do not carry a full U. For queue reads we use the
        bounded event window's controller.loop.start/end payload.U snapshots as
        the event-time role source for neighboring datum events.
        """
        out: list[Dict[str, Any]] = []

        for event in events:
            if str(event.get("kind") or "") != "controller_loop_event_v1":
                continue

            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                continue

            U = payload.get("U")
            if isinstance(U, Mapping):
                out.append(dict(U))

        return out

    @staticmethod
    def _controller_start_context_by_dispatch_v1(
        events: list[Mapping[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Return dispatch_id -> canonical controller start U.

        ``payload.A`` describes the submitted action at controller entry.
        Its datum-role interpretation is consequently relative to the start U,
        even when the end U has moved to another frame/span or contains a reused
        datum identifier.

        Malformed or legacy packets without a usable dispatch id/start U are
        simply absent from this index and continue through the ordinary
        conservative fallback path.
        """
        out: Dict[str, Dict[str, Any]] = {}

        for event in events:
            if str(event.get("kind") or "") != "controller_loop_event_v1":
                continue
            if str(event.get("phase") or "") != "start":
                continue

            dispatch_id = str(event.get("dispatch_id") or "").strip()
            if not dispatch_id:
                continue

            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                continue

            U = payload.get("U")
            if isinstance(U, Mapping):
                out[dispatch_id] = dict(U)

        return out

    def get_current_ui_events(
        self,
        session_id: str,
        *,
        role: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[Dict[str, Any]]:
        raw_events = [
            dict(event or {})
            for event in get_session_events(
                str(session_id),
                limit=limit,
            )
        ]

        if role is None:
            return raw_events

        context_candidates = self._controller_event_context_candidates_v1(
            raw_events,
        )
        start_context_by_dispatch = (
            self._controller_start_context_by_dispatch_v1(raw_events)
        )

        # Current ctx is a useful fallback for manual/external events that are
        # not bracketed by controller-loop packets in the bounded queue. It is
        # read only on public queue reads, not from inside dispatch callbacks.
        try:
            current_ctx = get_session_context(str(session_id))
            if isinstance(current_ctx, Mapping):
                context_candidates.append(dict(current_ctx))
        except Exception:
            pass

        projected: list[Dict[str, Any]] = []
        for event in raw_events:
            event_candidates = list(context_candidates)

            if (
                str(event.get("kind") or "")
                == "controller_loop_event_v1"
            ):
                dispatch_id = str(
                    event.get("dispatch_id") or ""
                ).strip()
                start_U = start_context_by_dispatch.get(dispatch_id)
                if isinstance(start_U, Mapping):
                    event_candidates = [
                        dict(start_U),
                        *event_candidates,
                    ]

            row = self.project_event_for_ui_role(
                event,
                role=role,
                context_candidates=event_candidates,
            )
            if row is not None:
                projected.append(row)

        return projected

    def dispatch_ui_action(
        self,
        session_id: str,
        *,
        action: UserAction = UserAction.STEP,
        user_fill: Optional[Dict[str, Any]] = None,
        user_signal: Optional[Dict[str, Any]] = None,
        role: Optional[str] = None,
        identity_id: str = None,
        render: bool = True,
        include_ctx: bool = True,
        threaded_callbacks: Optional[Mapping[str, Any]] = None,
        dispatch_context: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Dispatch one role-bound UI action through the page-flow controller.

        ``identity_id`` is the required higher-application dispatcher identity.
        The role and identity are passed at this interaction boundary and copied
        onto the controller start/end event envelope.

        The roleless concrete session API never receives a role or identity
        argument. The role remains captured by the role-bound liaison, while the
        immutable dispatch actor context is supplied directly to the controller.

        Semantic rejection returns a normal controller packet whose last_error
        describes the rejected datum submission.

        Systematic controller failures are returned as bounded packets with a
        top-level system_error mapping and ui_mode=None. Raw engine exceptions
        raised after the canonical controller start are not re-raised through
        this public dispatch boundary.
        """
        from _thinkengine._engine_interactive_flow_controller.dispatch_UFU_automaton import (
            dispatch_page_flow_controller_automaton,
        )

        role_bound_ops = self.bind_session_ops(
            get_concrete_session_api(),
            role=role,
            threaded_callbacks=threaded_callbacks,
        )

        result = dispatch_page_flow_controller_automaton(
            session_id=session_id,
            action=action,
            user_fill=dict(user_fill or {}),
            user_signal=(
                dict(user_signal)
                if isinstance(user_signal, Mapping)
                else None
            ),
            dispatcher_identity_id=identity_id,
            dispatcher_role=role,
            session_ops=role_bound_ops,
            threaded_callbacks=threaded_callbacks,
            dispatch_context=(
                dict(dispatch_context)
                if isinstance(dispatch_context, Mapping)
                else None
            ),
        )

        out = dict(result)

        if render and out.get("ui_mode") is not None:
            ui_mode_name = UIMode[out["ui_mode"]].name
            out["content"] = {
                "session_id": session_id,
                "ctx": out["ctx"],
                "event_kind": out["event_kind"],
                "ui_config": out["ui_config"],
                "ui_mode": ui_mode_name,
            }
        elif render:
            out["content"] = {
                "session_id": str(session_id),
                "event_kind": out.get("event_kind"),
                "system_error": out.get("system_error"),
            }

        if not include_ctx:
            raw_ctx = out.get("ctx")
            ctx = raw_ctx if isinstance(raw_ctx, Mapping) else {}

            raw_cursor = ctx.get("cursor")
            cursor = raw_cursor if isinstance(raw_cursor, Mapping) else {}

            raw_state = ctx.get("state")
            state = raw_state if isinstance(raw_state, Mapping) else {}

            out["ctx_report"] = {
                "kind": "ui_ctx_report_v1",
                "event_kind": ctx.get("kind"),
                "cursor": {
                    "index": cursor.get("index"),
                    "total": cursor.get("total"),
                },
                "form_id": ctx.get("form_id") or ctx.get("app_form_id"),
                "frame_id": ctx.get("current_frame_id"),
                "span_id": ctx.get("current_span") or ctx.get("current_span_id"),
                "datum_widgets_on_this_span_count": len(
                    ctx.get("datum_widgets_on_this_span") or []
                ),
                "counts": {
                    "form_prefills": state.get("form_prefills_count"),
                    "form_fills": state.get("form_fills_count"),
                    "forms_emitted": state.get("forms_emitted_count"),
                    "datum_widget_fills": state.get("datum_widget_fills_count"),
                },
                "last_error": ctx.get("last_error"),
            }
            out.pop("ctx", None)

        return out

    def render_current_ui_state(
        self,
        session_id: str,
        *,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Render the already-current durable UI state for one viewing role.

        This operation does not step or otherwise mutate the session. Callers
        must prime newly created sessions before invoking it.
        """
        ctx = self.get_current_ui_state(session_id, role=role)
        kind = str(ctx.get("kind") or "")

        if kind == "MANUALFILLNEEDEDSTEP":
            ui_mode = UIMode.FORM_FILL
            finished = False
        elif kind == "ATCOMPLETION":
            ui_mode = UIMode.RUN_COMPLETED_SUMMARY
            finished = True
        else:
            raise RuntimeError(
                "render_current_ui_state requires a renderable current UI state; "
                f"got kind={kind!r}. "
                "The session must be primed before public rendering."
            )

        ui_config = dict(ctx.get("session_metadata") or {})

        result = {
            "session_id": str(session_id),
            "globals": ctx.get("globals"),
            "datum_widgets_on_this_span": list(
                ctx.get("datum_widgets_on_this_span") or []
            ),
            "ui_mode": ui_mode.name,
            "ui_config": ui_config,
            "ctx": ctx,
            "event_kind": kind,
            "finished": finished,
            "last_error": ctx.get("last_error"),
        }

        result["content"] = {
            "session_id": session_id,
            "ctx": ctx,
            "event_kind": kind,
            "ui_config": ui_config,
            "ui_mode": ui_mode.name,
        }

        return result


_INTERACTIVE_SESSION_API = AppTableInteractiveSessionAPI()


def create_interactive_session(
    manifest: Any,
    initial_parameter_overrides: Dict[str, Any],
    *,
    ui_opts: Mapping[str, Any] | Any = None,
    roles: Optional[Mapping[str, Any]] = None,
    role_mismatch_policy: Optional[Mapping[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    return _INTERACTIVE_SESSION_API.create_interactive_session(
        manifest=manifest,
        initial_parameter_overrides=initial_parameter_overrides,
        ui_opts=ui_opts,
        roles=roles,
        role_mismatch_policy=role_mismatch_policy,
    )


def get_current_ui_state(
    session_id: str,
    *,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    return _INTERACTIVE_SESSION_API.get_current_ui_state(
        session_id,
        role=role,
    )


def get_current_ui_events(
    session_id: str,
    *,
    role: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[Dict[str, Any]]:
    return _INTERACTIVE_SESSION_API.get_current_ui_events(
        session_id,
        role=role,
        limit=limit,
    )


def dispatch_ui_action(
    session_id: str,
    *,
    action: UserAction = UserAction.STEP,
    user_fill: Optional[Dict[str, Any]] = None,
    user_signal: Optional[Dict[str, Any]] = None,
    role: Optional[str] = None,
    identity_id: str = None,
    render: bool = True,
    include_ctx: bool = True,
    threaded_callbacks: Optional[Mapping[str, Any]] = None,
    dispatch_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return _INTERACTIVE_SESSION_API.dispatch_ui_action(
        session_id,
        action=action,
        user_fill=user_fill,
        user_signal=user_signal,
        role=role,
        identity_id=identity_id,
        render=render,
        include_ctx=include_ctx,
        threaded_callbacks=threaded_callbacks,
        dispatch_context=dispatch_context,
    )


def render_current_ui_state(
    session_id: str,
    *,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    return _INTERACTIVE_SESSION_API.render_current_ui_state(
        session_id,
        role=role,
    )


def get_concrete_session_api_w_ui(
    **kwargs: Any,
) -> AppTableInteractiveSessionAPI:
    """
    Return the process-local App Table role-interaction singleton.

    ``kwargs`` is retained only for construction-call shape tolerance. The
    process-local singleton has already been constructed, so such options do not
    alter it.
    """
    del kwargs
    return _INTERACTIVE_SESSION_API


__all__ = [
    # Explicit symbols callers import from this façade.
    "AbstractSessionAPI",
    "StepFnregistry",
    "UserAction",
    "create_interactive_session",
    "checkpoint_session_runtime",
    "dispatch_ui_action",
    "drain_session_events",
    "emit_session_event",
    "evict_session_runtime",
    "get_session_events",
    "get_latest_session_event_seq",
    "get_current_ui_events",
    "get_concrete_session_api",
    "get_current_ui_state",
    "get_runtime_write_index_summary",
    "parse_and_validate_app_table",
    "query_runtime_writes",
    "register_step_fn",
    "render_current_ui_state",
    # Compatibility roleless session surface.
    "CreateSessionReturn",
    "create_VM_session",
    "create_VM_session_from_program",
    "step_session",
    "undo_last_step",
    "redo_last_step",
    "get_session_context",
    "get_outputs",
    "get_form_fill_info",
    "AppTableParserValidatorError",
    # Concrete role-aware interaction façade.
    "AppTableInteractiveSessionAPI",
    "get_concrete_session_api_w_ui",
    "UIMode",
]