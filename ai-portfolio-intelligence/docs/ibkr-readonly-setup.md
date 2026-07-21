# IBKR Read-Only Setup

A live read-only adapter is implemented: `IBKRReadOnlyAdapter`
(`apps/api/app/services/broker/ibkr_readonly.py`) connects to a running IB Gateway /
TWS session via `ib_insync` with `readonly=True` and exposes only `BrokerAdapter`
read methods. Mock portfolio data is disabled by default and is available only when
explicitly setting `BROKER_MODE=mock_ibkr_readonly`.

The live adapter, by design:

- Uses the read-only account, portfolio, transaction, and open-order-status APIs
- Never stores raw broker credentials (no IBKR password is ever collected)
- Avoids unsafe login automation
- Keeps all data user-scoped
- Limits broker connector methods to `BrokerAdapter`
- Is covered by tests asserting no trading methods or forbidden routes exist

The adapter must never add order placement, order modification, cancellation,
execution, or rebalancing methods.
