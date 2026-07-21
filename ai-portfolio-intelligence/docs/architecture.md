# Architecture

```mermaid
flowchart TD
  A["IBKR Read-Only Data"] --> B["Broker Adapter Layer"]
  B --> C["Portfolio Database"]
  C --> D["Portfolio Accounting Engine"]
  D --> E["Portfolio Risk Engine"]
  D --> F["Stock Scoring Engine"]
  E --> G["Decision-Support Engine"]
  F --> G
  G --> H["AI Research Engine"]
  H --> I["Reports, Alerts, Watchlist, Dashboard"]
```

The default desktop/runtime uses `IBKRReadOnlyAdapter` for live Gateway/TWS read-only market and portfolio data when configured. `MockIBKRAdapter` remains available for explicit demo mode and tests. Live adapters must remain limited to the read-only `BrokerAdapter` contract (`order_generated` permanently false).

The backend is a FastAPI service with typed Pydantic schemas and SQLAlchemy models. The frontend is a Next.js dashboard consuming REST endpoints.
