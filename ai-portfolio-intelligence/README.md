# AI Portfolio Intelligence and Research System

Read-only portfolio analytics and research for Interactive Brokers-style accounts. The system does not execute trades.

## Quick Start (Docker)

```bash
cp .env.example .env
# fill POSTGRES_PASSWORD, JWT_SECRET, BOOTSTRAP_TOKEN
cd infra
docker compose up --build
curl -X POST http://localhost:8000/auth/bootstrap \
  -H 'Content-Type: application/json' \
  -d '{"bootstrap_token":"<BOOTSTRAP_TOKEN>","email":"owner@example.com","password":"change-me-now","name":"Owner"}'
open http://localhost:3000/login
```

Supported runtimes: Python 3.12, Node 22.

## Required Environment

| Variable | Purpose |
| --- | --- |
| `POSTGRES_PASSWORD` | Postgres credential for compose |
| `JWT_SECRET` | Session signing secret |
| `BOOTSTRAP_TOKEN` | One-time owner bootstrap |
| `PERSISTENCE_BACKEND` | `postgres` for production-safe persistence |
| `BROKER_MODE` | `mock_ibkr_readonly` (demo) or `ibkr_readonly` (live read-only) |
| `IBKR_HOST` | Use `host.docker.internal` when Gateway runs on the host |
| `GEMINI_API_KEY` | Optional AI provider key (environment only in production) |

Migrations run automatically on API container start via Alembic `upgrade head`.

## Operating Modes

- **Demo**: `BROKER_MODE=mock_ibkr_readonly` with explicit mock fixtures.
- **Production-safe**: Postgres persistence, auth enforcement enabled, immutable audit events.
- **Withheld until validated**: scenario fair values, institutional attribution, tax reporting, live advanced optimization.

## IBKR Host Networking

When TWS or IB Gateway runs on the host machine, set:

```bash
IBKR_HOST=host.docker.internal
IBKR_PORT=4001
```

Docker Compose maps `host.docker.internal` through `extra_hosts`.

## Local Development

Backend:

```bash
python3 -m venv .venv
.venv/bin/pip install -r apps/api/requirements.txt
cd apps/api
../../.venv/bin/uvicorn app.main:app --reload
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

## Verification

```bash
cd apps/api && python -m pytest tests -q
cd apps/web && npm run build
bash infra/scripts/docker_smoke.sh
```

## Required Disclaimer

This is portfolio analysis and decision support only. The system does not execute trades. Review every suggestion independently before acting outside the platform.
