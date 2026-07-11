"""SEC EDGAR shared rate gate and audit immutability role fix

Revision ID: 0026_sec_gate_audit
Revises: 0025_tax_lot_transition
Create Date: 2026-07-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0026_sec_gate_audit"
down_revision = "0025_tax_lot_transition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sec_edgar_request_gate",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column(
            "last_request_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMESTAMPTZ '1970-01-01 00:00:00+00'"),
        ),
        sa.CheckConstraint("id = 1", name="ck_sec_edgar_request_gate_singleton"),
    )
    op.execute(
        """
        INSERT INTO sec_edgar_request_gate (id, last_request_at)
        VALUES (1, TIMESTAMPTZ '1970-01-01 00:00:00+00')
        ON CONFLICT (id) DO NOTHING
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_audit_events_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF coalesce(current_setting('app.audit_mutations_blocked', true), 'off') = 'on' THEN
                RAISE EXCEPTION 'audit_events are immutable for application sessions';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_audit_events_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF current_user = 'portfolio' THEN
                RAISE EXCEPTION 'audit_events are immutable for application role';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.drop_table("sec_edgar_request_gate")
