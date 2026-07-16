#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
API_DIR="${ROOT_DIR}/apps/api"
COOKIE_JAR="$(mktemp)"

export ENVIRONMENT="${ENVIRONMENT:-production}"
export PERSISTENCE_BACKEND="${PERSISTENCE_BACKEND:-postgres}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://portfolio:portfolio@127.0.0.1:5432/portfolio}"
export JWT_SECRET="${JWT_SECRET:-production-e2e-secret-with-length}"
export BOOTSTRAP_TOKEN="${BOOTSTRAP_TOKEN:-production-e2e-bootstrap}"
export BROKER_MODE="${BROKER_MODE:-mock_ibkr_readonly}"
export DISABLE_AUTH_ENFORCEMENT="${DISABLE_AUTH_ENFORCEMENT:-false}"
export E2E_EMAIL="${E2E_EMAIL:-prod-e2e@example.com}"
export E2E_PASSWORD="${E2E_PASSWORD:-prod-e2e-password-123}"
export API_BASE="${API_BASE:-http://127.0.0.1:8000}"

cleanup() {
  rm -f "${COOKIE_JAR}" || true
}
trap cleanup EXIT

cd "${API_DIR}"
alembic upgrade head

bootstrap_response="$(curl -sS -w '\n%{http_code}' -X POST "${API_BASE}/auth/bootstrap" \
  -H 'Content-Type: application/json' \
  -d "{\"bootstrap_token\":\"${BOOTSTRAP_TOKEN}\",\"email\":\"${E2E_EMAIL}\",\"password\":\"${E2E_PASSWORD}\",\"name\":\"Production E2E\"}" || true)"
bootstrap_body="$(printf '%s' "${bootstrap_response}" | sed '$d')"
bootstrap_code="$(printf '%s' "${bootstrap_response}" | tail -n1)"
if [[ "${bootstrap_code}" != "200" ]]; then
  echo "Bootstrap failed with HTTP ${bootstrap_code}: ${bootstrap_body}" >&2
  exit 1
fi
printf '%s' "${bootstrap_body}" | grep -q '"access_token"'

TOKEN="$(curl -fsS -X POST "${API_BASE}/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${E2E_EMAIL}\",\"password\":\"${E2E_PASSWORD}\"}" | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"

curl -fsS "${API_BASE}/auth/me" -H "Authorization: Bearer ${TOKEN}" | grep -q '"email"'
curl -fsS "${API_BASE}/health/ready" | grep -q '"status"'
curl -fsS "${API_BASE}/portfolio/summary?account_id=MOCK-001" -H "Authorization: Bearer ${TOKEN}" | grep -q '"net_liquidation"'

UNAUTHORIZED_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "${API_BASE}/portfolio/summary?account_id=U1234567" -H "Authorization: Bearer ${TOKEN}")"
if [[ "${UNAUTHORIZED_STATUS}" != "403" ]]; then
  echo "Expected account isolation denial with 403, got ${UNAUTHORIZED_STATUS}"
  exit 1
fi

curl -fsS -X POST "${API_BASE}/auth/logout" -H "Authorization: Bearer ${TOKEN}" | grep -q '"status"'
REVOKED_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "${API_BASE}/auth/me" -H "Authorization: Bearer ${TOKEN}")"
if [[ "${REVOKED_STATUS}" != "401" ]]; then
  echo "Expected revoked token to return 401, got ${REVOKED_STATUS}"
  exit 1
fi

TOKEN="$(curl -fsS -X POST "${API_BASE}/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${E2E_EMAIL}\",\"password\":\"${E2E_PASSWORD}\"}" | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"

curl -fsS "${API_BASE}/portfolio/pnl-history?account_id=MOCK-001" -H "Authorization: Bearer ${TOKEN}" | grep -q '"net_liquidation"'
curl -fsS "${API_BASE}/portfolio/attribution?account_id=MOCK-001" -H "Authorization: Bearer ${TOKEN}" | grep -q '"methodology"'

AUDIT_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "${API_BASE}/admin/audit-logs" -H "Authorization: Bearer ${TOKEN}")"
if [[ "${AUDIT_STATUS}" != "200" && "${AUDIT_STATUS}" != "403" ]]; then
  echo "Unexpected audit endpoint status ${AUDIT_STATUS}"
  exit 1
fi

echo "Production E2E checks passed"
