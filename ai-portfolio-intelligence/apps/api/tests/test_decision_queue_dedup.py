"""The review queue must hold one packet per holding, not one per evaluation.

Every Decision Center evaluation writes a new packet and appends it to the
account index. Building the queue from that raw history repeated each symbol
once per evaluation, so the queue grew on every page load.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.product_contract import DecisionOutcome
from app.db.decision_packet_repo import DecisionPacketRepository
from app.schemas.decision_packet import HoldingDecisionPacket


def _packet(
    *,
    decision_id: str,
    symbol: str,
    as_of: datetime,
    account_id: str = "U-TEST",
    outcome: DecisionOutcome = DecisionOutcome.REVIEW_TRIM,
) -> HoldingDecisionPacket:
    return HoldingDecisionPacket(
        decision_id=decision_id,
        account_id=account_id,
        instrument_key=f"{symbol}:STK:USD",
        symbol=symbol,
        as_of=as_of,
        evidence_cutoff=as_of,
        outcome=outcome,
        candidate_outcome=outcome,
    )


@pytest.fixture()
def repo() -> DecisionPacketRepository:
    return DecisionPacketRepository()


def test_repeated_evaluations_collapse_to_one_packet_per_instrument(repo):
    base = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    for index in range(5):
        repo.save(_packet(decision_id=f"dec_msft_{index}", symbol="MSFT", as_of=base + timedelta(minutes=index)))
        repo.save(_packet(decision_id=f"dec_spy_{index}", symbol="SPY", as_of=base + timedelta(minutes=index)))

    history = repo.list_for_account("U-TEST")
    assert len(history) == 10, "history keeps every evaluation for audit"

    current = repo.list_current_for_account("U-TEST")
    assert [packet.symbol for packet in sorted(current, key=lambda p: p.symbol)] == ["MSFT", "SPY"]


def test_current_listing_returns_the_newest_packet_for_an_instrument(repo):
    base = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    repo.save(
        _packet(
            decision_id="dec_old",
            symbol="NKE",
            as_of=base,
            outcome=DecisionOutcome.REVIEW_TRIM,
        )
    )
    repo.save(
        _packet(
            decision_id="dec_new",
            symbol="NKE",
            as_of=base + timedelta(hours=3),
            outcome=DecisionOutcome.REVIEW_EXIT,
        )
    )

    current = repo.list_current_for_account("U-TEST")
    assert len(current) == 1
    assert current[0].decision_id == "dec_new"
    assert current[0].outcome == DecisionOutcome.REVIEW_EXIT


def test_current_listing_is_newest_first_and_stable(repo):
    base = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    repo.save(_packet(decision_id="dec_a", symbol="AAA", as_of=base))
    repo.save(_packet(decision_id="dec_b", symbol="BBB", as_of=base + timedelta(minutes=1)))
    repo.save(_packet(decision_id="dec_c", symbol="CCC", as_of=base + timedelta(minutes=2)))

    first = [packet.symbol for packet in repo.list_current_for_account("U-TEST")]
    assert first == ["CCC", "BBB", "AAA"]
    assert first == [packet.symbol for packet in repo.list_current_for_account("U-TEST")]


def test_instruments_beyond_the_limit_window_are_not_crowded_out(repo):
    """Old evaluations of one symbol must not push other holdings off the queue."""
    base = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    repo.save(_packet(decision_id="dec_rare", symbol="RARE", as_of=base))
    for index in range(60):
        repo.save(
            _packet(
                decision_id=f"dec_busy_{index}",
                symbol="BUSY",
                as_of=base + timedelta(minutes=index + 1),
            )
        )

    symbols = {packet.symbol for packet in repo.list_current_for_account("U-TEST", limit=10)}
    assert symbols == {"BUSY", "RARE"}
