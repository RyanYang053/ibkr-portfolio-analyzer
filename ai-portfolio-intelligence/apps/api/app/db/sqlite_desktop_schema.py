"""Create Decision OS tables on desktop SQLite without requiring full Alembic chain.

Desktop SQLite uses create_all for Decision OS tables (0028+) plus state store.
Pre-0028 broker/ledger tables remain Postgres-oriented; desktop never needs a
cold Alembic upgrade from 0001 on SQLite.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    inspect,
    text,
)
from sqlalchemy.exc import SQLAlchemyError

from app.db.migration_types import json_document_type
from app.db.state_store import ensure_sql_state_table


def _decision_os_metadata() -> MetaData:
    metadata = MetaData()

    Table(
        "evidence_records",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("evidence_id", String(64), nullable=False, unique=True),
        Column("evidence_type", String(128), nullable=False),
        Column("provider", String(128), nullable=False),
        Column("source_record_id", String(128), nullable=True),
        Column("account_id", String(64), nullable=True),
        Column("instrument_key", String(128), nullable=True),
        Column("observed_at", DateTime(timezone=True), nullable=False),
        Column("effective_at", DateTime(timezone=True), nullable=True),
        Column("available_at", DateTime(timezone=True), nullable=False),
        Column("expires_at", DateTime(timezone=True), nullable=True),
        Column("quality_status", String(32), nullable=False),
        Column("methodology_id", String(128), nullable=True),
        Column("methodology_version", String(32), nullable=True),
        Column("calculation_run_id", String(64), nullable=True),
        Column("content_sha256", String(64), nullable=False),
        Column("provisional", Boolean, nullable=False, server_default=text("0")),
        Column("synthetic_demo", Boolean, nullable=False, server_default=text("0")),
        Column("payload_json", json_document_type(), nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )

    Table(
        "decision_packets",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("decision_id", String(64), nullable=False, unique=True),
        Column("account_id", String(64), nullable=False),
        Column("instrument_key", String(128), nullable=False),
        Column("symbol", String(32), nullable=False),
        Column("as_of", DateTime(timezone=True), nullable=False),
        Column("evidence_cutoff", DateTime(timezone=True), nullable=False),
        Column("outcome", String(32), nullable=False),
        Column("candidate_outcome", String(32), nullable=False),
        Column("previous_outcome", String(32), nullable=True),
        Column("priority", String(32), nullable=False),
        Column("confidence_status", String(32), nullable=False),
        Column("implementation_status", String(32), nullable=False),
        Column("packet_sha256", String(64), nullable=False),
        Column("payload_json", json_document_type(), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )

    Table(
        "decision_gates",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("decision_id", String(64), nullable=False),
        Column("gate_id", String(64), nullable=False),
        Column("passed", Boolean, nullable=False),
        Column("terminal", Boolean, nullable=False, server_default=text("0")),
        Column("severity", String(32), nullable=False),
        Column("status", String(32), nullable=False),
        Column("payload_json", json_document_type(), nullable=True),
    )

    Table(
        "decision_scenarios",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("decision_id", String(64), nullable=False),
        Column("scenario_id", String(64), nullable=False, unique=True),
        Column("scenario_type", String(64), nullable=False),
        Column("implementation_ready", Boolean, nullable=False, server_default=text("0")),
        Column("payload_json", json_document_type(), nullable=True),
    )

    Table(
        "decision_evidence_refs",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("decision_id", String(64), nullable=False),
        Column("evidence_id", String(64), nullable=False),
        Column("role", String(32), nullable=False, server_default="supporting"),
    )

    Table(
        "decision_changes",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("decision_id", String(64), nullable=False),
        Column("change_code", String(128), nullable=False),
        Column("payload_json", json_document_type(), nullable=True),
        Column("detected_at", DateTime(timezone=True), nullable=False),
    )

    Table(
        "decision_user_responses",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("decision_id", String(64), nullable=False),
        Column("response", String(64), nullable=False),
        Column("intended_weight", Float, nullable=True),
        Column("reasoning", Text, nullable=True),
        Column("responded_at", DateTime(timezone=True), nullable=False),
        Column("payload_json", json_document_type(), nullable=True),
    )

    Table(
        "portfolio_decision_packets",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("portfolio_decision_id", String(64), nullable=False, unique=True),
        Column("as_of", DateTime(timezone=True), nullable=False),
        Column("packet_sha256", String(64), nullable=False),
        Column("payload_json", json_document_type(), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )

    Table(
        "portfolio_decision_members",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("portfolio_decision_id", String(64), nullable=False),
        Column("decision_id", String(64), nullable=False),
        Column("account_id", String(64), nullable=False),
    )

    Table(
        "financial_plans",
        metadata,
        Column("plan_id", String(64), primary_key=True),
        Column("payload_json", json_document_type(), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=True),
    )

    Table(
        "decision_calibration_observations",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("decision_id", String(64), nullable=False),
        Column("outcome", String(32), nullable=False),
        Column("user_response", String(64), nullable=True),
        Column("realized_label", String(64), nullable=True),
        Column("payload_json", json_document_type(), nullable=True),
        Column("recorded_at", DateTime(timezone=True), nullable=False),
    )

    Table(
        "valuation_model_approvals",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("model_id", String(128), nullable=False),
        Column("version", String(32), nullable=False),
        Column("status", String(32), nullable=False),
        Column("approver", String(128), nullable=True),
        Column("approved_at", DateTime(timezone=True), nullable=True),
        Column("payload_json", json_document_type(), nullable=True),
        UniqueConstraint("model_id", "version", name="uq_valuation_model_approvals"),
    )

    Table(
        "personal_methodology_approvals",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("methodology_id", String(128), nullable=False),
        Column("version", String(32), nullable=False),
        Column("approver", String(128), nullable=False),
        Column("status", String(32), nullable=False),
        Column("notes", Text, nullable=True),
        Column("payload_json", json_document_type(), nullable=True),
        Column("approved_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint("methodology_id", "version", name="uq_personal_methodology_approvals"),
    )

    Table(
        "tax_reconciliation_runs",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("run_id", String(64), nullable=False, unique=True),
        Column("account_id", String(64), nullable=False),
        Column("tax_year", Integer, nullable=False),
        Column("status", String(32), nullable=False),
        Column("payload_json", json_document_type(), nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )

    Table(
        "monitoring_events",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("event_id", String(64), nullable=False, unique=True),
        Column("account_id", String(64), nullable=False),
        Column("instrument_key", String(128), nullable=True),
        Column("rule_id", String(64), nullable=True),
        Column("rule_type", String(64), nullable=True),
        Column("severity", String(32), nullable=False),
        Column("message", Text, nullable=True),
        Column("payload_json", json_document_type(), nullable=True),
        Column("detected_at", DateTime(timezone=True), nullable=False),
    )

    Table(
        "notification_outbox",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("notification_id", String(64), nullable=False, unique=True),
        Column("account_id", String(64), nullable=False),
        Column("title", String(256), nullable=False),
        Column("body", Text, nullable=False),
        Column("severity", String(32), nullable=False),
        Column("category", String(64), nullable=False),
        Column("status", String(32), nullable=False),
        Column("payload_json", json_document_type(), nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("delivered_at", DateTime(timezone=True), nullable=True),
    )

    Table(
        "resolved_alerts",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("alert_id", Integer, nullable=False, unique=True),
        Column("account_id", String(64), nullable=True),
        Column("resolved_at", DateTime(timezone=True), nullable=False),
        Column("payload_json", json_document_type(), nullable=True),
    )

    return metadata


def ensure_decision_os_sqlite_tables() -> dict[str, object]:
    """Idempotent create for Decision OS tables used by desktop sqlite mode.

    Returns ``{"ok": True, ...}`` only when every required table is present after
    creation. Callers MUST fail closed on ``{"ok": False}`` (plan P0.1) — the app
    must never start with an incomplete canonical schema.
    """
    ensure_sql_state_table()
    # Import at call time so a rebound engine (desktop bootstrap / tests) is honored.
    from app.db.session import engine

    metadata = _decision_os_metadata()
    required = sorted(metadata.tables.keys())
    created: list[str] = []
    try:
        metadata.create_all(bind=engine, checkfirst=True)
        created = sorted(metadata.tables.keys())
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
        # Verify the tables actually exist rather than trusting create_all.
        inspector = inspect(engine)
        present = set(inspector.get_table_names())
        missing = [name for name in required if name not in present]
        if missing:
            return {"ok": False, "error": f"missing tables: {missing}", "missing": missing, "tables": created}
    except SQLAlchemyError as exc:
        return {"ok": False, "error": str(exc), "tables": created}
    return {"ok": True, "tables": created, "required": required, "schema_pin": "0036"}
