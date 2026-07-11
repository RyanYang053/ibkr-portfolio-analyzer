from __future__ import annotations

from datetime import date

import pytest

from app.db.portfolio_snapshot_repo import configured_snapshot_tolerance, require_complete_snapshot


def test_configured_snapshot_tolerance():
    assert configured_snapshot_tolerance(100_000) >= 1.0


def test_require_complete_snapshot_raises_when_missing():
    with pytest.raises(ValueError, match="designated EOD snapshot missing"):
        require_complete_snapshot("missing-account", date(2026, 1, 1))
