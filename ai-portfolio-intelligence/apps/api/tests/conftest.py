import os

import pytest

# Force broker mode to default ibkr_readonly for test suite configuration isolation,
# ensuring developer overrides in local .env do not fail base configuration tests.
os.environ["BROKER_MODE"] = "ibkr_readonly"
os.environ["DISABLE_AUTH_ENFORCEMENT"] = "true"
os.environ["PERSISTENCE_BACKEND"] = "json"
os.environ["SCHEDULER_RUN_IN_API"] = "false"
os.environ["ENVIRONMENT"] = "development"


@pytest.fixture(autouse=True)
def isolated_json_state(tmp_path, monkeypatch):
    """Isolate JSON state, audit logs, and ledger files per test (Windows-safe keys)."""
    state_root = tmp_path / "state"
    data_root = tmp_path / "data"
    state_root.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("app.db.state_store._data_dir", lambda: str(state_root))
    monkeypatch.setenv("PERSISTENCE_BACKEND", "json")
    monkeypatch.setattr("app.core.audit.settings.persistence_backend", "json")
    monkeypatch.setattr("app.core.config.settings.persistence_backend", "json")

    monkeypatch.setattr("app.services.portfolio.ledger_coverage.DATA_DIR", str(data_root))
    monkeypatch.setattr("app.services.portfolio.transaction_store.DATA_DIR", str(data_root))
    monkeypatch.setattr("app.services.portfolio.pnl_tracker.DATA_DIR", str(data_root))

    audit_file = data_root / "audit_logs.json"
    monkeypatch.setattr("app.core.audit.AUDIT_LOG_FILE", str(audit_file))

    def _audit_read(namespace, record_key, legacy_path, default=None):
        if namespace == "audit_logs" and record_key == "events":
            if audit_file.exists():
                import json

                with open(audit_file, "r", encoding="utf-8") as handle:
                    return json.load(handle)
            return default if default is not None else []
        from app.db.legacy_bridge import read_json_with_legacy as original

        return original(namespace, record_key, legacy_path, default)

    def _audit_write(namespace, record_key, payload):
        if namespace == "audit_logs" and record_key == "events":
            import json

            audit_file.parent.mkdir(parents=True, exist_ok=True)
            with open(audit_file, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            return
        from app.db.legacy_bridge import write_json_state as original

        original(namespace, record_key, payload)

    monkeypatch.setattr("app.core.audit.read_json_with_legacy", _audit_read)
    monkeypatch.setattr("app.core.audit.write_json_state", _audit_write)

    yield tmp_path
