#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/infra/docker-compose.yml"

export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ci-smoke-password}"
export JWT_SECRET="${JWT_SECRET:-ci-smoke-secret-with-length}"
export BOOTSTRAP_TOKEN="${BOOTSTRAP_TOKEN:-ci-bootstrap-token}"
export ENVIRONMENT="${ENVIRONMENT:-development}"
export PERSISTENCE_BACKEND="${PERSISTENCE_BACKEND:-postgres}"
export BROKER_MODE="${BROKER_MODE:-mock_ibkr_readonly}"
export DISABLE_AUTH_ENFORCEMENT="${DISABLE_AUTH_ENFORCEMENT:-false}"
export DISABLE_AUTH_MIDDLEWARE="${DISABLE_AUTH_MIDDLEWARE:-false}"
export SEC_EDGAR_USER_AGENT="${SEC_EDGAR_USER_AGENT:-PortfolioIntelligence/1.0 ops@example.com}"

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
WEB_BASE="${WEB_BASE:-http://127.0.0.1:3000}"
SMOKE_EMAIL="${SMOKE_EMAIL:-smoke@example.com}"
SMOKE_PASSWORD="${SMOKE_PASSWORD:-smoke-password-123}"

cleanup() {
  docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose -f "${COMPOSE_FILE}" up -d --build postgres api scheduler web

for attempt in $(seq 1 60); do
  if curl -fsS "${API_BASE}/health" >/dev/null; then
    break
  fi
  sleep 2
done

curl -fsS "${API_BASE}/health" | grep -q '"status"'
curl -fsS "${API_BASE}/openapi.json" | grep -q '"openapi"'

docker compose -f "${COMPOSE_FILE}" exec -T api alembic upgrade head

curl -fsS -X POST "${API_BASE}/auth/bootstrap" \
  -H 'Content-Type: application/json' \
  -d "{\"bootstrap_token\":\"${BOOTSTRAP_TOKEN}\",\"email\":\"${SMOKE_EMAIL}\",\"password\":\"${SMOKE_PASSWORD}\",\"name\":\"Smoke User\"}" \
  | grep -q '"access_token"'

LOGIN_PAYLOAD="$(curl -fsS -X POST "${WEB_BASE}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${SMOKE_EMAIL}\",\"password\":\"${SMOKE_PASSWORD}\"}")"
echo "${LOGIN_PAYLOAD}" | grep -q '"email"'

TOKEN="$(curl -fsS -X POST "${API_BASE}/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${SMOKE_EMAIL}\",\"password\":\"${SMOKE_PASSWORD}\"}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"

curl -fsS "${API_BASE}/auth/me" -H "Authorization: Bearer ${TOKEN}" | grep -q '"email"'
curl -fsS "${API_BASE}/portfolio/summary?account_id=MOCK-001" -H "Authorization: Bearer ${TOKEN}" | grep -q '"net_liquidation"'
curl -fsS "${API_BASE}/portfolio/positions?account_id=MOCK-001" -H "Authorization: Bearer ${TOKEN}" | grep -q '\['
curl -fsS "${API_BASE}/portfolio/risk?account_id=MOCK-001" -H "Authorization: Bearer ${TOKEN}" | grep -q '"risk_score"'
curl -fsS "${API_BASE}/reports?account_id=MOCK-001" -H "Authorization: Bearer ${TOKEN}" | grep -q '\['

UNAUTHORIZED_STATUS="$(curl -s -o /dev/null -w '%{http_code}' "${API_BASE}/portfolio/summary?account_id=U1234567" -H "Authorization: Bearer ${TOKEN}")"
if [[ "${UNAUTHORIZED_STATUS}" != "403" ]]; then
  echo "Expected unauthorized account to return 403, got ${UNAUTHORIZED_STATUS}"
  exit 1
fi

curl -fsS "${WEB_BASE}/login" | grep -q 'Sign in'

docker compose -f "${COMPOSE_FILE}" ps --format json | grep -q '"State":"running"'

echo "Docker production-like smoke passed"
