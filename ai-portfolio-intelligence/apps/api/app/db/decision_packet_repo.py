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
        store = get_state_store()
        index = store.read_json(_NAMESPACE, f"index:{account_id}", default={}) or {}
        packets: list[HoldingDecisionPacket] = []
        for decision_id in list(index.get("decision_ids") or [])[:limit]:
            packet = self.get(str(decision_id))
            if packet:
                packets.append(packet)
        return packets

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
