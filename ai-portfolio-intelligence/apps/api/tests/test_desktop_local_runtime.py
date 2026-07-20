from secrets import token_urlsafe

import pytest

from app.core.local_runtime import LocalRuntime, generate_session_token
from app.core.network_policy import assert_deployment_network_policy, assert_loopback_bind
from app.core.deployment_mode import DeploymentMode


def test_generate_session_token_is_long_enough():
    token = generate_session_token()
    assert len(token) >= 43


def test_local_runtime_rejects_non_loopback():
    runtime = LocalRuntime(
        host="0.0.0.0",
        port=49182,
        session_token=token_urlsafe(32),
        parent_process_id=1,
    )
    with pytest.raises(RuntimeError, match="loopback"):
        runtime.validate()


def test_token_matches_constant_time():
    token = token_urlsafe(32)
    runtime = LocalRuntime(
        host="127.0.0.1",
        port=49182,
        session_token=token,
        parent_process_id=1,
    )
    runtime.validate()
    assert runtime.token_matches(token) is True
    assert runtime.token_matches("wrong") is False
    assert runtime.token_matches(None) is False


def test_desktop_requires_loopback_and_json_persistence():
    assert_loopback_bind("127.0.0.1")
    with pytest.raises(RuntimeError):
        assert_loopback_bind("0.0.0.0")

    assert_deployment_network_policy(
        deployment_mode=DeploymentMode.DESKTOP_LOCAL,
        bind_host="127.0.0.1",
        database_url="unused",
        persistence_backend="json",
    )
    with pytest.raises(RuntimeError, match="must be json"):
        assert_deployment_network_policy(
            deployment_mode=DeploymentMode.DESKTOP_LOCAL,
            bind_host="127.0.0.1",
            database_url="sqlite+pysqlite:////tmp/portfolio.db",
            persistence_backend="sqlite",
        )
