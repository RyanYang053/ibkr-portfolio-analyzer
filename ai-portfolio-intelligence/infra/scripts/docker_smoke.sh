#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/infra/docker-compose.yml"

export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ci-smoke-password}"
export JWT_SECRET="${JWT_SECRET:-ci-smoke-secret}"
export ENVIRONMENT="${ENVIRONMENT:-development}"
export BROKER_MODE="${BROKER_MODE:-mock_ibkr_readonly}"
export DISABLE_AUTH_ENFORCEMENT="${DISABLE_AUTH_ENFORCEMENT:-true}"

cleanup() {
  docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose -f "${COMPOSE_FILE}" up -d --build postgres api

for attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
    break
  fi
  sleep 2
done

curl -fsS http://127.0.0.1:8000/health | grep -q '"status"'
curl -fsS http://127.0.0.1:8000/openapi.json | grep -q '"openapi"'

echo "Docker production smoke passed"
