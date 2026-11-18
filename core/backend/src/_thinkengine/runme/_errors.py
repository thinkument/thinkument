
class ProgramRunStallError(RuntimeError):
    """
    Raised when scripted/session rollout detects no progress before a durable stop.

    This is intentionally a runtime/scriptit failure, not a test timeout.
    Any scripted loop that cannot prove forward progress must fail loudly here.
    """
