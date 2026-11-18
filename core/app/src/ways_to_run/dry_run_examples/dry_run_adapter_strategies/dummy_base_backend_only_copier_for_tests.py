from __future__ import annotations

"""Second concrete strategy used to prove exchangeability of the runner.

It intentionally produces the same net effects as the current base-facade
strategy while living as a separate concrete class.  Every method is an
explicit override so future strategy experiments can replace one seam at a
time without changing the dry-run language or machinery.
"""

from typing import Any, Mapping, Optional

from .BASE_CLASS import DryRunLiveEventSinkV1, DryRunRunHandleV1
from .base_facade_backend_only import BaseFacadeBackendOnlyDryRunStrategy


class DummyBaseBackendOnlyCopierForTestsStrategy(
    BaseFacadeBackendOnlyDryRunStrategy
):
    @property
    def strategy_name(self) -> str:
        return "dummy-base-backend-only-copier-for-tests"

    def start_run_v1(
        self,
        *,
        program: Mapping[str, Any],
        session_metadata: Mapping[str, Any],
        initial_parameter_overrides: Mapping[str, Any],
    ) -> DryRunRunHandleV1:
        return super().start_run_v1(
            program=program,
            session_metadata=session_metadata,
            initial_parameter_overrides=initial_parameter_overrides,
        )

    def close_run_v1(self, *, run: DryRunRunHandleV1) -> None:
        super().close_run_v1(run=run)

    def dispatch_action_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        A: Mapping[str, Any],
        live_event_sink: Optional[DryRunLiveEventSinkV1] = None,
    ) -> Mapping[str, Any]:
        return super().dispatch_action_v1(
            run=run,
            A=A,
            live_event_sink=live_event_sink,
        )

    def dispatch_action_with_chain_reaction_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        A: Mapping[str, Any],
        live_event_sink: Optional[DryRunLiveEventSinkV1] = None,
    ) -> Mapping[str, Any]:
        return super().dispatch_action_with_chain_reaction_v1(
            run=run,
            A=A,
            live_event_sink=live_event_sink,
        )

    def latest_committed_event_seq_v1(
        self,
        *,
        run: DryRunRunHandleV1,
    ) -> int:
        return super().latest_committed_event_seq_v1(run=run)

    def committed_events_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> list[Mapping[str, Any]]:
        return super().committed_events_v1(run=run, role=role)

    def poll_committed_events_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
        after_event_seq: int,
        identity_id: str,
        limit: Optional[int],
    ) -> Mapping[str, Any]:
        return super().poll_committed_events_v1(
            run=run,
            role=role,
            after_event_seq=after_event_seq,
            identity_id=identity_id,
            limit=limit,
        )

    def read_context_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> Mapping[str, Any]:
        return super().read_context_v1(run=run, role=role)


__all__ = ["DummyBaseBackendOnlyCopierForTestsStrategy"]
