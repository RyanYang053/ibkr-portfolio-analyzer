# Qlib research-validation boundary

This package is a **disconnected research stub**. It must not import or mutate
portfolio accounting, tax lots, transaction ledgers, or Decision Center scoring.

## Rules

1. Consume **exported feature frames only** (returns, factors) produced outside this path.
2. Walk-forward, transaction-cost, and liquidity validation must pass before any
   Qlib / RL signal is considered for Decision Center input.
3. **Default: disconnected.** No production route imports this package.
4. CI does **not** require a Qlib install.

## Adapter

See `adapter.py` for the thin interface. Implementations may optionally depend on
`pyqlib` in a separate research environment.
