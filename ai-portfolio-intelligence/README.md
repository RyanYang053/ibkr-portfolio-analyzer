# Portfolio Analyzer

Local-first, read-only portfolio analytics and decision-support for Interactive Brokers accounts.

> **Product definition:** a local personal application. All portfolio data, broker sessions, tax records, and application state remain on your device. No application login or hosted backend is required.

## Download & install

Portfolio Analyzer ships as a native desktop app for **macOS**, **Windows**, and **Linux**. Grab the
installer for your platform from the
[Releases page](https://github.com/RyanYang053/ibkr-portfolio-analyzer/releases):

- **macOS** — download the `.dmg`, open it, drag **Portfolio Analyzer** to Applications. If the build
  is unsigned, right-click the app → **Open** the first time to get past Gatekeeper.
- **Windows** — run the `Portfolio Analyzer_*-setup.exe` (NSIS) installer. If unsigned, click
  **More info → Run anyway** on the one-time SmartScreen prompt.
- **Linux** — run the `.AppImage`, or install the `.deb`.

Once configured, the app **updates itself** on launch. Maintainers cut a release by tagging
`desktop-v*`; see [docs/RELEASE_AND_SIGNING.md](docs/RELEASE_AND_SIGNING.md) for signing + release
steps. To build locally: `python3 scripts/build-macos-installer.py`.

## Using the app

1. **Launch** — the app starts a local, loopback-only engine and opens the dashboard. No sign-up, no login.
2. **Connect Interactive Brokers (read-only)** — add an IBKR **Flex** token to pull positions,
   transactions, and history. It **never** places orders and **never** collects your IBKR password.
   See [docs/ibkr-readonly-setup.md](docs/ibkr-readonly-setup.md).
3. **Explore** — holdings & P&L, risk (Sharpe/Sortino/Calmar/drawdown/VaR + capture ratios), a
   securities workspace with interactive charts, screener, options, tax lots, journal, trade-plan
   drafts (never submitted), markets/regime, and reports.
4. **Your data stays on your device** — under your OS Application Support folder (see below).

Decision-support only — it surfaces analytics and suggestions for **you** to act on in your own
broker; it does not trade. See [docs/PRODUCT_SCOPE.md](docs/PRODUCT_SCOPE.md).

## Personal developer bring-up

From `ai-portfolio-intelligence`:

```bash
python3 scripts/desktop_local_smoke.py    # loopback API + session gate + export
python3 scripts/desktop_restore_smoke.py  # export manifest hashes + restore roundtrip
python3 scripts/run_personal_desktop.py   # starts API only (no browser UI)
```

The full interactive UI ships inside the Tauri desktop app. The session token is injected by Rust into the webview and is **not** served by any public HTTP route.

| Capability | Status |
| --- | --- |
| No application login | Done |
| Loopback-only API + per-launch session token | Done |
| Token not disclosed over HTTP | Done |
| Local data under OS Application Support | Done |
| Startup backup retention (last 10) + export manifest | Done |
| No Docker / Postgres for personal use | Done |
| No order submission | Done |
| IBKR password collection | Never |

Data directory (macOS):

```text
~/Library/Application Support/PortfolioAnalyzer/
├── portfolio.db     # canonical SQLite database (positions, transactions, decisions, …)
├── state/           # namespaced JSON projections / legacy import staging
├── imports/
├── exports/
├── backups/
└── logs/
```

## Current release status

The certified commit, gate conclusions, and installer hashes for any release are the
release manifest emitted into `ci-evidence/<commit-sha>/` — that manifest, not this
table, is the source of truth (see `scripts/write_release_manifest.py`).

Baseline for the SQLite/goldens/release-gates layer: `39a3a2bde2f37f3f26e5d8d137d2c5db7ce481fc`.
The package matrix + launch smoke must be re-run and re-certified for the current
commit before publishing (the P0 release-hardening changes supersede the earlier
`67ab2c78…` pre-hardening evidence).

| Area | Status |
| --- | --- |
| Local-first architecture | **GO** |
| CI + Desktop validate | Re-certify for current commit |
| Platform installers (DMG/NSIS/AppImage/DEB) | Re-certify for current commit |
| Packaged sidecar smoke | Re-certify for current commit |
| Tauri application launch smoke | Re-certify for current commit |
| Signed / notarized installers | Add GitHub signing secrets, then tag `desktop-v*` |
| Public GitHub Release for other users | **Ready after signing secrets** |

## Architecture

```text
Tauri desktop app
├── Next.js static UI (apps/web/out) in the webview
├── FastAPI sidecar on 127.0.0.1:<random port>
├── X-Local-Session injected as window.__DESKTOP_RUNTIME__ (webview only)
├── SQLite database (portfolio.db) in Application Support — canonical local store,
│     fail-closed on schema-init failure; namespaced JSON is a projection
└── OS Keychain for Flex tokens
```

Deployment modes:

```text
desktop_local   → personal use (no login, SQLite persistence via portfolio.db)
development     → engineering (Docker/Postgres allowed)
```

## Developer notes

### Signed releases for other users

Add these GitHub Actions secrets, then tag `desktop-v0.1.0`:

```text
APPLE_CERTIFICATE
APPLE_CERTIFICATE_PASSWORD
APPLE_SIGNING_IDENTITY
APPLE_ID
APPLE_PASSWORD
APPLE_TEAM_ID
KEYCHAIN_PASSWORD
WINDOWS_CERTIFICATE
WINDOWS_CERTIFICATE_PASSWORD
```

Without those secrets, main-branch CI still builds unsigned installers and runs launch smoke. Tagged releases refuse to publish unsigned macOS/Windows artifacts.

Full **macOS** installer helper (requires Rust toolchain + PyInstaller):

```bash
# macOS one-shot: sidecar + static web + .app/.dmg
python3 scripts/build-macos-installer.py

# Cross-platform packaging is handled by GitHub Actions (Desktop workflow).
# Or step by step:
python3 scripts/build-backend-sidecar.py
python3 scripts/prepare-tauri-binaries.py
python3 scripts/smoke-packaged-sidecar.py
cd apps/desktop && npm install && npx tauri build
```

Artifacts land under `apps/desktop/src-tauri/target/release/bundle/` (and target-triple paths in CI).

Note: Tauri’s built-in DMG step can fail when the repo path contains spaces; `build-macos-installer.py` can create a DMG with `hdiutil` as a fallback.

## Product claims

Supported: broker-reconciled personal analytics, tax estimates, proxy attribution, decision-support signals, broker-reported margin.

Not claimed: official books and records, CRA filing, registered advice, official Brinson, broker-equivalent margin, automated trading.

See `docs/PRODUCT_SCOPE.md`.
