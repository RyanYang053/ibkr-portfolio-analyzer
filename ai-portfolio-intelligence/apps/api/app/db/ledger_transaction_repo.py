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
                SELECT account_id, transaction_id, symbol, con_id, local_symbol, trade_date,
                       trade_timestamp, effective_timestamp, settlement_date, action,
                       quantity, price, commission, currency, fx_rate, amount, source,
                       source_batch_id, source_row_id, source_hash, description
                FROM ledger_transactions
                WHERE account_id = :account_id
                ORDER BY trade_timestamp ASC NULLS LAST, trade_date ASC,
                         source_row_id ASC, transaction_id ASC
                """
            ),
            {"account_id": account_id},
        ).mappings().all()

    if not rows:
        return None

    payload: list[dict[str, Any]] = []
    for row in rows:
        trade_date = row["trade_date"]
        item: dict[str, Any] = {
            "account_id": row["account_id"],
            "transaction_id": row["transaction_id"],
            "symbol": row["symbol"],
            "con_id": row["con_id"],
            "local_symbol": row.get("local_symbol"),
            "trade_date": trade_date.isoformat() if isinstance(trade_date, date) else trade_date,
            "action": row["action"],
            "quantity": float(row["quantity"]),
            "price": float(row["price"]),
            "commission": float(row["commission"] or 0.0),
            "currency": row["currency"],
            "source": row["source"],
        }
        for field in (
            "trade_timestamp",
            "effective_timestamp",
            "settlement_date",
            "fx_rate",
            "amount",
            "source_batch_id",
            "source_row_id",
            "source_hash",
            "description",
        ):
            value = row.get(field)
            if value is None:
                continue
            if isinstance(value, datetime):
                item[field] = value.isoformat()
            elif isinstance(value, date):
                item[field] = value.isoformat()
            else:
                item[field] = value
        payload.append(item)
    return payload


def replace_transactions(account_id: str, transactions: list[Transaction]) -> None:
    if not _table_available() or not transactions:
        return

    from app.db.session import SessionLocal
    from app.services.portfolio.transaction_store import _transaction_key

    now = _utc_now()
    with SessionLocal() as session:
        for txn in transactions:
            transaction_id = txn.transaction_id or _transaction_key(txn)
            session.execute(
                text(
                    """
                    INSERT INTO ledger_transactions (
                        account_id, transaction_id, symbol, con_id, local_symbol, trade_date,
                        trade_timestamp, effective_timestamp, settlement_date, action,
                        quantity, price, commission, currency, fx_rate, amount, source,
                        source_batch_id, source_row_id, source_hash, description, ingested_at
                    ) VALUES (
                        :account_id, :transaction_id, :symbol, :con_id, :local_symbol, :trade_date,
                        :trade_timestamp, :effective_timestamp, :settlement_date, :action,
                        :quantity, :price, :commission, :currency, :fx_rate, :amount, :source,
                        :source_batch_id, :source_row_id, :source_hash, :description, :ingested_at
                    )
                    ON CONFLICT ON CONSTRAINT uq_ledger_transactions_account_txn
                    DO UPDATE SET
                        symbol = EXCLUDED.symbol,
                        con_id = EXCLUDED.con_id,
                        local_symbol = EXCLUDED.local_symbol,
                        trade_date = EXCLUDED.trade_date,
                        trade_timestamp = EXCLUDED.trade_timestamp,
                        effective_timestamp = EXCLUDED.effective_timestamp,
                        settlement_date = EXCLUDED.settlement_date,
                        action = EXCLUDED.action,
                        quantity = EXCLUDED.quantity,
                        price = EXCLUDED.price,
                        commission = EXCLUDED.commission,
                        currency = EXCLUDED.currency,
                        fx_rate = EXCLUDED.fx_rate,
                        amount = EXCLUDED.amount,
                        source = EXCLUDED.source,
                        source_batch_id = EXCLUDED.source_batch_id,
                        source_row_id = EXCLUDED.source_row_id,
                        source_hash = EXCLUDED.source_hash,
                        description = EXCLUDED.description,
                        ingested_at = EXCLUDED.ingested_at
                    """
                ),
                {
                    "account_id": account_id,
                    "transaction_id": transaction_id,
                    "symbol": txn.symbol,
                    "con_id": txn.con_id,
                    "local_symbol": txn.local_symbol,
                    "trade_date": txn.trade_date,
                    "trade_timestamp": txn.trade_timestamp,
                    "effective_timestamp": txn.effective_timestamp,
                    "settlement_date": txn.settlement_date,
                    "action": txn.action,
                    "quantity": float(txn.quantity),
                    "price": float(txn.price),
                    "commission": float(txn.commission),
                    "currency": txn.currency,
                    "fx_rate": txn.fx_rate,
                    "amount": txn.amount,
                    "source": txn.source,
                    "source_batch_id": txn.source_batch_id,
                    "source_row_id": txn.source_row_id,
                    "source_hash": txn.source_hash,
                    "description": txn.description,
                    "ingested_at": now,
                },
            )
        session.commit()
