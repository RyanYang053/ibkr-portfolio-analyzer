# IBKR Read-Only Setup

The MVP does not connect to live IBKR yet. Mock portfolio data is disabled by default and is available only when explicitly setting `BROKER_MODE=mock_ibkr_readonly`.

Future live implementation should:

- Use official IBKR read-only account, portfolio, transaction, open-order status, and market data APIs where available
- Avoid storing raw broker credentials
- Avoid unsafe login automation
- Keep all data user-scoped
- Keep broker connector methods limited to `BrokerAdapter`
- Preserve tests that assert no trading methods or forbidden routes exist

The live adapter must not add order placement, order modification, cancellation, execution, or rebalancing methods.
