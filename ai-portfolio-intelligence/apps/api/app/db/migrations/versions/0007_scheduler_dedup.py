"""deduplicate scheduled_jobs before non-null account_id enforcement

Revision ID: 0007_scheduler_dedup
Revises: 0006_scheduler_claims
Create Date: 2026-07-10
"""
from alembic import op

revision = "0007_scheduler_dedup"
down_revision = "0006_scheduler_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM scheduled_jobs old
        USING scheduled_jobs newer
        WHERE old.job_name = newer.job_name
          AND old.business_date = newer.business_date
          AND old.slot = newer.slot
          AND COALESCE(old.account_id, '__all__') = COALESCE(newer.account_id, '__all__')
          AND old.id < newer.id
        """
    )


def downgrade() -> None:
    pass
