# Open-Source Incorporation Plan

**Date:** 2026-07-21 · **Method:** surveyed ~30 public repos across 5 clusters (data layer, perf/risk
analytics, optimization/indicators, PF-products/IBKR/charts, quant-platform sweep). Licenses, stars,
and maintenance verified live against the GitHub API / PyPI on 2026-07-21, then filtered against three
hard constraints and mapped to existing services.

**Hard constraints (a borrow must pass all three):**
1. **No-trade** — nothing that places or simulates orders in the hot path. Optimizer/allocation outputs
   are reviewable *suggestions* only. See [no-trading-policy.md](no-trading-policy.md).
2. **Offline / PyInstaller** — no network import in the hot path; prefer pure-python or vendorable code;
   native-heavy deps run acquisition-side (user-initiated refresh), not in the shipped sidecar.
3. **License** — MIT/BSD/Apache = code usable. AGPL/GPL/EPL/Commons-Clause = **concepts only**, never
   copy source (a distributed desktop app would be infected).

---

## 0. Already covered — do NOT duplicate

Verified in-tree. These kill several otherwise-popular recommendations:

| Capability | Where it already lives | Repos this rules out |
|---|---|---|
| Mean-variance + **Black-Litterman** optimizer, tax-aware lots, rebalance proposals | `services/portfolio_construction/advanced_optimizer.py`, `optimizer.py` | PyPortfolioOpt/Riskfolio/skfolio **as a core optimizer** |
| **Options** Black-Scholes + Greeks (American-aware) | `services/options/` via **QuantLib** | py_vollib, QuantLib re-adoption |
| **Exchange calendars** (holidays/early-closes) | `services/market_data/exchange_calendar.py` via `exchange_calendars` | pandas_market_calendars |
| **Time-weighted + money-weighted (XIRR)** returns, geometric linking | `portfolio/return_engine.py`, `performance_returns.py`, `attribution/linking.py` | Portfolio Performance return math |
| Core risk metrics: vol, drawdown, alpha/beta, Sharpe/Sortino/Calmar, VaR | `services/risk/`, `services/analytics/` | most of empyrical's overlap |
| Tax lots + booking, EDGAR fundamentals lineage | `services/tax/`, `services/fundamentals/` | beancount as a dependency |
| Already ship: `cvxpy`, `scipy`, `numpy`, `statsmodels`, `QuantLib` | `requirements.txt` | — (deps needing these are "already paid for") |

---

## 1. Adopt — permissive license, genuinely additive

| Repo | License | What we take | Maps to | Effort | Packaging note |
|---|---|---|---|---|---|
| **ib-api-reloaded/ib_async** | BSD-2 | Maintained successor to your **archived** `ib_insync`; read paths (positions/PnL/historical/contractDetails) **+ Flex Web Service** (tax-lot / cash-transaction / dividend / realized-P&L detail the socket API can't give) | `services/broker/`, `portfolio`, `tax`, `reports` | M | asyncio loop in sidecar; wrap in **read-only allowlist adapter** |
| **stefan-jansen/empyrical-reloaded** | Apache-2.0 | The *delta* metrics you lack: **Omega, tail ratio, CVaR, up/down capture, batting average, information ratio, rolling Sharpe/Sortino/beta** | `services/risk/`, `analytics/`, `attribution/` | S | numpy/pandas/scipy only — zero new packaging risk |
| **tradingview/lightweight-charts** | Apache-2.0 | Real candlestick/OHLC/area + multi-series overlay + markers; ~35 kB, pure-canvas, offline. (UI is **recharts-only** today.) | `apps/web` securities workspace, portfolio-vs-benchmark, journal-event markers | S | preserve TradingView attribution NOTICE |
| **JerBouma/FinanceDatabase** (data) | MIT | **Vendor the ~20 MB compressed symbol CSVs at build time** → seed instrument master + aliases with **ISIN/CUSIP/FIGI** + sector/industry/country taxonomy | `instruments/`, `screening/` | S | build-time only; **do not** use the pip pkg (it fetches from GitHub at runtime) |
| **dgunning/edgartools** | MIT | Best-in-class **XBRL→standardized statements** + Company Facts; filing-date = point-in-time for free | `fundamentals/`, `data_quality/` | M | pulls `pyarrow` (~100 MB) → run **acquisition-side**, not in-sidecar |
| **matplotlib/mplfinance** | BSD | Static candlestick+volume+MA PNGs embedded in PDF/report exports | `services/reports/` | S | matplotlib-backed; low risk |
| **ranaroussi/yfinance** | Apache-2.0 | *Optional, guarded* online price/corporate-action refresh **behind the provider interface** — a free fallback when IBKR isn't connected / for unowned securities | `services/market_data/` | M | `curl_cffi` needs PyInstaller hooks; Yahoo ToS is fragile → never canonical/offline source |

---

## 2. Vendor-subset — copy specific formulas/algorithms (permissive)

Small, well-specified surfaces; cheaper and lighter than adopting the whole dependency.

- **skfolio (BSD) / Riskfolio-Lib (BSD) risk measures** → `risk/`: **CDaR, EVaR, EDaR, Ulcer index, Gini
  mean difference** — downside measures absent from empyrical; ~10–30 lines of numpy each. **Do not** add
  the packages (cvxpy/clarabel/vectorbt/pybind11 = sidecar bloat you don't need).
- **stefan-jansen/alphalens-reloaded (Apache-2.0)** → `scoring/` + `decision_calibration`: **Information
  Coefficient + quantile forward-return spread + turnover**. This is the *no-trade "backtest"* — it
  measures whether your composite score / regime label precedes favorable forward returns, with **no
  order simulation**. Vendor the IC/quantile math (scipy path); statsmodels is already in-tree.
- **JerBouma/FinanceToolkit (MIT)** → `valuation/`, `scoring/`: distinctive scored models — **Altman Z,
  Beneish M, Graham Number, DuPont, WACC** — fed from your EDGAR-sourced statements.
- **mortada/fredapi (Apache-2.0)** → macro context + PIT reference: the **ALFRED vintage client**
  (`get_series_as_of_date`, `get_series_first_release`, ~200 lines) — copyable "what-was-known-when"
  discipline; plus FRED macro/FX series as an optional refresh.
- **PyPortfolioOpt `greedy_portfolio` DiscreteAllocation (MIT)** → `trade_planning/`: target weights →
  **whole-share deltas**, pure-python (no cvxpy). Surface as a reviewable suggestion only.
- **ranaroussi/quantstats (Apache-2.0)** → `reports/`: the **HTML tearsheet + monthly-returns heatmap +
  drawdown-periods table**. Vendor `stats.py` + report module; **strip the yfinance benchmark path**.

---

## 3. Concepts-only — copyleft/source-available, clean-room reimplement (no source copied)

- **ghostfolio/ghostfolio (AGPL-3.0)** — the best "Decision OS" concept fit:
  - **X-Ray rules engine**: declarative, *user-configurable-threshold* portfolio-risk rules
    (`Rule = {key, thresholdConfig, evaluate(holdings) → {value,status,message}}`) — account/currency/
    regional **cluster-risk**, emergency-fund adequacy, fee ratio → `analytics/` + `notifications/`.
  - **FIRE / sustainable-withdrawal calculator** → `planning/`.
  - Allocation breakdowns by sector/geo/currency/account; dividend-income timeline → `analytics/`.
- **OpenBB (AGPL-3.0)** — reimplement the **provider-abstraction pattern**: a `Fetcher`
  (transform_query → extract_data → transform_data) + standardized pydantic models + a provider registry,
  so IBKR/Flex, edgartools, FRED, and yfinance sit behind one swappable, **read-only-guarded** interface.
  This is the spine that §1 (yfinance/edgartools) and §2 (fredapi) plug into.
- **microsoft/qlib (MIT, but torch-laden — don't adopt the package)** — borrow the **Alpha158/360
  expression DSL** (declarative factor formulas `Ref/Mean/Std/Corr`, ~200 lines over pandas) for the
  screener/scoring, and its point-in-time data discipline.
- **beancount (GPL-2.0)** — *only if* the tax service lacks a booking method: reference the lot-booking
  algorithms (FIFO/LIFO/avg-cost/specific-lot) — reimplement, never import.

---

## 4. Explicitly SKIP (with reason)

| Repo | Reason |
|---|---|
| freqtrade | GPL-3.0 crypto **execution bot** — wrong domain + copyleft |
| nautilus_trader | LGPL execution/OMS engine, heavy Rust build — literal opposite of read-only |
| backtrader | GPL-3.0 **and ~2 yrs unmaintained** + execution-oriented |
| FinRL | Trains RL agents to **place trades**; heavy torch/gym; clashes with deterministic/no-trade |
| vectorbt / vectorbtpro | Commons-Clause "no Sell" / proprietary paid — non-distributable |
| kernc/backtesting.py | AGPL-3.0 blocks proprietary distribution (great API → concepts only) |
| maybe-finance/maybe | AGPL **and archived (2025-07)** + Rails; Ghostfolio covers the space, alive |
| erdewit/ib_insync | **Archived 2024** — replaced by ib_async |
| TA-Lib | Native C library → PyInstaller/offline pain; keep pure-python |
| **pandas-ta** | ⚠️ **Supply-chain risk** — GitHub repo removed, PyPI maintainer changed with force-removed history. Do not pin. If broader indicators are ever needed: MIT `bukosabino/ta` (stable, 43, zero-native) or `pandas-ta-classic` (pin + vendor). Current hand-rolled `technicals/indicators.py` is fine and deliberate. |

---

## 5. Cross-cutting guardrails

- **License hygiene:** never lift source from Ghostfolio/Maybe/OpenBB (AGPL), backtesting.py/vectorbt
  (AGPL/Commons-Clause), Portfolio Performance (EPL), beancount (GPL). Keep AGPL/GPL packages out of the
  dependency tree entirely. Preserve required attribution NOTICEs (lightweight-charts, empyrical, ffn…).
- **No-trade contract:** `ib_async` *can* place orders — wrap it in a read-only allowlist adapter exposing
  only read methods, and add a contract test asserting no order API is reachable (mirror the existing
  no-order-submission test). Discrete-allocation / optimizer outputs stay reviewable suggestions.
- **Offline / packaging:** yfinance, edgartools, fredapi are **user-initiated refresh only**, never hot-path.
  Prefer vendoring formulas (§2) over pulling native-heavy optimizer packages. `pyarrow` (edgartools) is
  acceptable acquisition-side, not in the shipped sidecar.

---

## 6. Suggested sequencing

- **Phase 0 — quick wins** (independent, permissive, zero contract risk):
  `empyrical-reloaded` metric gaps · `FinanceDatabase` instrument seed · `lightweight-charts` UI charts.
- **Phase 1 — correctness & coverage:** `ib_async` migration + Flex read paths (read-only adapter) ·
  `edgartools` acquisition upgrade · provider-abstraction spine (OpenBB pattern).
- **Phase 2 — decision depth:** alphalens IC/quantile signal-validation for `scoring`/regime ·
  skfolio/Riskfolio downside-risk formulas · Ghostfolio X-Ray rules + allocation/dividend/FIRE ·
  FinanceToolkit scored models.
- **Phase 3 — polish:** quantstats/mplfinance report tearsheets · FRED macro context · qlib
  expression-DSL for the screener.

---

## 7. Implementation status (2026-07-21)

Full API suite **625 pass / 9 skip / 0 fail**; web typecheck + build + lint green. All new
backend modules are ruff + mypy clean.

**Shipped (9 capabilities, ~30 new tests):**
1. `services/risk/extended_metrics.py` — Omega, tail ratio, gain-to-pain, pain index, CDaR,
   up/down/up-down capture, batting average → wired into `AdvancedRiskMetrics` (+10 fields).
2. `scoring/calibration.py` — top-minus-bottom quantile spread (IC/Spearman/buckets already existed).
3. `services/valuation/forensic_models.py` — Altman-Z, Beneish-M, Graham, DuPont, WACC (Graham +
   net-margin wired via `scores_from_snapshot`; the balance-sheet models await richer statement fields).
4. `portfolio_construction/discrete_allocation.py` — greedy whole-share allocation (no cvxpy).
5. `analytics/portfolio_xray.py` — currency/top-5/holdings/HHI declarative threshold rules.
6. `ib_insync` → `ib_async==2.1.0` + read-only order-method contract test.
7. `apps/web/components/LightweightPriceChart.tsx` (lightweight-charts 5.2.0) replacing the
   hand-rolled SVG in `HoldingInteractiveChart`.
8. Vendored FinanceDatabase slice (`app/data/reference/financedatabase/`, 9,941 equities +
   4,445 USD ETFs) + `services/reference_seed.py` (ISIN/CUSIP/FIGI aliases).
11. `build_performance_tearsheet` in `reports/builders.py` (reuses `render_report_html`, no new dep).

**Declined with cause:**
- **edgartools (9)** — the existing `fundamentals/providers/edgar_provider.py` + `concept_resolver.py`
  + `metric_lineage.py` already do standardized us-gaap XBRL extraction with concept resolution and
  point-in-time filing dates. Installing edgartools also bumped numpy/pandas and broke the venv
  (pandas 3.0.3 binary blocked by macOS policy). Redundant **and** destabilising → not adopted.
- **provider-abstraction (10)** — premature abstraction (YAGNI): a spine for providers we are not
  adding, over a per-domain provider pattern that already exists.
- **mplfinance charts** — skipped to avoid a matplotlib dependency; the HTML tearsheet covers the need.

**Repo hygiene fixed (with approval):** removed 76 untracked ` 2.` copy-artifact files (10 in
`migrations/versions/` were breaking `alembic upgrade head` and desktop boot) and 15
`node_modules/@types/* 3` artifacts that were breaking `next build`.
