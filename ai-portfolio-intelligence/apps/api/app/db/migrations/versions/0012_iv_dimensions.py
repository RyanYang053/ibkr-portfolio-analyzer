"""IV observation dimensions for tenor and moneyness

Revision ID: 0012_iv_dimensions
Revises: 0011_position_lineage_conid
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_iv_dimensions"
down_revision = "0011_position_lineage_conid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("iv_observations", sa.Column("option_right", sa.String(length=4), server_default="C"))
    op.add_column("iv_observations", sa.Column("days_to_expiry", sa.Integer()))
    op.add_column("iv_observations", sa.Column("delta", sa.Float()))
    op.add_column("iv_observations", sa.Column("moneyness", sa.Float()))
    op.add_column("iv_observations", sa.Column("quote_timestamp", sa.DateTime(timezone=True)))

    op.drop_constraint("uq_iv_observations_symbol_date_source", "iv_observations", type_="unique")
    op.create_unique_constraint(
        "uq_iv_observations_symbol_date_source",
        "iv_observations",
        ["symbol", "observation_date", "source", "option_right", "days_to_expiry"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_iv_observations_symbol_date_source", "iv_observations", type_="unique")
    op.create_unique_constraint(
        "uq_iv_observations_symbol_date_source",
        "iv_observations",
        ["symbol", "observation_date", "source"],
    )
    for column in ("quote_timestamp", "moneyness", "delta", "days_to_expiry", "option_right"):
        op.drop_column("iv_observations", column)
