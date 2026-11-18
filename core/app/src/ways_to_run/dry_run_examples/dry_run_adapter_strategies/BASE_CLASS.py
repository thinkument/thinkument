from __future__ import annotations

"""Strategy contract for executing the standard dry-run formalism.

The dry-run language owns P / SM / C / A / E. A strategy owns only the
translation between that standard language and one concrete execution lens.

Universal strategy spaces
-------------------------
Every strategy covers the same execution/observation spaces:

``lambda`` / launch
    start one P + SM + C run and return an opaque handle;

``gamma`` / direct dispatch
    apply one role-bound standard A and return a standard dispatch result;

``gamma_f`` / funked dispatch
    apply the same A grammar through the chain-reaction operator;

``epsilon`` / live dispatch-time observation
    optionally emit standard live event packets while gamma/gamma_f is open;

``theta`` / committed queue observation
    expose the role-independent canonical high-water and role-projected
    committed queue pages over canonical cursors;

``Q/U`` / current context observation
    expose the current role-projected session context;

``omega`` / close
    release the opaque run handle and its hosting resources.

Roles are parameters of the standard action/read spaces, not a separate
strategy-specific language. Concrete strategies may realize a role through a
Python argument, an HTTP capability, a Django principal, a browser identity, a
DOM-bound page, or another mechanism.

Strategy capability law
-----------------------
A higher membrane may intentionally refuse a small subset of shared dry-run
cases when those cases require an operation that is impossible through that
membrane by design. For example, a real browser opinionation should not expose
a control that lets a human forge ThinkumentJS-owned transport cursors.

Such exclusions are explicit strategy capabilities, never hidden branches in
the generic runner or edits to the shared flow catalog. ``case_skip_reason_v1``
returns a reason for a named case, and the convenience helpers below partition
one catalog deterministically. Ordinary strategies support every case by
default.

Normalization law
-----------------
Transport/environment-specific details belong behind this interface. A Flask
strategy may receive HTTP status codes and request ids; a browser strategy may
receive DOM events; a Django strategy may receive transaction/idempotency
receipts. Before observations are returned to generic proof machinery, those
facts are translated into the standard P/SM/C/A/E vocabulary used by the
shared catalogs.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, TypeVar


DryRunRunHandleV1 = Any
DryRunLiveEventSinkV1 = Callable[[Mapping[str, Any]], None]
_CaseT = TypeVar("_CaseT")


class BaseDryRunStrategy(ABC):
    """Abstract adapter for one way of driving and observing a P/SM/C run."""

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Stable human-readable strategy identifier."""
        raise NotImplementedError

    def case_skip_reason_v1(
        self,
        *,
        case_name: str,
        funked: bool,
    ) -> Optional[str]:
        """Return an explicit reason when this membrane cannot execute a case.

        The default is full support. Concrete higher-layer strategies should
        override this only for semantic impossibilities at that layer, not for
        slowness, flakiness, implementation convenience, or known bugs.
        """

        del case_name, funked
        return None

    def supported_cases_v1(
        self,
        cases: Iterable[_CaseT],
        *,
        funked: bool = False,
    ) -> tuple[_CaseT, ...]:
        """Return catalog rows that this strategy can execute faithfully."""

        return tuple(
            case
            for case in cases
            if self.case_skip_reason_v1(
                case_name=str(getattr(case, "name", "")),
                funked=bool(funked),
            )
            is None
        )

    def skipped_cases_v1(
        self,
        cases: Sequence[_CaseT],
        *,
        funked: bool = False,
    ) -> tuple[tuple[_CaseT, str], ...]:
        """Return explicit ``(case, reason)`` exclusions for one catalog."""

        out: list[tuple[_CaseT, str]] = []
        for case in cases:
            reason = self.case_skip_reason_v1(
                case_name=str(getattr(case, "name", "")),
                funked=bool(funked),
            )
            if reason is not None:
                out.append((case, str(reason)))
        return tuple(out)

    @abstractmethod
    def start_run_v1(
        self,
        *,
        program: Mapping[str, Any],
        session_metadata: Mapping[str, Any],
        initial_parameter_overrides: Mapping[str, Any],
    ) -> DryRunRunHandleV1:
        """lambda: start one run from standard P, SM, and C inputs."""
        raise NotImplementedError

    @abstractmethod
    def close_run_v1(self, *, run: DryRunRunHandleV1) -> None:
        """omega: release one run created by :meth:`start_run_v1`."""
        raise NotImplementedError

    @abstractmethod
    def dispatch_action_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        A: Mapping[str, Any],
        live_event_sink: Optional[DryRunLiveEventSinkV1] = None,
    ) -> Mapping[str, Any]:
        """gamma (+ optional epsilon): apply one standard role-bound A."""
        raise NotImplementedError

    @abstractmethod
    def dispatch_action_with_chain_reaction_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        A: Mapping[str, Any],
        live_event_sink: Optional[DryRunLiveEventSinkV1] = None,
    ) -> Mapping[str, Any]:
        """gamma_f (+ optional epsilon): apply A with chain reaction."""
        raise NotImplementedError

    @abstractmethod
    def latest_committed_event_seq_v1(
        self,
        *,
        run: DryRunRunHandleV1,
    ) -> int:
        """theta: return the role-independent committed queue high-water."""
        raise NotImplementedError

    @abstractmethod
    def committed_events_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> list[Mapping[str, Any]]:
        """theta: return the retained committed queue under one role."""
        raise NotImplementedError

    @abstractmethod
    def poll_committed_events_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
        after_event_seq: int,
        identity_id: str,
        limit: Optional[int],
    ) -> Mapping[str, Any]:
        """theta: poll committed queue data after one canonical cursor."""
        raise NotImplementedError

    @abstractmethod
    def read_context_v1(
        self,
        *,
        run: DryRunRunHandleV1,
        role: Optional[str],
    ) -> Mapping[str, Any]:
        """Q/U: read the current role-projected session context."""
        raise NotImplementedError


__all__ = [
    "BaseDryRunStrategy",
    "DryRunLiveEventSinkV1",
    "DryRunRunHandleV1",
]
