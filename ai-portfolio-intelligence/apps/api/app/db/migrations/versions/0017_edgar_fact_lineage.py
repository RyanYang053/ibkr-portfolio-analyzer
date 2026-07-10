"""SEC EDGAR fact lineage and ticker cache

Revision ID: 0017_edgar_fact_lineage
Revises: 0016_position_snapshot_lineage
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017_edgar_fact_lineage"
down_revision = "0016_position_snapshot_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sec_ticker_map_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("cached_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cache_key", name="uq_sec_ticker_map_cache_key"),
    )

    op.create_table(
        "sec_company_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("cik", sa.String(length=16), nullable=False),
        sa.Column("entity_name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload_json", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "source_hash", name="uq_sec_company_facts_symbol_hash"),
    )
    op.create_index("ix_sec_company_facts_symbol_fetched_at", "sec_company_facts", ["symbol", "fetched_at"])

    op.create_table(
        "sec_fact_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("cik", sa.String(length=16), nullable=False),
        sa.Column("concept", sa.String(length=128), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Numeric(28, 8), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("filed_date", sa.Date(), nullable=True),
        sa.Column("accepted_at", sa.String(length=64), nullable=True),
        sa.Column("accn", sa.String(length=32), nullable=True),
        sa.Column("form", sa.String(length=16), nullable=True),
        sa.Column("fy", sa.Integer(), nullable=True),
        sa.Column("fp", sa.String(length=8), nullable=True),
        sa.Column("frame", sa.String(length=32), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_hash", sa.String(length=64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "symbol",
            "concept",
            "unit",
            "start_date",
            "end_date",
            "form",
            "fp",
            "frame",
            name="uq_sec_fact_observations_identity",
        ),
    )
    op.create_index(
        "ix_sec_fact_observations_symbol_concept_filed",
        "sec_fact_observations",
        ["symbol", "concept", "filed_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_sec_fact_observations_symbol_concept_filed", table_name="sec_fact_observations")
    op.drop_table("sec_fact_observations")
    op.drop_index("ix_sec_company_facts_symbol_fetched_at", table_name="sec_company_facts")
    op.drop_table("sec_company_facts")
    op.drop_table("sec_ticker_map_cache")
