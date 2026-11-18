"""Managed service credentials. Importing the contract never initializes Django."""
from .contract import AccountSpec, Credentials, CredentialError, load_credentials

__all__ = ["AccountSpec", "Credentials", "CredentialError", "load_credentials"]
