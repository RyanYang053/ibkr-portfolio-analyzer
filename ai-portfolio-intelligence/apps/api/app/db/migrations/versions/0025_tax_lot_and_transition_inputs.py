"""tax lot snapshots and optimizer transition inputs

Revision ID: 0025_tax_lot_transition
Revises: 0024_benchmark_attribution
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op

from app.db.migration_types import (
    json_document_type,
    json_server_default_empty_object,
    uuid_column_type,
    uuid_server_default,
)

revision = "0025_tax_lot_transition"
down_revision = "0024_benchmark_attribution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tax_lot_snapshots",
        sa.Column("id", uuid_column_type(), primary_key=True, server_default=uuid_server_default()),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("con_id", sa.BigInteger(), nullable=True),
        sa.Column("quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("cost_basis_per_share", sa.Numeric(28, 8), nullable=False),
        sa.Column("acquired_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("jurisdiction", sa.String(length=8), nullable=False),
        sa.Column("lot_method", sa.String(length=32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column(
            "payload_json",
            json_document_type(),
            nullable=False,
            server_default=json_server_default_empty_object(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_tax_lot_snapshots_account_asof", "tax_lot_snapshots", ["account_id", "as_of_date"])
    op.create_table(
        "tax_affiliated_accounts",
        sa.Column("id", uuid_column_type(), primary_key=True, server_default=uuid_server_default()),
        sa.Column("household_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("relationship", sa.String(length=64), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_tax_affiliated_accounts_household", "tax_affiliated_accounts", ["household_id"])
    op.create_table(
        "tax_transition_inputs",
        sa.Column("id", uuid_column_type(), primary_key=True, server_default=uuid_server_default()),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("jurisdiction", sa.String(length=8), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False),
        sa.Column("tax_budget", sa.Numeric(18, 2), nullable=True),
        sa.Column("available_loss_offsets", sa.Numeric(18, 2), nullable=True),
        sa.Column("wash_sale_window_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("superficial_loss_window_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column(
            "constraints_json",
            json_document_type(),
            nullable=False,
            server_default=json_server_default_empty_object(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_tax_transition_inputs_account_effective", "tax_transition_inputs", ["account_id", "effective_date"])


def downgrade() -> None:
    op.drop_index("ix_tax_transition_inputs_account_effective", table_name="tax_transition_inputs")
    op.drop_table("tax_transition_inputs")
    op.drop_index("ix_tax_affiliated_accounts_household", table_name="tax_affiliated_accounts")
    op.drop_table("tax_affiliated_accounts")
    op.drop_index("ix_tax_lot_snapshots_account_asof", table_name="tax_lot_snapshots")
    op.drop_table("tax_lot_snapshots")
