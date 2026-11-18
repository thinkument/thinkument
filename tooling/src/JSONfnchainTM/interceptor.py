"""Host-owned observability hooks; implementations must synchronize shared state."""
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class FlowAttemptContext:
    execution_id: str
    attempt_id: str
    node_path: tuple[str | int, ...]
    map_indices: tuple[int, ...]
    loop_iterations: tuple[int, ...]
    host_context: Any = None

class FlowInterceptor:
    """No-op lifecycle base. Hooks execute in the calling/worker thread.

    after_step is invoked only after successful output validation. Any failure in
    before_step, the callable, output validation, or after_step calls on_step_error
    exactly once for a started attempt. A failure in on_step_error is recorded as
    a runtime error and does not suppress fork-join settlement.
    """
    def before_step(self, ctx: FlowAttemptContext, args: dict) -> None: pass
    def after_step(self, ctx: FlowAttemptContext, args: dict, result: dict) -> None: pass
    def on_step_error(self, ctx: FlowAttemptContext, args: dict, error: Exception) -> None: pass
