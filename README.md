# IBKR Portfolio Analyzer

**Understand your IBKR portfolio without giving an app permission to trade.**

Local-first desktop analytics for holdings, performance, risk and research. Built with Tauri, Next.js, FastAPI and SQLite.

[Quick start](#quick-start) · [Capabilities](#what-you-can-explore) · [Engineering reference](ENGINEERING.md) · [Contribute](CONTRIBUTING.md)

[![CI](https://github.com/RyanYang053/ibkr-portfolio-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/RyanYang053/ibkr-portfolio-analyzer/actions/workflows/ci.yml)
![Research only](https://img.shields.io/badge/live%20orders-disabled-555)

## Quick start

```bash
git clone https://github.com/RyanYang053/ibkr-portfolio-analyzer.git
cd ibkr-portfolio-analyzer
python -m venv .venv
```

Activate with `source .venv/bin/activate` on macOS/Linux or `.venv\Scripts\Activate.ps1` in PowerShell.

```bash
python -m pip install -r ai-portfolio-intelligence/apps/api/requirements.txt
python scripts/demo.py --output portfolio-demo.html
```

Open the generated HTML file locally. A small HTML preview generated from the actual mock broker adapter, showing fictional accounts and holdings. It is not the full desktop UI and uses no brokerage credentials.

## What you can explore

| Area | Capability |
| --- | --- |
| Accounts | USD/CAD holdings, multi-account views, Flex ingestion |
| Performance | Historical valuations, P&L, benchmark and return analysis |
| Risk | Drawdown, volatility, concentration and risk metrics |
| Research | Securities workspace, charts, screening, optional AI |
| Workflow | Tax estimates, journal and draft trade plans; no submitted orders |

```mermaid
flowchart LR
 B[IBKR read-only data] --> A[Local FastAPI engine]
 A --> S[SQLite]
 A --> U[Tauri desktop / Next.js]
 A -. optional market data or AI .-> X[External providers]
```

## Desktop setup

- [Desktop architecture and local smoke tests](ai-portfolio-intelligence/README.md)
- [IBKR read-only connection](ai-portfolio-intelligence/docs/ibkr-readonly-setup.md)
- [Release and signing](ai-portfolio-intelligence/docs/RELEASE_AND_SIGNING.md)
- [Product scope](ai-portfolio-intelligence/docs/PRODUCT_SCOPE.md)

**Release status:** no published desktop installers at the time of this update. Source checkout only; check CI and release certification before deployment. Do not bypass OS security to install unverified builds.

The local desktop engine uses a loopback-only API. Optional AI and data providers can make network requests; review their data flows and policies before enabling them. Never share real account statements or tokens. No order execution.

## Verification

```bash
cd ai-portfolio-intelligence/apps/api && python -m pytest tests -q
```

See [engineering reference](ENGINEERING.md) for the preserved previous technical documentation, [launch gates](docs/LAUNCH.md) and [license status](LICENSING.md).

## Related projects

- [Atlas Investment OS](https://github.com/RyanYang053/50agent-invest-system) — Local-first research, valuation, quantitative analysis, risk and governance.
- [IBKR Agent Harness](https://github.com/RyanYang053/IBKR-Agent-harness) — Local-first Python and MCP toolkit for Interactive Brokers portfolio research, combining deterministic calculations, investment policy checks, valuation and persistent workflows with human approval..

These are separate projects, not a claimed integrated deployment.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). If the project is useful, consider starring it or reporting a reproducible improvement.

Research and educational use only; not financial or tax advice.
