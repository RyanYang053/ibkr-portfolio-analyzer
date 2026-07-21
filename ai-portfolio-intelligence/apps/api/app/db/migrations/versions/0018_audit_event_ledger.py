"""Immutable audit event ledger

Revision ID: 0018_audit_event_ledger
Revises: 0017_edgar_fact_lineage
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op

from app.db.migration_types import (
    inet_column_type,
    json_document_type,
    json_server_default_empty_object,
    uuid_column_type,
    uuid_server_default,
)

revision = "0018_audit_event_ledger"
down_revision = "0017_edgar_fact_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", uuid_column_type(), primary_key=True, server_default=uuid_server_default()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=320), nullable=False),
        sa.Column("tenant_id", sa.String(length=320), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=256), nullable=True),
        sa.Column("request_id", uuid_column_type(), nullable=True),
        sa.Column("source_ip", inet_column_type(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("before_json", json_document_type(), nullable=True),
        sa.Column("after_json", json_document_type(), nullable=True),
        sa.Column(
            "metadata_json",
            json_document_type(),
            nullable=False,
            server_default=json_server_default_empty_object(),
        ),
    )
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_index("ix_audit_events_account_id", "audit_events", ["account_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_audit_events_account_id", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_id", table_name="audit_events")
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
    op.drop_table("audit_events")
