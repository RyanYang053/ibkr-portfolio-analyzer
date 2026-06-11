from abc import ABC, abstractmethod
from datetime import date

from app.schemas.domain import AccountSummary, BrokerAccount, OpenOrderReadOnly, Position, Transaction


class BrokerAdapter(ABC):
    """Read-only broker adapter contract.

    Implementations may retrieve account, position, transaction, order-status, and
    market data. The contract deliberately excludes order placement, order
    modification, cancellation, execution, and rebalancing methods.
    """

    @abstractmethod
    def get_accounts(self) -> list[BrokerAccount]:
        raise NotImplementedError

    @abstractmethod
    def get_account_summary(self, account_id: str) -> AccountSummary:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self, account_id: str) -> list[Position]:
        raise NotImplementedError

    @abstractmethod
    def get_transactions(self, account_id: str, start_date: date, end_date: date) -> list[Transaction]:
        raise NotImplementedError

    @abstractmethod
    def get_open_orders_readonly(self, account_id: str) -> list[OpenOrderReadOnly]:
        raise NotImplementedError

    @abstractmethod
    def get_latest_price(self, symbol: str) -> float:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> dict[str, str]:
        raise NotImplementedError
