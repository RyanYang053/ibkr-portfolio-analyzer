# AI Portfolio Intelligence and Research System

Read-only portfolio analytics and research system for an Interactive Brokers-style account. The MVP runs fully on mock IBKR data and does not execute trades.

## Product Boundary

This platform connects read-only to broker-style data, analyzes portfolio allocation and risk, scores stocks and ETFs, and produces decision-support suggestions and reports.

It does not place orders, modify orders, cancel orders, execute trades, automate rebalancing, or provide broker execution controls.

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

Docker Compose:

```bash
cd infra
docker compose up --build
```

The web app runs at `http://localhost:3000`; the API runs at `http://localhost:8000`.

## Implemented MVP

- FastAPI backend with read-only broker routes
- Live IBKR read-only placeholder by default, with mock IBKR available only through explicit demo mode
- Portfolio summary, positions, allocation, performance, and risk endpoints
- Stock detail, fundamentals, valuation, technicals, score, and analysis endpoints
- Decision-support recommendation engine
- Gemini-backed AI research layer with deterministic fallback when no key is configured
- Structured daily report generator and manual per-stock AI refresh endpoint
- Watchlist, alerts, settings, and audit endpoints
- Next.js dashboard and core pages
- No-trading guardrail tests

## Gemini AI Setup

The app keeps the Gemini key on the backend only. Do not put it in frontend code.

```bash
export GEMINI_API_KEY="your_google_ai_studio_key"
export GEMINI_MODEL="gemini-2.5-flash"
cd apps/api
../../.venv/bin/uvicorn app.main:app --reload
```

Manual stock analysis endpoint after a live read-only portfolio is connected, or in explicit demo mode:

```bash
curl -X POST http://localhost:8000/ai/analyze-stock/MSFT
```

Portfolio memo endpoint:

```bash
curl -X POST http://localhost:8000/ai/analyze-portfolio
```

If `GEMINI_API_KEY` is missing or Gemini returns an error, the API returns a deterministic fallback report with the same no-trading disclaimer.

## Demo Mode

Mock portfolio data is disabled by default. To run the old local demo data intentionally:

```bash
export BROKER_MODE=mock_ibkr_readonly
cd apps/api
../../.venv/bin/uvicorn app.main:app --reload
```

For normal use, keep:

```bash
BROKER_MODE=ibkr_readonly
```

Until the live IBKR read-only connector is implemented, the app will show a disconnected state instead of fake holdings.

## Verification

```bash
npm run api:test
cd apps/web && npm run build
```

## Required Disclaimer

This is portfolio analysis and decision support only. The system does not execute trades. The user must independently review any suggestion before making investment decisions outside the platform.
