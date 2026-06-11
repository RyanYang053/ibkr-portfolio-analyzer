# AI Research Workflow

The AI layer uses Gemini through the backend only.

## Division of Responsibility

The system is split into four layers:

1. Data layer: imports read-only portfolio, price, fundamental, technical, valuation, and catalyst data.
2. Calculation engine: computes P&L, weights, exposure, Herfindahl concentration, SMA, EMA, RSI, MACD, ATR, beta, relative strength, drawdown, margins, FCF, and valuation ratios.
3. Rule engine: applies if/then rules for risk alerts, technical red flags, valuation red flags, data freshness, confidence caps, thesis status, and decision-support categories.
4. AI/Gemini layer: explains and synthesizes the structured outputs. It does not calculate raw indicators, access IBKR, access credentials, submit orders, rebalance, or trade.

## Inputs

- Position data
- Stock score and sub-scores
- Decision-support recommendation
- Portfolio risk context
- Data freshness and missing-data flags
- Rule-engine action, red flags, and confidence limits
- Evidence registry with stable `evidence_ids`
- Stored thesis and thesis status

## Prompt Framework

The stock prompt requires Gemini to analyze:

- Business quality and portfolio role
- Growth, profitability, cash flow, and balance sheet quality
- Valuation risk
- Technical trend and support/resistance context
- Catalyst and missing-data risks
- Portfolio fit and concentration
- Thesis invalidation triggers

The prompt requires strict JSON and forbids broker-order language.

Every stock AI output must include:

- `schema_version`
- `action`
- `rule_engine_action`
- `confidence`
- `confidence_limits`
- `data_quality`
- `thesis.status`
- `thesis_invalidation_triggers`
- `claims[]` with `evidence_ids`
- `evidence[]`
- `strengths`, `weaknesses`, and `risks`
- add, hold, trim review, and exit review explanations
- `human_review_required`
- no-trading disclaimer

Confidence limits are deterministic:

- stale portfolio data: max confidence `Medium`
- missing price data: no add zone
- missing fundamentals: max confidence `Medium`
- missing technicals: `technical_score = null`
- missing news/catalyst data: `catalyst_score = null`
- more than two major missing categories: action `Data Insufficient`, confidence `Low`

## Refresh Modes

Implemented now:

- Manual per-stock refresh: `POST /ai/analyze-stock/{symbol}`
- Manual portfolio memo refresh: `POST /ai/analyze-portfolio`
- Schedule configuration endpoint: `/ai/schedule`

Future worker phase:

- Use Redis plus Celery or RQ to execute scheduled refreshes
- Store generated AI reports in `ai_reports`
- Add per-symbol refresh cadence and stale-data warnings

## API Key

Set the key on the backend process:

```bash
export GEMINI_API_KEY="..."
export GEMINI_MODEL="gemini-2.5-flash"
```

The key must not be sent to the browser or stored in the database.

Sources used for implementation:

- [Gemini API key setup](https://ai.google.dev/gemini-api/docs/api-key)
- [Gemini generateContent REST API](https://ai.google.dev/gemini-api/docs)
