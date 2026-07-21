"""login rate limits and audit immutability

Revision ID: 0020_login_rate_limit_audit
Revises: 0019_accounting_hardening
Create Date: 2026-07-10
"""
import sqlalchemy as sa
from alembic import op

from app.db.migration_types import timestamp_now_default

revision = "0020_login_rate_limit_audit"
down_revision = "0019_accounting_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_rate_limits",
        sa.Column("client_key", sa.String(length=320), primary_key=True),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=timestamp_now_default()),
    )

    op.add_column("audit_events", sa.Column("previous_event_hash", sa.CHAR(length=64), nullable=True))
    op.add_column("audit_events", sa.Column("event_hash", sa.CHAR(length=64), nullable=True))

    if op.get_bind().dialect.name == "postgresql":
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
        op.execute(
            """
            CREATE TRIGGER audit_events_immutable
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_audit_events_mutation();
            """
        )

        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'portfolio_audit_archive') THEN
                    CREATE ROLE portfolio_audit_archive NOLOGIN;
                END IF;
                GRANT SELECT, DELETE ON audit_events TO portfolio_audit_archive;
                CREATE OR REPLACE PROCEDURE archive_audit_events_before(IN cutoff TIMESTAMPTZ)
                LANGUAGE plpgsql
                AS $proc$
                BEGIN
                    DELETE FROM audit_events WHERE occurred_at < cutoff;
                END;
                $proc$;
                GRANT EXECUTE ON PROCEDURE archive_audit_events_before(TIMESTAMPTZ) TO portfolio_audit_archive;
            EXCEPTION
                WHEN insufficient_privilege THEN
                    RAISE NOTICE 'Skipping audit archive role setup; requires database superuser';
            END $$;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                DROP PROCEDURE IF EXISTS archive_audit_events_before(TIMESTAMPTZ);
                IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'portfolio_audit_archive') THEN
                    REVOKE EXECUTE ON PROCEDURE archive_audit_events_before(TIMESTAMPTZ) FROM portfolio_audit_archive;
                    REVOKE SELECT, DELETE ON audit_events FROM portfolio_audit_archive;
                    DROP ROLE portfolio_audit_archive;
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    NULL;
            END $$;
            """
        )

        op.execute("DROP TRIGGER IF EXISTS audit_events_immutable ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS reject_audit_events_mutation()")

    op.drop_column("audit_events", "event_hash")
    op.drop_column("audit_events", "previous_event_hash")
    op.drop_table("login_rate_limits")
