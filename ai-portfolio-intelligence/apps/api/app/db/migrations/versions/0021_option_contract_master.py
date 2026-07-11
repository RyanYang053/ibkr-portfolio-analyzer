"""option contract master for live Greeks and risk repricing

Revision ID: 0021_option_contract_master
Revises: 0020_login_rate_limit_audit
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021_option_contract_master"
down_revision = "0020_login_rate_limit_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "option_contracts",
        sa.Column("con_id", sa.BigInteger(), primary_key=True),
        sa.Column("underlying_con_id", sa.BigInteger(), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("local_symbol", sa.String(length=64), nullable=True),
        sa.Column("right", sa.String(length=1), nullable=False),
        sa.Column("strike", sa.Float(), nullable=False),
        sa.Column("expiration", sa.Date(), nullable=False),
        sa.Column("multiplier", sa.Float(), nullable=False, server_default="100"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("trading_class", sa.String(length=32), nullable=True),
        sa.Column("exercise_style", sa.String(length=16), nullable=True),
        sa.Column("settlement_type", sa.String(length=16), nullable=True),
        sa.Column("last_trade_date", sa.Date(), nullable=True),
        sa.Column("quote_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bid", sa.Float(), nullable=True),
        sa.Column("ask", sa.Float(), nullable=True),
        sa.Column("mid", sa.Float(), nullable=True),
        sa.Column("implied_volatility", sa.Float(), nullable=True),
        sa.Column("delta", sa.Float(), nullable=True),
        sa.Column("gamma", sa.Float(), nullable=True),
        sa.Column("vega", sa.Float(), nullable=True),
        sa.Column("theta", sa.Float(), nullable=True),
        sa.Column("rho", sa.Float(), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("market_data_type", sa.String(length=32), nullable=True),
        sa.Column("greeks_source", sa.String(length=32), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("source_batch_id", sa.String(length=36), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_option_contracts_symbol", "option_contracts", ["symbol"])
    op.create_index("ix_option_contracts_underlying_con_id", "option_contracts", ["underlying_con_id"])
    op.create_index("ix_option_contracts_expiration", "option_contracts", ["expiration"])


def downgrade() -> None:
    op.drop_index("ix_option_contracts_expiration", table_name="option_contracts")
    op.drop_index("ix_option_contracts_underlying_con_id", table_name="option_contracts")
    op.drop_index("ix_option_contracts_symbol", table_name="option_contracts")
    op.drop_table("option_contracts")
