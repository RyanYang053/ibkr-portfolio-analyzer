from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.state_store import postgres_available
from app.schemas.domain import Transaction


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_available() -> bool:
    if not postgres_available():
        return False
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            session.execute(text("SELECT 1 FROM ledger_transactions LIMIT 1"))
        return True
    except SQLAlchemyError:
        return False


def read_transactions(account_id: str) -> list[dict[str, Any]] | None:
    if not _table_available():
        return None

    from app.db.session import SessionLocal

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT account_id, transaction_id, symbol, con_id, trade_date, action,
                       quantity, price, commission, currency, fx_rate, source, description
                FROM ledger_transactions
                WHERE account_id = :account_id
                ORDER BY trade_date ASC, symbol ASC, action ASC
                """
            ),
            {"account_id": account_id},
        ).mappings().all()

    if not rows:
        return None

    payload: list[dict[str, Any]] = []
    for row in rows:
        trade_date = row["trade_date"]
        item = {
            "account_id": row["account_id"],
            "transaction_id": row["transaction_id"],
            "symbol": row["symbol"],
            "con_id": row["con_id"],
            "trade_date": trade_date.isoformat() if isinstance(trade_date, date) else trade_date,
            "action": row["action"],
            "quantity": float(row["quantity"]),
            "price": float(row["price"]),
            "commission": float(row["commission"] or 0.0),
            "currency": row["currency"],
            "source": row["source"],
        }
        if row.get("fx_rate") is not None:
            item["fx_rate"] = float(row["fx_rate"])
        if row.get("description"):
            item["description"] = row["description"]
        payload.append(item)
    return payload


def replace_transactions(account_id: str, transactions: list[Transaction]) -> None:
    if not _table_available() or not transactions:
        return

    from app.db.session import SessionLocal

    def _txn_key(txn: Transaction) -> str:
        if txn.transaction_id:
            return txn.transaction_id
        return "|".join(
            [
                txn.account_id,
                txn.trade_date.isoformat(),
                txn.action,
                txn.symbol,
                str(txn.quantity),
                str(txn.price),
                str(txn.commission),
                txn.currency,
                str(txn.con_id or ""),
            ]
        )

    now = _utc_now()
    with SessionLocal() as session:
        for txn in transactions:
            transaction_id = txn.transaction_id or _txn_key(txn)
            session.execute(
                text(
                    """
                    INSERT INTO ledger_transactions (
                        account_id, transaction_id, symbol, con_id, trade_date, action,
                        quantity, price, commission, currency, fx_rate, source, description, ingested_at
                    ) VALUES (
                        :account_id, :transaction_id, :symbol, :con_id, :trade_date, :action,
                        :quantity, :price, :commission, :currency, :fx_rate, :source, :description, :ingested_at
                    )
                    ON CONFLICT ON CONSTRAINT uq_ledger_transactions_account_txn
                    DO UPDATE SET
                        symbol = EXCLUDED.symbol,
                        con_id = EXCLUDED.con_id,
                        trade_date = EXCLUDED.trade_date,
                        action = EXCLUDED.action,
                        quantity = EXCLUDED.quantity,
                        price = EXCLUDED.price,
                        commission = EXCLUDED.commission,
                        currency = EXCLUDED.currency,
                        fx_rate = EXCLUDED.fx_rate,
                        source = EXCLUDED.source,
                        description = EXCLUDED.description,
                        ingested_at = EXCLUDED.ingested_at
                    """
                ),
                {
                    "account_id": account_id,
                    "transaction_id": transaction_id,
                    "symbol": txn.symbol,
                    "con_id": txn.con_id,
                    "trade_date": txn.trade_date,
                    "action": txn.action,
                    "quantity": float(txn.quantity),
                    "price": float(txn.price),
                    "commission": float(txn.commission),
                    "currency": txn.currency,
                    "fx_rate": txn.fx_rate,
                    "source": txn.source,
                    "description": getattr(txn, "description", None),
                    "ingested_at": now,
                },
            )
        session.commit()
