"""scheduler fencing token and non-null account_id

Revision ID: 0006_scheduler_claims
Revises: 0005_auth_identity
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_scheduler_claims"
down_revision = "0005_auth_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduled_jobs", sa.Column("fencing_token", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE scheduled_jobs SET account_id = '__all__' WHERE account_id IS NULL")
    op.alter_column("scheduled_jobs", "account_id", existing_type=sa.String(length=64), nullable=False)


def downgrade() -> None:
    op.alter_column("scheduled_jobs", "account_id", existing_type=sa.String(length=64), nullable=True)
    op.drop_column("scheduled_jobs", "fencing_token")
