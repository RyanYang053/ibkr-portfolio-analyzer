"""Legacy JSON import stub test."""

from __future__ import annotations

import json
from pathlib import Path

from app.db.legacy_json_import import import_legacy_json_state


def test_legacy_json_import_copies_namespaces_and_marks_migrated(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target" / "state"
    (source / "decision_packets").mkdir(parents=True)
    (source / "financial_plans").mkdir(parents=True)
    (source / "decision_packets" / "sample.json").write_text("{}", encoding="utf-8")
    (source / "financial_plans" / "default.json").write_text('{"plan_id":"default"}', encoding="utf-8")

    result = import_legacy_json_state(source_dir=source, target_dir=target, backup_dir=tmp_path / "backups")
    assert "decision_packets" in result["copied_namespaces"]
    assert "financial_plans" in result["copied_namespaces"]
    assert (target / "decision_packets" / "sample.json").exists()
    marker = json.loads((target / "legacy_json_migrated.json").read_text(encoding="utf-8"))
    assert marker["copied_namespaces"] == result["copied_namespaces"]
