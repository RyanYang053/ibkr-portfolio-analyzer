"""OS Keychain / Credential Manager backed secret storage."""

from __future__ import annotations

import sys
from typing import Protocol


SERVICE_NAME = "PortfolioAnalyzer"


class SecretBackend(Protocol):
    def set_secret(self, key: str, value: str) -> None: ...

    def get_secret(self, key: str) -> str | None: ...

    def delete_secret(self, key: str) -> None: ...


class MemorySecretBackend:
    """Test / fallback backend — never used for Flex tokens in production desktop builds."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def set_secret(self, key: str, value: str) -> None:
        self._values[key] = value

    def get_secret(self, key: str) -> str | None:
        return self._values.get(key)

    def delete_secret(self, key: str) -> None:
        self._values.pop(key, None)


class KeyringSecretBackend:
    def set_secret(self, key: str, value: str) -> None:
        import keyring

        keyring.set_password(SERVICE_NAME, key, value)

    def get_secret(self, key: str) -> str | None:
        import keyring

        return keyring.get_password(SERVICE_NAME, key)

    def delete_secret(self, key: str) -> None:
        import keyring

        try:
            keyring.delete_password(SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            return


def default_secret_backend(*, allow_memory_fallback: bool = True) -> SecretBackend:
    try:
        import keyring  # noqa: F401

        return KeyringSecretBackend()
    except Exception:
        if not allow_memory_fallback:
            raise RuntimeError(
                f"OS keychain unavailable on {sys.platform}; cannot store secrets safely"
            )
        return MemorySecretBackend()
