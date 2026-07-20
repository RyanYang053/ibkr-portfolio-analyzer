from pathlib import Path

from app.core.config import settings
from app.core.deployment_mode import DeploymentMode
from app.core.desktop_bootstrap import backup_desktop_data, export_desktop_archive, portfolio_data_root


def test_portfolio_data_root_honors_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "deployment_mode", DeploymentMode.DESKTOP_LOCAL)
    root = portfolio_data_root()
    assert root == tmp_path
    assert (root / "exports").is_dir()
    assert (root / "backups").is_dir()


def test_backup_and_export_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTFOLIO_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "deployment_mode", DeploymentMode.DESKTOP_LOCAL)
    state = portfolio_data_root() / "state" / "demo"
    state.mkdir(parents=True)
    (state / "sample.json").write_text('{"ok": true}', encoding="utf-8")

    backup = backup_desktop_data(reason="test")
    assert backup is not None
    assert backup.exists()

    export_path = export_desktop_archive()
    assert export_path.exists()
    assert export_path.parent == Path(tmp_path) / "exports"
