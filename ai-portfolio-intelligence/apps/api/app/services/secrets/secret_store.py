"""Application secret store — Flex tokens and encryption keys only."""

from __future__ import annotations

from app.services.secrets.os_keychain import SecretBackend, default_secret_backend

ALLOWED_SECRET_KEYS = frozenset(
    {
        "ibkr_flex_token",
        "app_encryption_key",
    }
)

FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "ibkr_password",
        "ibkr_username",
        "ibkr_2fa",
        "password",
        "totp",
    }
)


class SecretStore:
    def __init__(self, backend: SecretBackend | None = None) -> None:
        self._backend = backend or default_secret_backend()

    def set(self, key: str, value: str) -> None:
        if key in FORBIDDEN_SECRET_KEYS:
            raise ValueError(f"Refusing to store forbidden secret key: {key}")
        if key not in ALLOWED_SECRET_KEYS:
            raise ValueError(f"Secret key is not allow-listed: {key}")
        if not value:
            raise ValueError("Secret value must be non-empty")
        self._backend.set_secret(key, value)

    def get(self, key: str) -> str | None:
        if key in FORBIDDEN_SECRET_KEYS:
            raise ValueError(f"Refusing to read forbidden secret key: {key}")
        return self._backend.get_secret(key)

    def delete(self, key: str) -> None:
        self._backend.delete_secret(key)


_store: SecretStore | None = None


def get_secret_store() -> SecretStore:
    global _store
    if _store is None:
        _store = SecretStore()
    return _store
