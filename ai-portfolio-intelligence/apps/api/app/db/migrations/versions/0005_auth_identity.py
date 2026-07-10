"""auth identity tables and user token version

Revision ID: 0005_auth_identity
Revises: 0004_scheduler_retries
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_auth_identity"
down_revision = "0004_scheduler_retries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "broker_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("broker", sa.String(length=64), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_broker_connections_user_id", "broker_connections", ["user_id"])
    op.create_table(
        "user_account_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("external_account_id", sa.String(length=64), nullable=False),
        sa.Column("access_level", sa.String(length=32), nullable=False, server_default="read"),
        sa.Column("granted_by_user_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "external_account_id", name="uq_user_account_access_user_account"),
    )
    op.create_index("ix_user_account_access_user_id", "user_account_access", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_account_access_user_id", table_name="user_account_access")
    op.drop_table("user_account_access")
    op.drop_index("ix_broker_connections_user_id", table_name="broker_connections")
    op.drop_table("broker_connections")
    op.drop_column("users", "token_version")
