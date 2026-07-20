import pytest

from app.services.secrets.os_keychain import MemorySecretBackend
from app.services.secrets.secret_store import SecretStore


def test_secret_store_allows_flex_token_only():
    store = SecretStore(backend=MemorySecretBackend())
    store.set("ibkr_flex_token", "flex-abc")
    assert store.get("ibkr_flex_token") == "flex-abc"
    store.delete("ibkr_flex_token")
    assert store.get("ibkr_flex_token") is None


def test_secret_store_rejects_ibkr_passwords():
    store = SecretStore(backend=MemorySecretBackend())
    with pytest.raises(ValueError, match="forbidden"):
        store.set("ibkr_password", "secret")
    with pytest.raises(ValueError, match="forbidden"):
        store.set("ibkr_username", "user")
