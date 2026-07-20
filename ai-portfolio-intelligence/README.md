# Portfolio Analyzer

Local-first, read-only portfolio analytics and decision-support for Interactive Brokers accounts.

> **Product definition:** a local personal application. All portfolio data, broker sessions, tax records, and application state remain on your device. No application login or hosted backend is required.

## Personal FULL GO (use this)

On your Mac, from `ai-portfolio-intelligence`:

```bash
python3 scripts/desktop_local_smoke.py    # verifies local API + session + export
python3 scripts/run_personal_desktop.py   # starts local UI in your browser
```

What you get immediately:

| Capability | Status |
| --- | --- |
| No application login | Done |
| Loopback-only API + per-launch session token | Done |
| Local data under OS Application Support | Done |
| Startup backup + data export zip | Done |
| No Docker / Postgres for personal use | Done |
| No order submission | Done |
| Personal desktop UI (local browser) | Done |
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

## Current stage vs signed installers

| Area | Status |
| --- | --- |
| Personal local runtime (smoke + launcher) | **GO** |
| Full Next.js interactive panels in desktop shell | **GO** (static export under `apps/web/out`) |
| Tauri + PyInstaller sidecar installer build | **GO** on machines with Rust + PyInstaller |
| Signed / notarized DMG / EXE | Blocked on Apple/Windows signing certificates |
| Docker / Postgres | CI and developer use only |

Signed installers are optional for **your own** machine. Personal FULL GO does not require notarization.

## Architecture

```text
Tauri desktop app
├── Next.js static UI (apps/web/out) in the webview
├── FastAPI sidecar on 127.0.0.1:<random port>
├── X-Local-Session injected as window.__DESKTOP_RUNTIME__
├── JSON state in Application Support
└── OS Keychain for Flex tokens
```

Deployment modes:

```text
desktop_local   → personal use (no login)
development     → engineering (Docker/Postgres allowed)
```

## Developer notes

Docker Compose remains for CI:

```bash
cd infra && docker compose up --build
```

Full desktop installer (requires Rust toolchain + PyInstaller):

```bash
# One-shot: sidecar + static web + Tauri .app + DMG
python3 scripts/build-desktop-installer.py

# Or step by step:
python3 scripts/build-backend-sidecar.py
python3 scripts/prepare-tauri-binaries.py   # builds Next static export (uses /tmp on Documents volumes)
cd apps/desktop && npm install && npx tauri build
```

Artifacts:

```text
apps/desktop/src-tauri/target/release/bundle/macos/Portfolio Analyzer.app
apps/desktop/src-tauri/target/release/bundle/dmg/Portfolio Analyzer_0.1.0_aarch64.dmg
```

Note: Tauri’s built-in DMG step can fail when the repo path contains spaces; `build-desktop-installer.py` creates the DMG with `hdiutil` instead.

## Product claims

Supported: broker-reconciled personal analytics, tax estimates, proxy attribution, decision-support signals, broker-reported margin.

Not claimed: official books and records, CRA filing, registered advice, official Brinson, broker-equivalent margin, automated trading.

See `docs/PRODUCT_SCOPE.md`.
