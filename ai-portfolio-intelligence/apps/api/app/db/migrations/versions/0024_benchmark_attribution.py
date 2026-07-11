"""benchmark attribution persistence tables

Revision ID: 0024_benchmark_attribution
Revises: 0023_methodology_governance
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024_benchmark_attribution"
down_revision = "0023_methodology_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmark_definitions",
        sa.Column("benchmark_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "benchmark_constituent_weights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("benchmark_id", sa.String(length=64), sa.ForeignKey("benchmark_definitions.benchmark_id"), nullable=False),
        sa.Column("constituent_key", sa.String(length=128), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("weight", sa.Numeric(18, 8), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_benchmark_constituent_weights_benchmark_effective",
        "benchmark_constituent_weights",
        ["benchmark_id", "effective_date"],
    )
    op.create_table(
        "security_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("con_id", sa.BigInteger(), nullable=True),
        sa.Column("sector", sa.String(length=64), nullable=False),
        sa.Column("asset_class", sa.String(length=32), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_security_classifications_symbol_effective",
        "security_classifications",
        ["symbol", "effective_date"],
    )
    op.create_table(
        "daily_security_returns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("con_id", sa.BigInteger(), nullable=True),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("total_return", sa.Numeric(18, 8), nullable=False),
        sa.Column("price_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("income_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("fx_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_daily_security_returns_account_date",
        "daily_security_returns",
        ["account_id", "return_date"],
    )
    op.create_table(
        "daily_portfolio_weights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("weight_date", sa.Date(), nullable=False),
        sa.Column("constituent_key", sa.String(length=128), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("weight", sa.Numeric(18, 8), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_daily_portfolio_weights_account_date",
        "daily_portfolio_weights",
        ["account_id", "weight_date"],
    )
    op.create_table(
        "daily_attribution_contributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("contribution_date", sa.Date(), nullable=False),
        sa.Column("security_contribution", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("income_contribution", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("fx_contribution", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("fee_contribution", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("tax_contribution", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("allocation_effect", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("selection_effect", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("interaction_effect", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("portfolio_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("benchmark_return", sa.Numeric(18, 8), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_daily_attribution_contributions_account_date",
        "daily_attribution_contributions",
        ["account_id", "contribution_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_attribution_contributions_account_date", table_name="daily_attribution_contributions")
    op.drop_table("daily_attribution_contributions")
    op.drop_index("ix_daily_portfolio_weights_account_date", table_name="daily_portfolio_weights")
    op.drop_table("daily_portfolio_weights")
    op.drop_index("ix_daily_security_returns_account_date", table_name="daily_security_returns")
    op.drop_table("daily_security_returns")
    op.drop_index("ix_security_classifications_symbol_effective", table_name="security_classifications")
    op.drop_table("security_classifications")
    op.drop_index("ix_benchmark_constituent_weights_benchmark_effective", table_name="benchmark_constituent_weights")
    op.drop_table("benchmark_constituent_weights")
    op.drop_table("benchmark_definitions")
