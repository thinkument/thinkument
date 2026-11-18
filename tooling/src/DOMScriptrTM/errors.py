"""Small, information-bearing DOMScriptr exceptions."""


class DOMScriptrError(RuntimeError):
    """Base error for DOMScriptr lifecycle/contract failures."""


class LifecycleError(DOMScriptrError):
    """Raised when an object is used outside its valid async lifetime."""


class ServerContractError(DOMScriptrError):
    """Raised when a server starter returns an unsupported value."""


class NoPageError(DOMScriptrError):
    """Raised when a Client page convenience method has no live default page."""
