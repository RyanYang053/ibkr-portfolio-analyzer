"""scheduler fencing token and non-null account_id

Revision ID: 0006_scheduler_claims
Revises: 0005_auth_identity
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_scheduler_claims"
down_revision = "0005_auth_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduled_jobs", sa.Column("fencing_token", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE scheduled_jobs SET account_id = '__all__' WHERE account_id IS NULL")
    # batch_alter_table recreates the table on SQLite (no ALTER COLUMN); emits ALTER on Postgres.
    with op.batch_alter_table("scheduled_jobs") as batch_op:
        batch_op.alter_column("account_id", existing_type=sa.String(length=64), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("scheduled_jobs") as batch_op:
        batch_op.alter_column("account_id", existing_type=sa.String(length=64), nullable=True)
    op.drop_column("scheduled_jobs", "fencing_token")
