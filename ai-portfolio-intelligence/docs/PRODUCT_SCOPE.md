# Product scope

This application is designed for an individual account owner operating
a self-directed portfolio on their own computer.

## Delivery model

- Cross-platform **local desktop app** (Tauri + bundled FastAPI sidecar)
- One-click installers; no Python, Node, Docker, or PostgreSQL for end users
- No application login, subscription account, or hosted portfolio backend
- All portfolio data remains on the user’s device (SQLite + OS Keychain)

## Supported claims

- Broker-reconciled personal portfolio analytics
- Tax estimation and tax-lot reconciliation
- Proxy-based allocation and attribution analysis
- Personal investment decision-support signals
- Broker-reported margin monitoring
- Internal risk and stress scenarios

## Unsupported claims

- Official books and records
- CRA-certified tax filing
- Registered investment advice
- Official constituent-level benchmark attribution
- Broker-equivalent portfolio-margin calculation
- Automated trade execution
- Multi-user hosted / cloud portfolio storage
