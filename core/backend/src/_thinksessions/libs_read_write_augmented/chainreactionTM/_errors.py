from __future__ import annotations


class FunkTMError(Exception):
    """Base chainreactionTM error."""


class FunkTMStaticError(FunkTMError):
    """Static config/schema/coherence error."""


class FunkTMRuntimeError(FunkTMError):
    """Runtime chain-reaction error."""


class FunkExtraneousRoleStaticError(FunkTMStaticError):
    pass


class FunkRoleMissingStaticError(FunkTMStaticError):
    pass


class FunkRoleConfigMissingStaticError(FunkTMStaticError):
    pass


class FunkVersionStaticError(FunkTMStaticError):
    pass


class FunkConfigStaticError(FunkTMStaticError):
    pass


class FunkUnanticipatedDatumRoleRuntimeError(FunkTMRuntimeError):
    pass


class FunkInputSemanticError(FunkTMRuntimeError):
    pass


class FunkMaxSemanticErrorsExceeded(FunkTMRuntimeError):
    pass


class FunkMaxFillsOnSpanExceeded(FunkTMRuntimeError):
    pass


class FunkMaxFillsE2EExceeded(FunkTMRuntimeError):
    pass