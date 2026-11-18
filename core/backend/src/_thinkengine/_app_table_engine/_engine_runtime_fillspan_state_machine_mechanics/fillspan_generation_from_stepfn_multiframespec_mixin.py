from __future__ import annotations

from typing import Any


class StepFnMultiframespecReturnedExpansionMixin:
    """
    Expands a step-function-returned multiframespec/pending form into concrete
    MANUAL fillspan program steps.
    """

    def expand_stepfn_multiframespec_out_to_fillspan_steps(
        self,
        step: Any,
    ) -> None:
        
        from .span_main_algos.span_generation import (
            expand_stepfn_multiframespec_out_to_fillspan_steps
        )

        return expand_stepfn_multiframespec_out_to_fillspan_steps(self, step)
        