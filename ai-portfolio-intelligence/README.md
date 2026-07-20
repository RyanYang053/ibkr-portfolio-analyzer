# Portfolio Analyzer

Local-first, read-only portfolio analytics and decision-support for Interactive Brokers accounts.

> **Product definition:** a local personal application. All portfolio data, broker sessions, tax records, and application state remain on your device. No application login or hosted backend is required.

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
| Startup backup retention + export manifest | Done |
| No Docker / Postgres for personal use | Done |
| No order submission | Done |
| IBKR password collection | Never |

Data directory (macOS):

```text
~/Library/Application Support/PortfolioAnalyzer/
├── state/
├── imports/
├── exports/
├── backups/
└── logs/
```

## Current release status

| Area | Status |
| --- | --- |
| Local-first architecture | GO in principle |
| Personal local API smoke | GO after local verification |
| Full Next.js panels in Tauri | Built; needs exact-SHA CI |
| Platform installers (DMG/NSIS/AppImage) | Built in Desktop CI with launch smoke |
| Signed / notarized installers | Requires GitHub secrets (see below) |
| Easy install for other users | Tag `desktop-v*` after secrets are set |
| Docker / Postgres | CI and developer use only |

## Architecture

```text
Tauri desktop app
├── Next.js static UI (apps/web/out) in the webview
├── FastAPI sidecar on 127.0.0.1:<random port>
├── X-Local-Session injected as window.__DESKTOP_RUNTIME__ (webview only)
├── JSON state in Application Support (fail-closed on corruption)
└── OS Keychain for Flex tokens
```

Deployment modes:

```text
desktop_local   → personal use (no login, JSON state only)
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

Docker Compose remains for CI:

```bash
cd infra && docker compose up --build
```

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
