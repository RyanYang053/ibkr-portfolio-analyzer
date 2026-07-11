"""identity and invitation hardening

Revision ID: 0013_identity_and_invitation_hardening
Revises: 0012_iv_dimensions
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_identity_and_invitation_hardening"
down_revision = "0012_iv_dimensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_invitations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("token_digest", sa.CHAR(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("invited_by_email", sa.String(length=320), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("token_digest", name="uq_user_invitations_token_digest"),
        sa.CheckConstraint("role IN ('owner', 'viewer')", name="ck_user_invitations_role"),
    )
    op.create_index(
        "ix_user_invitations_email",
        "user_invitations",
        [sa.text("lower(email)")],
    )


def downgrade() -> None:
    op.drop_index("ix_user_invitations_email", table_name="user_invitations")
    op.drop_table("user_invitations")
