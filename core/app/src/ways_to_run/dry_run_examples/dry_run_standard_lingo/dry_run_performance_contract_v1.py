from __future__ import annotations

"""Reusable performance contracts for dry-run strategy integration sheets.

The semantic catalogs prove that every strategy preserves the shared
P / SM / C / A / E grammar. This module lets the same sheets also protect
the performance class of each strategy without hard-coding a budget to the
catalog's current number of cases.

A strategy sheet declares:

* a small fixed allowance for sheet/runtime noise;
* a maximum average contribution per ordinary/funked case; and
* the architectural reason that budget should remain achievable.

The resulting unscaled budget grows with catalog size:

    fixed_allowance + case_count * max_seconds_per_case

A central multiplier absorbs normal wall-clock variance from machine load,
scheduler contention, and concurrent CI work. A known machine class may
override that default with THINKUMENT_DRY_RUN_PERF_MULTIPLIER.

This is a regression envelope, not a microbenchmark. It is deliberately
looser than the fastest observed developer-machine timing while still being
tight enough to catch accidental abstraction-layer costs such as coarse
server shutdown polling, arbitrary sleeps, repeated process startup, or
unnecessary transport setup.
"""

import os
from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Generic, TypeVar


T = TypeVar("T")

PERFORMANCE_MULTIPLIER_ENV_V1 = "THINKUMENT_DRY_RUN_PERF_MULTIPLIER"
DEFAULT_PERFORMANCE_MULTIPLIER_V1 = 1.40


@dataclass(frozen=True, slots=True)
class DryRunPerformanceContractV1:
    """Scalable runtime envelope for one dry-run strategy sheet."""

    fixed_allowance_seconds: float
    max_seconds_per_case: float
    efficiency_reason: str

    def max_seconds_v1(self, *, case_count: int) -> float:
        if case_count < 0:
            raise ValueError("case_count must be >= 0")
        if self.fixed_allowance_seconds < 0:
            raise ValueError("fixed_allowance_seconds must be >= 0")
        if self.max_seconds_per_case < 0:
            raise ValueError("max_seconds_per_case must be >= 0")

        return (
            self.fixed_allowance_seconds
            + self.max_seconds_per_case * case_count
        )


@dataclass(frozen=True, slots=True)
class TimedResultV1(Generic[T]):
    """Return value plus wall-clock duration from one timed catalog run."""

    value: T
    elapsed_seconds: float


def timed_v1(fn: Callable[[], T]) -> TimedResultV1[T]:
    """Measure one synchronous catalog operation with a monotonic clock."""
    started = perf_counter()
    value = fn()

    return TimedResultV1(
        value=value,
        elapsed_seconds=perf_counter() - started,
    )


def _performance_multiplier_v1() -> float:
    raw = os.environ.get(
        PERFORMANCE_MULTIPLIER_ENV_V1,
        str(DEFAULT_PERFORMANCE_MULTIPLIER_V1),
    )

    try:
        multiplier = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"{PERFORMANCE_MULTIPLIER_ENV_V1} must be a positive number"
        ) from exc

    if multiplier <= 0:
        raise ValueError(
            f"{PERFORMANCE_MULTIPLIER_ENV_V1} must be > 0"
        )

    return multiplier


def assert_performance_contract_v1(
    *,
    strategy_name: str,
    elapsed_seconds: float,
    case_count: int,
    contract: DryRunPerformanceContractV1,
) -> None:
    """Fail when a strategy crosses its declared performance envelope.

    The default multiplier absorbs ordinary wall-clock variance across
    developer machines and concurrent CI work. A known machine class may
    override it with THINKUMENT_DRY_RUN_PERF_MULTIPLIER.

    The multiplier exists for execution-environment variance; it should not
    be raised to conceal an implementation regression.
    """
    if elapsed_seconds < 0:
        raise ValueError("elapsed_seconds must be >= 0")

    multiplier = _performance_multiplier_v1()
    unscaled_budget = contract.max_seconds_v1(case_count=case_count)
    effective_budget = unscaled_budget * multiplier
    average_seconds_per_case = elapsed_seconds / max(case_count, 1)

    print(
        "\n[dry-run benchmark]"
        f" strategy={strategy_name}"
        f" cases={case_count}"
        f" elapsed={elapsed_seconds:.3f}s"
        f" average={average_seconds_per_case:.3f}s/case"
        f" budget={effective_budget:.3f}s"
        f" multiplier={multiplier:.3f}"
    )

    assert elapsed_seconds <= effective_budget, (
        f"\nDry-run strategy performance regression: {strategy_name}\n"
        f"  cases:                  {case_count}\n"
        f"  elapsed:                {elapsed_seconds:.3f}s\n"
        f"  average per case:       {average_seconds_per_case:.3f}s\n"
        f"  unscaled budget:        {unscaled_budget:.3f}s\n"
        f"  environment multiplier:{multiplier: .3f}\n"
        f"  effective budget:       {effective_budget:.3f}s\n"
        "\n"
        "Why this strategy is expected to remain inside this envelope:\n"
        f"{contract.efficiency_reason}\n"
    )


__all__ = [
    "DEFAULT_PERFORMANCE_MULTIPLIER_V1",
    "DryRunPerformanceContractV1",
    "PERFORMANCE_MULTIPLIER_ENV_V1",
    "TimedResultV1",
    "assert_performance_contract_v1",
    "timed_v1",
]