from datetime import date, timedelta

from app.schemas.domain import AccountSummary, BrokerAccount, OpenOrderReadOnly, Position, Transaction, utc_now
from app.services.broker.base import BrokerAdapter
from app.services.broker.securities import SECURITIES_DB as SAMPLE_SECURITIES

MOCK_CON_IDS = {
    "QQQ": 320227571,
    "SPY": 756733,
    "MSFT": 272093,
    "META": 107113386,
    "GOOGL": 208813720,
    "SOXX": 229725622,
    "SOFI": 494162451,
    "CRM": 29624264,
    "CELH": 71364351,
    "NKE": 10291,
    "IONQ": 517593749,
    "LAES": 665380967,
    "INFQ": 531212348,
}

MOCK_LOTS = {
    "QQQ": (68, 405, 468),
    "SPY": (52, 485, 545),
    "MSFT": (45, 338, 425),
    "META": (27, 410, 505),
    "GOOGL": (70, 132, 176),
    "SOXX": (38, 196, 232),
    "SOFI": (650, 8.4, 10.2),
    "CRM": (31, 215, 254),
    "CELH": (120, 42, 56),
    "NKE": (78, 82, 93),
    "IONQ": (400, 11, 18),
    "LAES": (900, 1.6, 2.4),
    "INFQ": (750, 2.1, 1.7),
}


class MockIBKRAdapter(BrokerAdapter):
    def __init__(self) -> None:
        self.account_id = "MOCK-001"
        self._synced_at = utc_now()

    def get_accounts(self) -> list[BrokerAccount]:
        return [
            BrokerAccount(
                id="MOCK-001",
                account_number_hash="sha256:mocked-account-number-1",
                account_alias="Mock USD Portfolio",
                account_type="Margin",
                base_currency="USD",
                status="connected_mock_readonly",
                last_sync_at=self._synced_at,
            ),
            BrokerAccount(
                id="MOCK-002",
                account_number_hash="sha256:mocked-account-number-2",
                account_alias="Mock CAD Portfolio",
                account_type="Margin",
                base_currency="CAD",
                status="connected_mock_readonly",
                last_sync_at=self._synced_at,
            ),
        ]

    def get_account_summary(self, account_id: str) -> AccountSummary:
        positions = self.get_positions(account_id)
        market_value = sum(position.market_value for position in positions)
        cash = 32500.0 if account_id == "MOCK-001" else 45000.0
        unrealized = sum(position.unrealized_pnl for position in positions)
        net_liquidation = market_value + cash
        base_currency = "USD" if account_id == "MOCK-001" else "CAD"
        return AccountSummary(
            account_id=account_id,
            net_liquidation=round(net_liquidation, 2),
            cash=cash,
            buying_power=125000.0 if account_id == "MOCK-001" else 150000.0,
            margin_requirement=18500.0 if account_id == "MOCK-001" else 22000.0,
            excess_liquidity=94000.0 if account_id == "MOCK-001" else 128000.0,
            total_unrealized_pnl=round(unrealized, 2),
            total_realized_pnl=7420.0 if account_id == "MOCK-001" else 3120.0,
            base_currency=base_currency,
            data_timestamp=self._synced_at,
        )

    def get_positions(self, account_id: str) -> list[Position]:
        lots = MOCK_LOTS
        if account_id == "MOCK-002":
            lots = {k: v for k, v in MOCK_LOTS.items() if k in {"QQQ", "SPY", "MSFT", "GOOGL"}}

        raw_values = {
            symbol: quantity * market_price
            for symbol, (quantity, _avg_cost, market_price) in lots.items()
        }
        invested_value = sum(raw_values.values())
        positions: list[Position] = []
        for symbol, (quantity, avg_cost, market_price) in lots.items():
            company, asset_class, exchange, currency, sector, industry, stock_type, is_etf, is_speculative = SAMPLE_SECURITIES[symbol]
            currency_to_use = "CAD" if account_id == "MOCK-002" else currency
            market_value = quantity * market_price
            unrealized = (market_price - avg_cost) * quantity
            positions.append(
                Position(
                    account_id=account_id,
                    symbol=symbol,
                    company_name=company,
                    asset_class=asset_class,
                    quantity=quantity,
                    avg_cost=avg_cost,
                    market_price=market_price,
                    market_value=round(market_value, 2),
                    unrealized_pnl=round(unrealized, 2),
                    realized_pnl=0,
                    currency=currency_to_use,
                    exchange=exchange,
                    sector=sector,
                    industry=industry,
                    portfolio_weight=round(market_value / invested_value * 100, 2),
                    stock_type=stock_type,
                    is_etf=is_etf,
                    is_speculative=is_speculative,
                    updated_at=self._synced_at,
                    con_id=MOCK_CON_IDS.get(symbol),
                    local_symbol=symbol,
                    multiplier=1.0,
                    price_source="mock_broker",
                )
            )
        return positions

    def get_transactions(self, account_id: str, start_date: date, end_date: date) -> list[Transaction]:
        currency = "USD" if account_id == "MOCK-001" else "CAD"
        rows = [
            Transaction(
                account_id=account_id,
                symbol="MSFT",
                trade_date=end_date - timedelta(days=18),
                action="buy",
                quantity=3,
                price=410,
                commission=1,
                currency=currency,
                con_id=MOCK_CON_IDS["MSFT"],
                local_symbol="MSFT",
                transaction_id=f"{account_id}:buy:MSFT:1",
                amount=1230.0,
                source="mock_ibkr_readonly",
            ),
            Transaction(
                account_id=account_id,
                symbol="QQQ",
                trade_date=end_date - timedelta(days=45),
                action="dividend",
                quantity=68,
                price=0.74,
                commission=0,
                currency=currency,
                con_id=MOCK_CON_IDS["QQQ"],
                local_symbol="QQQ",
                transaction_id=f"{account_id}:dividend:QQQ:1",
                amount=50.32,
                source="mock_ibkr_readonly",
            ),
            Transaction(
                account_id=account_id,
                symbol="CASH",
                trade_date=end_date - timedelta(days=120),
                action="deposit",
                quantity=1,
                price=25000,
                commission=0,
                currency=currency,
                transaction_id=f"{account_id}:deposit:1",
                amount=25000.0,
                source="mock_ibkr_readonly",
            ),
            Transaction(
                account_id=account_id,
                symbol="CASH",
                trade_date=end_date - timedelta(days=10),
                action="withdrawal",
                quantity=1,
                price=5000,
                commission=0,
                currency=currency,
                transaction_id=f"{account_id}:withdrawal:1",
                amount=5000.0,
                source="mock_ibkr_readonly",
            ),
        ]
        return [row for row in rows if start_date <= row.trade_date <= end_date]

    def get_open_orders_readonly(self, account_id: str) -> list[OpenOrderReadOnly]:
        return []

    def get_latest_price(self, symbol: str) -> float:
        if symbol not in MOCK_LOTS:
            raise KeyError(f"No mock price for {symbol}")
        return MOCK_LOTS[symbol][2]

    def health_check(self) -> dict[str, str]:
        return {
            "status": "healthy",
            "mode": "mock_ibkr_readonly",
            "trading": "disabled",
            "credential_storage": "no_ibkr_credentials_stored",
        }
