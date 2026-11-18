from __future__ import annotations

"""Executable highest-facade flow catalog for ``dry_run_lib_widgets_flows``.

Each row is intentionally only ``(P, C, SM, attempted actions)``. The generic
runner owns session creation/deletion, dispatch, cursor discipline, canonical
event reads, role projections, and optional frontend-data-blanket assertions.
That keeps flow examples declarative and lets new flow tests scale by adding a
case rather than rebuilding a bespoke test harness.
"""

from ways_to_run.dry_run_examples.dry_run_standard_lingo.live_session_dry_run_v1 import DryRunCaseV1

from .flows.program1__thinkwidget_composition_and_progression import (
    PROGRAM as P1,
    PUPPET as PUPPET1,
    expected_unrolling as E1,
)
from .flows.program2__thinkprogram_authoring_range import (
    PROGRAM as P2,
    PROGRAM_TAKE_OVER as P2_TAKE_OVER,
    PUPPET as PUPPET2,
    PUPPET_TAKE_OVER as PUPPET2_TAKE_OVER,
    expected_unrolling as E2,
    expected_unrolling_take_over as E2_TAKE_OVER,
)
from .flows.program3__thinkwidget_lifecycle_execution_flags import (
    PROGRAM as P3,
    PUPPET as PUPPET3,
    expected_unrolling as E3,
)
from .flows.program4__thinkwidget_wires_args_and_history_observation import (
    PROGRAM as P4,
    PUPPET as PUPPET4,
    expected_unrolling as E4,
)
from .flows.program6__micros_shell__semantic_validation_by_platform_and_the_alternative_functional_lifecycle_validation_later import (
    PROGRAM as P6,
    PUPPET as PUPPET6,
    expected_unrolling as E6,
)
from .flows.program7__thinkprogram_session_metadata_as_a_scalable_activation_head import (
    PROGRAM as P8,
    PUPPET as PUPPET8,
    SESSION_METADATA as SESSION_METADATA8,
    expected_unrolling as E8,
)
from .flows.program8__events_heard__preflight_invalidation_so_no_dispatch_event_and_dispatch_end_failure_events import (
    PROGRAM as P7,
    PUPPET as PUPPET7,
    expected_unrolling as E7,
)
from .flows.program9__events_heard_and_events_caused_by_dispatch_under_role_modulated_reads_writes import (
    PROGRAM as P9,
    PUPPET as PUPPET9,
    SESSION_METADATA as SESSION_METADATA9,
    expected_unrolling as E9,
)
from .flows.program10__events_heard__dispatch_start_and_end_events_projection_asymmetries import (
    PROGRAM as P10,
    PUPPET as PUPPET10,
    SESSION_METADATA as SESSION_METADATA10,
    expected_unrolling as E10,
)
from .flows.program13___frontend_data_blankets_expected_proven_e2e import (
    PROGRAM as P13,
    PUPPET as PUPPET13,
    SESSION_METADATA as SESSION_METADATA13,
    expected_unrolling as E13,
)


DRY_RUN_CASES = (
    DryRunCaseV1(
        name="dry_run_lib_widgets_flows.P1.widget_play",
        program=P1,
        initial_parameter_overrides=PUPPET1,
        session_metadata=None,
        actions=E1,
    ),
    DryRunCaseV1(
        name="dry_run_lib_widgets_flows.P2.program_range",
        program=P2,
        initial_parameter_overrides=PUPPET2,
        session_metadata=None,
        actions=E2,
    ),
    DryRunCaseV1(
        name="dry_run_lib_widgets_flows.P2.program_range_take_over",
        program=P2_TAKE_OVER,
        initial_parameter_overrides=PUPPET2_TAKE_OVER,
        session_metadata=None,
        actions=E2_TAKE_OVER,
    ),
    DryRunCaseV1(
        name="dry_run_lib_widgets_flows.P3.lifecycle_flags",
        program=P3,
        initial_parameter_overrides=PUPPET3,
        session_metadata=None,
        actions=E3,
    ),
    DryRunCaseV1(
        name="dry_run_lib_widgets_flows.P4.wiring_observation",
        program=P4,
        initial_parameter_overrides=PUPPET4,
        session_metadata=None,
        actions=E4,
    ),
    DryRunCaseV1(
        name="dry_run_lib_widgets_flows.P6.semantic_validation_layers",
        program=P6,
        initial_parameter_overrides=PUPPET6,
        session_metadata=None,
        actions=E6,
    ),
    DryRunCaseV1(
        name="dry_run_lib_widgets_flows.P7.dispatch_failure_boundaries",
        program=P7,
        initial_parameter_overrides=PUPPET7,
        session_metadata=None,
        actions=E7,
    ),
    DryRunCaseV1(
        name="dry_run_lib_widgets_flows.P8.session_metadata_activation_head",
        program=P8,
        initial_parameter_overrides=PUPPET8,
        session_metadata=SESSION_METADATA8,
        actions=E8,
    ),
    DryRunCaseV1(
        name="dry_run_lib_widgets_flows.P9.role_modulated_reads_writes",
        program=P9,
        initial_parameter_overrides=PUPPET9,
        session_metadata=SESSION_METADATA9,
        actions=E9,
    ),
    DryRunCaseV1(
        name="dry_run_lib_widgets_flows.P10.dispatch_boundary_projection_asymmetries",
        program=P10,
        initial_parameter_overrides=PUPPET10,
        session_metadata=SESSION_METADATA10,
        actions=E10,
    ),
    DryRunCaseV1(
        name=(
            "dry_run_lib_widgets_flows.P13."
            "frontend_data_blankets_expected_proven_e2e"
        ),
        program=P13,
        initial_parameter_overrides=PUPPET13,
        session_metadata=SESSION_METADATA13,
        actions=E13,
    ),
)


__all__ = ["DRY_RUN_CASES"]
