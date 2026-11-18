from __future__ import annotations


#########################

class AppTableParserValidatorError(ValueError):
    """Raised when the app table manifest is invalid: schema, fn args, duplicates, etc."""


class InvalidExternalFillError(ValueError):
    """Raised when a user fill payload is invalid for the current MANUALFILLNEEDEDSTEP."""


class ProgramEndReachedError(RuntimeError):
    """Raised when stepping beyond ATCOMPLETION."""


class ProgramStartReachedError(RuntimeError):
    """Raised when undoing before ATSTART."""


class FatalEngineError(RuntimeError):
    """Raised when the backend cannot continue because of an internal invariant failure."""


class DatumLifecycleContractError(FatalEngineError):
    """
    Raised when a Q datum widget violates the datum lifecycle contract.

    This is a developer/system error, not a user-input validation error.
    """


class RedoUnavailableError(RuntimeError):
    """Raised when redo is requested but no redoable public manual action exists."""


class ScriptedFillRejectedError(RuntimeError):
    """
    Raised when a scripted fill action is rejected by the current manual span.

    This keeps bad scripted input from silently parking forever on the same
    MANUALFILLNEEDEDSTEP.
    """


#########################
"""
Public error classes exported for downstream packages.

This module is intentionally lightweight: it must not import engine internals or
data/vendor packages. Downstream packages can safely import these public errors
without creating dependency cycles.
"""


class EngineError(Exception):
    """Root for all public Thinkument engine exceptions."""
    ...



class HCIEngineErrorWDetailedMsgs(EngineError):
    """User-facing engine error that may carry detailed UI messages."""
    ...


class ValidatorReturnContractError(RuntimeError):
    """
    Raised when a micro/macro validator does not comply with the required return
    contract: (bool, str|None).

    This is a system-level error, not a user input error.
    """

    def __init__(
        self,
        *,
        context: str,
        validator_label: str,
        got_type: str,
        value_repr: str,
    ):
        super().__init__(
            f"{context} validator {validator_label!r} must return (bool, str|None); "
            f"got {got_type} → {value_repr}"
        )


class FormFillsAPIError(ValueError):
    """Raised when fills API inputs, coercion, typing, or transfer rules fail."""
    pass



class FormFillsContractError(ValueError):
    """Raised when prefills/fills violate the canonical forms contract."""



class ComposerError(FatalEngineError):
    ...

class ProgramDeclViaDSLInvalid(ValueError):
    """Raised when the program declaration via DSL fails static validation."""
    pass

class EngineComposerTapeError(ComposerError):
    ...

class ProgramEndReachedError(EngineComposerTapeError):
    """
    Raised when attempting to step or undo a session
    that has already completed.
    """
    pass

class ProgramStartReachedError(EngineComposerTapeError):
    pass

class InvalidExternalFillError(HCIEngineErrorWDetailedMsgs):
    """
    Raised when user-supplied manual-fill values are invalid
    (e.g. wrong fields, parse errors).
    Carries a mapping from field_id -> error message.
    """

    def __init__(self, errors: dict[str, str], message: str | None = None):
        super().__init__(message or "Invalid fill for one or more fields")
        self.errors = errors



__all__ = [
    "AppTableParserValidatorError",
    "DatumLifecycleContractError",
    "FatalEngineError",
    "InvalidExternalFillError",
    "ProgramEndReachedError",
    "ProgramStartReachedError",
    "RedoUnavailableError",
    "ScriptedFillRejectedError",
    "EngineError",
    "FormFillsAPIError",
    "FatalEngineError",
    "HCIEngineErrorWDetailedMsgs",
    "ValidatorReturnContractError",
    "ComposerError",
    "ProgramDeclViaDSLInvalid",
    "EngineComposerTapeError",
    "ProgramEndReachedError",
    "ProgramStartReachedError",
    "InvalidExternalFillError",
]