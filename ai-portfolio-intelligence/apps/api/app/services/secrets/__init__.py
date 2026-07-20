"""Secrets package for OS keychain-backed credentials."""

from app.services.secrets.secret_store import SecretStore, get_secret_store

__all__ = ["SecretStore", "get_secret_store"]
