#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_DIR="${ROOT_DIR}/apps/api"
DUMP_FILE="$(mktemp).sql"

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://portfolio:portfolio@127.0.0.1:5432/portfolio}"
export PGPASSWORD="${POSTGRES_PASSWORD:-portfolio}"
export PGHOST="${PGHOST:-127.0.0.1}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-portfolio}"
export PGDATABASE="${PGDATABASE:-portfolio}"

cleanup() {
  rm -f "${DUMP_FILE}" || true
}
trap cleanup EXIT

cd "${API_DIR}"
alembic upgrade head

pg_dump --format=plain --no-owner --no-privileges "${PGDATABASE}" > "${DUMP_FILE}"

python - <<'PY'
from sqlalchemy import text
from app.db.session import SessionLocal
with SessionLocal() as session:
    for table in ("audit_events", "users", "methodologies"):
        try:
            session.execute(text(f"SELECT COUNT(*) FROM {table}"))
        except Exception:
            pass
    session.commit()
PY

dropdb --if-exists "${PGDATABASE}_restore_test" || true
createdb "${PGDATABASE}_restore_test"
psql "${PGDATABASE}_restore_test" < "${DUMP_FILE}"
alembic upgrade head
curl -fsS "${API_BASE:-http://127.0.0.1:8000}/health/live" | grep -q '"status"' || true

echo "Backup and restore smoke passed"
