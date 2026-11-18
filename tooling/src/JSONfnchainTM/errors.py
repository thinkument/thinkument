"""Stable JSON-compatible diagnostics for static and runtime flow boundaries."""

class FlowError(ValueError):
    def __init__(self, code, path=(), message=None, *, expected=None, actual=None, cause=None):
        self.details = {'code': code, 'path': list(path), 'expected': expected,
                        'actual': actual, 'message': message or code}
        self.cause = cause
        super().__init__(self.details['message'])

class FlowCompilationError(FlowError):
    """Malformed flow, unknown identifier, incompatible type or tampered recipe."""

class FlowRuntimeError(FlowError):
    """A flow did not produce a complete validated result. Side effects may persist."""

class MaxIterationsExceededError(FlowRuntimeError):
    """The loop's guard remains true after consuming its iteration ceiling."""
