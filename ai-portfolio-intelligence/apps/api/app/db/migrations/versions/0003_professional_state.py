"""professional state and scheduler jobs

Revision ID: 0003_professional_state
Revises: 0002_financial_ledger
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_professional_state"
down_revision = "0002_financial_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "professional_state_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("namespace", sa.String(length=64), nullable=False),
        sa.Column("record_key", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("namespace", "record_key", name="uq_professional_state_namespace_key"),
    )
    op.create_index(
        "ix_professional_state_namespace",
        "professional_state_records",
        ["namespace"],
    )

    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64)),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "job_name",
            "account_id",
            "business_date",
            "slot",
            name="uq_scheduled_jobs_idempotency",
        ),
    )


def downgrade() -> None:
    op.drop_table("scheduled_jobs")
    op.drop_index("ix_professional_state_namespace", table_name="professional_state_records")
    op.drop_table("professional_state_records")
