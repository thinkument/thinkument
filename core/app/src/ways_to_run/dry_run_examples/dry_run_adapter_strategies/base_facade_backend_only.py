from __future__ import annotations

"""Current in-process backend-only dry-run strategy.

This class contains every opinion that used to leak from the generic dry-run
runner into ``_thinksessions.run.run_from_here``:

* how P/SM/C starts a run;
* how standard A becomes a direct dispatch;
* how standard A becomes a funked dispatch;
* how epsilon/live packets are captured from threaded callbacks;
* how theta/committed events are read and cursored;
* how role-projected Q/U context is read; and
* how the run is deleted.

The generic dry-run machinery imports none of those backend surfaces.
"""

from copy import deepcopy
from typing import Any, Mapping, Optional

from _thinkprogram.thinkprogramTM.api import LANG_THINK_PROGRAM_V1
from _thinksessions.run.run_from_here import (
    UserAction,
    create_live_session_from_program,
    delete_live_session,
    dispatch_live_session_action,
    dispatch_live_session_action_with_chain_reaction,
    get_live_session_context,
    get_live_session_events,
    get_live_session_events_since,
    get_live_session_latest_event_seq,
)
from _thinksessions.run.runme_surfaces_out.__engine_event_packet import (
    CONTROLLER_EVENTS_CALLBACK_KEY,
    EXPLOSION_EVENTS_CALLBACK_KEY,
)

from .BASE_CLASS import (
    BaseDryRunStrategy,
    DryRunLiveEventSinkV1,
    DryRunRunHandleV1,
)


class BaseFacadeBackendOnlyDryRunStrategy(BaseDryRunStrategy):
    """Execute the standard dry-run language directly through run_from_here."""

    @property
    def strategy_name(self) -> str:
        return "base-facade-strategy"

    def start_run_v1(
        self,
        *,
        program: Mapping[str, Any],
        session_metadata: Mapping[str, Any],
        initial_parameter_overrides: Mapping[str, Any],
    ) -> DryRunRunHandleV1:
        created = create_live_session_from_program(
            program=deepcopy(dict(program)),
            program_language=LANG_THINK_PROGRAM_V1,
            initial_parameter_overrides=deepcopy(
                dict(initial_parameter_overrides)
            ),
            session_metadata=deepcopy(dict(session_metadata)),
        )
        if created.get("ok") is not True:
            raise AssertionError(
                "base facade strategy failed to create live session: "
                f"{created!r}"
            )
        return str(created["session_id"])

    def close_run_v1(self, *, run: DryRunRunHandleV1) -> None:
        delete_live_session(session_id=str(run))

    @staticmethod
    def _user_action(raw: Any) -> UserAction:
        if isinstance(raw, UserAction):
            return raw
        return UserAction[str(raw or "STEP").strip().upper()]

    @staticmethod
    def _live_callbacks(
        sink: Optional[DryRunLiveEventSinkV1],
    ) -> Optional[dict[str, Any]]:
        if sink is None:
            return None

        def capture(*args: Any, **kwargs: Any) -> None:
            candidates = [*reversed(args), *reversed(tuple(kwargs.values()))]
            for candidate in candidates:
                if not isinstance(candidate, Mapping):
                    continue
                if candidate.get("kind") in {
                    "controller_loop_event_v1",
                    "datum_lifecycle_event_v1",
                }:
                    row = deepcopy(dict(candidate))
                    if row.get("kind") == "datum_lifecycle_event_v1":
                        if "channel" not in row:
                            row["channel"] = row.get("name")
                    sink(row)
                    return
            raise AssertionError(
                "base facade callback did not expose a standard event packet: "
                f"args={args!r}, kwargs={dict(kwargs)!r}"
            )

        return {
            CONTROLLER_EVENTS_CALLBACK_KEY: capture,
            EXPLOSION_EVENTS_CALLBACK_KEY: capture,
        }

    @staticmethod
    def _dispatch_kwargs(
        A: Mapping[str, Any],
        *,
        live_event_sink: Optional[DryRunLiveEventSinkV1],
    ) -> dict[str, Any]:
        raw_role = A.get("role")
        return {
            "action": BaseFacadeBackendOnlyDryRunStrategy._user_action(
                A.get("action")
            ),
            "identity_id": str(A.get("identity_id") or ""),
            "user_fill": A.get("user_fill"),
            "user_signal": A.get("user_signal"),
            "role": None if raw_role is None else str(raw_role),
            "threaded_callbacks": (
                BaseFacadeBackendOnlyDryRunStrategy._live_callbacks(
                    live_event_sink
                )
            ),
            "my_current_event_seq_number": A.get(
                "my_current_event_seq_number"
            ),
        }

    def dispatch_action_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        A: Mapping[str, Any],
        live_event_sink: Optional[DryRunLiveEventSinkV1] = None,
    ) -> Mapping[str, Any]:
        return dict(
            dispatch_live_session_action(
                session_id=str(run),
                **self._dispatch_kwargs(
                    A,
                    live_event_sink=live_event_sink,
                ),
            )
            or {}
        )

    def dispatch_action_with_chain_reaction_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        A: Mapping[str, Any],
        live_event_sink: Optional[DryRunLiveEventSinkV1] = None,
    ) -> Mapping[str, Any]:
        kwargs = self._dispatch_kwargs(
            A,
            live_event_sink=live_event_sink,
        )
        if "chainreactionTM_config" in A:
            kwargs["chainreactionTM_config"] = A[
                "chainreactionTM_config"
            ]
        return dict(
            dispatch_live_session_action_with_chain_reaction(
                session_id=str(run),
                **kwargs,
            )
            or {}
        )

    def latest_committed_event_seq_v1(
        self,
        *,
        run: DryRunRunHandleV1,
    ) -> int:
        return int(
            get_live_session_latest_event_seq(session_id=str(run))
        )

    def committed_events_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> list[Mapping[str, Any]]:
        return [
            dict(event)
            for event in get_live_session_events(
                session_id=str(run),
                role=role,
            )
        ]

    def poll_committed_events_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
        after_event_seq: int,
        identity_id: str,
        limit: Optional[int],
    ) -> Mapping[str, Any]:
        return dict(
            get_live_session_events_since(
                session_id=str(run),
                role=role,
                after_event_seq=int(after_event_seq),
                identity_id=str(identity_id),
                limit=limit,
            )
            or {}
        )

    def read_context_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> Mapping[str, Any]:
        return dict(
            get_live_session_context(
                session_id=str(run),
                role=role,
            )
            or {}
        )


__all__ = ["BaseFacadeBackendOnlyDryRunStrategy"]
