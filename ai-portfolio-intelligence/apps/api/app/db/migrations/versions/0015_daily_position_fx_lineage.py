"""daily position fx lineage

Revision ID: 0015_daily_position_fx_lineage
Revises: 0013_identity_and_invitation_hardening
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_daily_position_fx_lineage"
down_revision = "0013_identity_and_invitation_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("daily_position_snapshots", sa.Column("fx_source", sa.String(length=64), nullable=True))
    op.add_column("daily_position_snapshots", sa.Column("fx_observed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("daily_position_snapshots", sa.Column("fx_rate_date", sa.Date(), nullable=True))
    op.add_column(
        "daily_position_snapshots",
        sa.Column("valuation_status", sa.String(length=32), nullable=False, server_default="available"),
    )


def downgrade() -> None:
    op.drop_column("daily_position_snapshots", "valuation_status")
    op.drop_column("daily_position_snapshots", "fx_rate_date")
    op.drop_column("daily_position_snapshots", "fx_observed_at")
    op.drop_column("daily_position_snapshots", "fx_source")
