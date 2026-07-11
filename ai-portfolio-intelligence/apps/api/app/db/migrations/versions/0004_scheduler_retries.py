"""scheduler job retry and lease fields

Revision ID: 0004_scheduler_retries
Revises: 0003_professional_state
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_scheduler_retries"
down_revision = "0003_professional_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduled_jobs", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("scheduled_jobs", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("scheduled_jobs", sa.Column("leased_until", sa.DateTime(timezone=True)))
    op.add_column("scheduled_jobs", sa.Column("worker_id", sa.String(length=64)))
    op.add_column("scheduled_jobs", sa.Column("next_retry_at", sa.DateTime(timezone=True)))
    op.add_column("scheduled_jobs", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("scheduled_jobs", "heartbeat_at")
    op.drop_column("scheduled_jobs", "next_retry_at")
    op.drop_column("scheduled_jobs", "worker_id")
    op.drop_column("scheduled_jobs", "leased_until")
    op.drop_column("scheduled_jobs", "max_attempts")
    op.drop_column("scheduled_jobs", "attempt_count")
