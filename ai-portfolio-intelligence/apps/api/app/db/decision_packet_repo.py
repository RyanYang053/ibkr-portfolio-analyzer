"""Decision Packet repository — SQLite/Postgres/JSON-backed."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.db.state_store import get_state_store
from app.schemas.decision_packet import HoldingDecisionPacket

_NAMESPACE = "decision_packets"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _packet_sort_key(packet: HoldingDecisionPacket) -> tuple[str, str]:
    """Newest-first ordering. ``decision_id`` breaks ties within the same
    ``as_of`` so the choice of current packet is stable across requests."""
    return (str(packet.as_of or ""), str(packet.decision_id or ""))


class DecisionPacketRepository:
    def save(self, packet: HoldingDecisionPacket) -> HoldingDecisionPacket:
        payload = packet.model_dump(mode="json")
        if settings.persistence_backend in {"postgres", "sqlite"}:
            try:
                self._save_db(payload)
            except Exception:
                pass
        store = get_state_store()
        store.write_json(_NAMESPACE, packet.decision_id, payload)
        store.write_json(
            _NAMESPACE,
            f"latest:{packet.account_id}:{packet.instrument_key}",
            {"decision_id": packet.decision_id, "payload": payload},
        )
        index = store.read_json(_NAMESPACE, f"index:{packet.account_id}", default={"decision_ids": []}) or {}
        ids = list(index.get("decision_ids") or [])
        if packet.decision_id not in ids:
            ids.insert(0, packet.decision_id)
        store.write_json(_NAMESPACE, f"index:{packet.account_id}", {"decision_ids": ids[:500]})
        return packet

    def latest_for_instrument(self, account_id: str, instrument_key: str) -> HoldingDecisionPacket | None:
        if settings.persistence_backend in {"postgres", "sqlite"}:
            try:
                row = self._latest_db(account_id, instrument_key)
                if row:
                    return HoldingDecisionPacket.model_validate(row)
            except Exception:
                pass
        store = get_state_store()
        latest = store.read_json(_NAMESPACE, f"latest:{account_id}:{instrument_key}", default=None)
        if not latest:
            return None
        payload = latest.get("payload") or latest
        return HoldingDecisionPacket.model_validate(payload)

    def get(self, decision_id: str) -> HoldingDecisionPacket | None:
        if settings.persistence_backend in {"postgres", "sqlite"}:
            try:
                row = self._get_db(decision_id)
                if row:
                    return HoldingDecisionPacket.model_validate(row)
            except Exception:
                pass
        store = get_state_store()
        payload = store.read_json(_NAMESPACE, decision_id, default=None)
        if not payload:
            return None
        return HoldingDecisionPacket.model_validate(payload)

    def list_for_account(self, account_id: str, limit: int = 100) -> list[HoldingDecisionPacket]:
        """Every stored packet, newest first — the audit history.

        Contains superseded packets for an instrument as well as the current
        one. Callers rendering "what needs a decision now" want
        :meth:`list_current_for_account` instead.
        """
        store = get_state_store()
        index = store.read_json(_NAMESPACE, f"index:{account_id}", default={}) or {}
        packets: list[HoldingDecisionPacket] = []
        for decision_id in list(index.get("decision_ids") or [])[:limit]:
            packet = self.get(str(decision_id))
            if packet:
                packets.append(packet)
        return packets

    def list_current_for_account(
        self, account_id: str, limit: int = 100
    ) -> list[HoldingDecisionPacket]:
        """The one live packet per instrument.

        Each evaluation writes a new packet and appends it to the account index,
        so the raw history holds several packets for the same holding. A review
        queue built from that history repeats every symbol once per evaluation;
        collapsing to the newest packet per instrument keeps the queue equal to
        the number of open decisions.
        """
        # Read past `limit` before collapsing: the window is over packets, and
        # older evaluations of the same instrument would otherwise crowd out
        # instruments that have not been re-evaluated recently.
        history = self.list_for_account(account_id, limit=max(limit, 500))

        current: dict[str, HoldingDecisionPacket] = {}
        for packet in history:
            existing = current.get(packet.instrument_key)
            if existing is None or _packet_sort_key(packet) > _packet_sort_key(existing):
                current[packet.instrument_key] = packet

        ordered = sorted(current.values(), key=_packet_sort_key, reverse=True)
        return ordered[:limit]

    def _save_db(self, payload: dict[str, Any]) -> None:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(
                text(
                    """
                    INSERT INTO decision_packets (
                        decision_id, account_id, instrument_key, symbol, as_of,
                        evidence_cutoff, outcome, candidate_outcome, previous_outcome,
                        priority, confidence_status, implementation_status,
                        packet_sha256, payload_json, created_at
                    ) VALUES (
                        :decision_id, :account_id, :instrument_key, :symbol, :as_of,
                        :evidence_cutoff, :outcome, :candidate_outcome, :previous_outcome,
                        :priority, :confidence_status, :implementation_status,
                        :packet_sha256, :payload_json, :created_at
                    )
                    ON CONFLICT (decision_id) DO NOTHING
                    """
                ),
                {
                    "decision_id": payload["decision_id"],
                    "account_id": payload["account_id"],
                    "instrument_key": payload["instrument_key"],
                    "symbol": payload["symbol"],
                    "as_of": payload["as_of"],
                    "evidence_cutoff": payload["evidence_cutoff"],
                    "outcome": payload["outcome"],
                    "candidate_outcome": payload["candidate_outcome"],
                    "previous_outcome": payload.get("previous_outcome"),
                    "priority": payload.get("priority"),
                    "confidence_status": payload.get("confidence_status"),
                    "implementation_status": str(payload.get("implementation_status")),
                    "packet_sha256": payload.get("packet_sha256"),
                    "payload_json": json.dumps(payload),
                    "created_at": _now().isoformat(),
                },
            )
            session.commit()

    def _latest_db(self, account_id: str, instrument_key: str) -> dict[str, Any] | None:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text(
                    """
                    SELECT payload_json FROM decision_packets
                    WHERE account_id = :account_id AND instrument_key = :instrument_key
                    ORDER BY as_of DESC LIMIT 1
                    """
                ),
                {"account_id": account_id, "instrument_key": instrument_key},
            ).fetchone()
        if not row:
            return None
        payload = row[0]
        return json.loads(payload) if isinstance(payload, str) else payload

    def _get_db(self, decision_id: str) -> dict[str, Any] | None:
        from sqlalchemy import text

        from app.db.session import SessionLocal

        with SessionLocal() as session:
            row = session.execute(
                text("SELECT payload_json FROM decision_packets WHERE decision_id = :id"),
                {"id": decision_id},
            ).fetchone()
        if not row:
            return None
        payload = row[0]
        return json.loads(payload) if isinstance(payload, str) else payload
