from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Iterable

from app.schemas.domain import Position, Transaction
from app.services.attribution.benchmark_weights import benchmark_sector_weights_as_of
from app.services.attribution.daily_contribution import DailyContribution
from app.services.attribution.engine import SECTOR_BENCHMARK_ETF
from app.services.market_data.exchange_calendar import is_us_equity_trading_day, previous_trading_session
from app.services.portfolio.pnl_tracker import PortfolioPnLSnapshot

DAILY_ATTRIBUTION_STATUS = "experimental_static_weight_daily_attribution"
HOLDINGS_DAILY_ATTRIBUTION_STATUS = "price_only_holdings_attribution"
PARTIAL_LEDGER_ATTRIBUTION_STATUS = "ledger_enriched_partial_attribution"
TOTAL_RETURN_DAILY_ATTRIBUTION_STATUS = "ledger_backed_total_return_attribution"
WITHHELD_ATTRIBUTION_STATUS = "withheld_attribution_identity_failure"
# Backward-compatible aliases used by older tests/callers.
LEGACY_HOLDINGS_DAILY_ATTRIBUTION_STATUS = "ledger_backed_daily_holdings_attribution"
LEGACY_TOTAL_RETURN_DAILY_ATTRIBUTION_STATUS = "ledger_backed_total_return_daily_attribution"

INCOME_ACTIONS = {"dividend", "dividend_reversal", "interest", "interest_reversal"}
FEE_ACTIONS = {"fee", "fee_reversal"}
TAX_ACTIONS = {"withholding_tax", "withholding_tax_reversal"}
CORP_ACTIONS = {"corporate_action", "cash_in_lieu"}
FX_ACTIONS = {"fx"}
CASH_ONLY_ACTIONS = {
    "deposit",
    "withdrawal",
    "contribution",
    "distribution",
    "transfer",
    "transfer_in",
    "transfer_out",
    "interest",
    "interest_reversal",
}


@dataclass(frozen=True)
class DailySecurityInput:
    date: date
    instrument_key: str
    sector: str
    beginning_weight: float
    total_return: float
    # When legs_from_ledger is True, non-price fields are portfolio contributions
    # (ledger dollars / beginning NAV), not instrument returns.
    income_return: float = 0.0
    fx_return: float = 0.0
    fee_return: float = 0.0
    tax_return: float = 0.0
    corp_action_return: float = 0.0
    legs_from_ledger: bool = False

    @property
    def non_price_portfolio_contribution(self) -> float:
        return (
            self.income_return
            + self.fx_return
            + self.fee_return
            + self.tax_return
            + self.corp_action_return
        )

    @property
    def composed_total_return(self) -> float:
        """Instrument total return used for sector Brinson sleeves."""
        if self.legs_from_ledger:
            if abs(self.beginning_weight) <= 1e-12:
                return self.price_return
            return self.price_return + (self.non_price_portfolio_contribution / self.beginning_weight)
        residual = (
            self.total_return
            - self.income_return
            - self.fx_return
            - self.fee_return
            - self.tax_return
            - self.corp_action_return
        )
        return residual

    @property
    def price_return(self) -> float:
        # total_return field holds the price leg when legs are decomposed.
        if self.legs_from_ledger:
            return self.total_return
        residual = (
            self.total_return
            - self.income_return
            - self.fx_return
            - self.fee_return
            - self.tax_return
            - self.corp_action_return
        )
        return residual


def trading_days_in_range(start: date, end: date) -> list[date]:
    if end < start:
        return []
    days: list[date] = []
    current = start
    while current <= end:
        if is_us_equity_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def _etf_close_on(etf: str, day: date, *, allow_mock: bool) -> float | None:
    from app.services.attribution.brinson_ledger import _price_on_or_before

    return _price_on_or_before(etf, day, allow_mock=allow_mock)


def _etf_daily_return(etf: str, day: date, *, allow_mock: bool) -> float | None:
    prior = previous_trading_session(day)
    start_close = _etf_close_on(etf, prior, allow_mock=allow_mock)
    end_close = _etf_close_on(etf, day, allow_mock=allow_mock)
    if start_close is None or end_close is None or start_close <= 0:
        return None
    return (end_close / start_close) - 1.0


def _daily_returns_from_history(
    history: list[PortfolioPnLSnapshot],
    period_start: date,
    period_end: date,
) -> tuple[dict[date, float], set[date]]:
    """Return daily returns and the set of days that used non-authoritative NAV fallback."""
    ordered = sorted(
        (
            item
            for item in history
            if period_start <= date.fromisoformat(item.date) <= period_end
        ),
        key=lambda item: (item.date, item.timestamp),
    )
    returns: dict[date, float] = {}
    nav_fallback_days: set[date] = set()
    for previous, current in zip(ordered, ordered[1:], strict=False):
        day = date.fromisoformat(current.date)
        if current.investment_return_percent is not None:
            returns[day] = float(current.investment_return_percent) / 100.0
            continue
        if previous.net_liquidation > 0:
            returns[day] = (current.net_liquidation - previous.net_liquidation) / previous.net_liquidation
            nav_fallback_days.add(day)
    return returns, nav_fallback_days


def _record_exit_evidence_missing(
    findings: list[dict[str, object]] | None,
    *,
    instrument_key: str,
    day: date,
) -> None:
    if findings is None:
        return
    findings.append(
        {
            "code": "exit_execution_evidence_missing",
            "instrument_key": instrument_key,
            "date": day.isoformat(),
        }
    )


def _instrument_key(symbol: str, con_id: int | None) -> str:
    if con_id is None:
        return symbol.upper()
    return f"{symbol.upper()}:{con_id}"


def _sector_for_symbol(symbol: str, positions: list[Position], fallback: str = "Unknown") -> str:
    for position in positions:
        if position.symbol.upper() == symbol.upper():
            return position.sector or fallback
    return fallback


def _signed_notional(txn: Transaction) -> float:
    if txn.amount is not None:
        return float(txn.amount)
    return float(txn.quantity) * float(txn.price)


def _txn_leg_dollars(txn: Transaction) -> tuple[str, float] | None:
    """Map a ledger transaction to (leg_name, signed dollar effect).

    Fee and withholding are returned as negative dollars (expenses).
    """
    action = txn.action
    notional = _signed_notional(txn)
    if action in {"dividend", "interest"}:
        return "income", notional
    if action in {"dividend_reversal", "interest_reversal"}:
        return "income", -abs(notional)
    if action == "fee":
        return "fee", -abs(notional)
    if action == "fee_reversal":
        return "fee", abs(notional)
    if action == "withholding_tax":
        return "tax", -abs(notional)
    if action == "withholding_tax_reversal":
        return "tax", abs(notional)
    if action in CORP_ACTIONS:
        return "corp_action", notional
    if action in FX_ACTIONS:
        return "fx", notional
    if action in {"buy", "sell"} and txn.commission:
        return "fee", -abs(float(txn.commission))
    return None


def _legs_populated(inputs: Iterable[DailySecurityInput]) -> bool:
    rows = list(inputs)
    if not rows:
        return False
    return any(row.legs_from_ledger for row in rows)


def _non_price_legs_observed(inputs: Iterable[DailySecurityInput]) -> bool:
    return any(
        abs(row.non_price_portfolio_contribution) > 1e-12
        for row in inputs
        if row.legs_from_ledger
    )


def _exit_price_return_from_transactions(
    *,
    symbol: str,
    con_id: int | None,
    prior_price: float,
    beginning_value: float,
    day: date,
    transactions: list[Transaction] | None,
) -> float | None:
    """Derive exit return from execution evidence; None means withhold."""
    if not transactions or prior_price <= 0:
        return None
    symbol_u = symbol.upper()
    matched: list[Transaction] = []
    for txn in transactions:
        if txn.trade_date != day:
            continue
        if str(txn.symbol or "").upper() != symbol_u:
            continue
        if con_id is not None and txn.con_id is not None and int(txn.con_id) != int(con_id):
            continue
        if txn.action not in {"sell", "sell_short", "buy_to_cover", "buy"}:
            continue
        # Closing a long uses sell; closing a short uses buy/buy_to_cover.
        if beginning_value > 0 and txn.action not in {"sell", "sell_short"}:
            continue
        if beginning_value < 0 and txn.action not in {"buy", "buy_to_cover"}:
            continue
        if float(txn.price or 0.0) <= 0 or abs(float(txn.quantity or 0.0)) <= 0:
            continue
        matched.append(txn)
    if not matched:
        return None
    notional = sum(abs(float(txn.quantity)) * float(txn.price) for txn in matched)
    qty = sum(abs(float(txn.quantity)) for txn in matched)
    if qty <= 0:
        return None
    vwap = notional / qty
    return (vwap / prior_price) - 1.0


def allocate_ledger_legs_for_day(
    transactions: list[Transaction],
    *,
    day: date,
    beginning_nav: float,
    instrument_keys: set[str],
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Allocate day ledger dollars to instruments and a cash sleeve.

    Returns (per_instrument_leg_dollars, cash_sleeve_leg_dollars).
    """
    per_instrument: dict[str, dict[str, float]] = {
        key: {"income": 0.0, "fx": 0.0, "fee": 0.0, "tax": 0.0, "corp_action": 0.0}
        for key in instrument_keys
    }
    cash_sleeve = {"income": 0.0, "fx": 0.0, "fee": 0.0, "tax": 0.0, "corp_action": 0.0}
    if beginning_nav == 0:
        return per_instrument, cash_sleeve

    for txn in transactions:
        if txn.trade_date != day:
            continue
        mapped = _txn_leg_dollars(txn)
        if mapped is None:
            continue
        leg, dollars = mapped
        key = _instrument_key(txn.symbol, txn.con_id) if txn.symbol else ""
        if key and key in per_instrument:
            per_instrument[key][leg] += dollars
        elif not txn.symbol or action_is_cash_sleeve(txn.action):
            cash_sleeve[leg] += dollars
        elif key:
            # Sold/exited name still present on ledger — keep a bucket.
            per_instrument.setdefault(
                key,
                {"income": 0.0, "fx": 0.0, "fee": 0.0, "tax": 0.0, "corp_action": 0.0},
            )
            per_instrument[key][leg] += dollars
        else:
            cash_sleeve[leg] += dollars
    return per_instrument, cash_sleeve


def action_is_cash_sleeve(action: str) -> bool:
    return action in CASH_ONLY_ACTIONS or action in {"interest", "interest_reversal", "fx"}


def enrich_security_inputs_with_ledger_legs(
    inputs: list[DailySecurityInput],
    transactions: list[Transaction],
    *,
    beginning_nav_by_day: dict[date, float] | None = None,
) -> tuple[list[DailySecurityInput], dict[date, dict[str, float]]]:
    """Attach income/FX/fee/tax/corp legs and return cash-sleeve returns by day."""
    if not inputs:
        return [], {}

    by_day: dict[date, list[DailySecurityInput]] = {}
    for row in inputs:
        by_day.setdefault(row.date, []).append(row)

    cash_sleeve_returns: dict[date, dict[str, float]] = {}
    enriched: list[DailySecurityInput] = []

    for day, day_rows in sorted(by_day.items()):
        beginning_nav = 0.0
        if beginning_nav_by_day and day in beginning_nav_by_day:
            beginning_nav = beginning_nav_by_day[day]
        else:
            # Reconstruct approximate beginning MV from weights * implied unit NAV=1.
            beginning_nav = sum(abs(row.beginning_weight) for row in day_rows) or 1.0

        instrument_keys = {row.instrument_key for row in day_rows}
        per_instrument, cash_dollars = allocate_ledger_legs_for_day(
            transactions,
            day=day,
            beginning_nav=beginning_nav,
            instrument_keys=instrument_keys,
        )
        scale = beginning_nav if beginning_nav else 1.0
        cash_sleeve_returns[day] = {
            leg: dollars / scale for leg, dollars in cash_dollars.items()
        }

        for row in day_rows:
            legs = per_instrument.get(row.instrument_key, {})
            income = legs.get("income", 0.0) / scale
            fx = legs.get("fx", 0.0) / scale
            fee = legs.get("fee", 0.0) / scale
            tax = legs.get("tax", 0.0) / scale
            corp = legs.get("corp_action", 0.0) / scale
            # Keep price leg in total_return; compose full total separately downstream.
            enriched.append(
                replace(
                    row,
                    income_return=income,
                    fx_return=fx,
                    fee_return=fee,
                    tax_return=tax,
                    corp_action_return=corp,
                    legs_from_ledger=True,
                )
            )

        # Include instruments that exited before the day but still have ledger activity.
        known = {row.instrument_key for row in day_rows}
        for key, legs in per_instrument.items():
            if key in known:
                continue
            if not any(legs.values()):
                continue
            enriched.append(
                DailySecurityInput(
                    date=day,
                    instrument_key=key,
                    sector="Unknown",
                    beginning_weight=0.0,
                    total_return=0.0,
                    income_return=legs.get("income", 0.0) / scale,
                    fx_return=legs.get("fx", 0.0) / scale,
                    fee_return=legs.get("fee", 0.0) / scale,
                    tax_return=legs.get("tax", 0.0) / scale,
                    corp_action_return=legs.get("corp_action", 0.0) / scale,
                    legs_from_ledger=True,
                )
            )

    return enriched, cash_sleeve_returns


def build_daily_security_inputs_from_history(
    history: list[PortfolioPnLSnapshot],
    *,
    period_start: date,
    period_end: date,
    positions: list[Position],
    transactions: list[Transaction] | None = None,
    quality_findings: list[dict[str, object]] | None = None,
) -> list[DailySecurityInput]:
    """Derive beginning-weight security returns from consecutive PnL snapshots.

    Uses signed market values (shorts included). Positions that exit between
    snapshots require execution evidence; without it the security/day is withheld
    rather than inventing a ±100% price return.
    """
    ordered = sorted(
        (
            item
            for item in history
            if period_start <= date.fromisoformat(item.date) <= period_end
        ),
        key=lambda item: (item.date, item.timestamp),
    )
    by_date: dict[date, PortfolioPnLSnapshot] = {}
    for snapshot in ordered:
        by_date[date.fromisoformat(snapshot.date)] = snapshot

    dates = sorted(by_date)
    inputs: list[DailySecurityInput] = []
    beginning_nav_by_day: dict[date, float] = {}
    for previous_date, current_date in zip(dates, dates[1:], strict=False):
        previous = by_date[previous_date]
        current = by_date[current_date]
        cash = float(getattr(previous, "cash", 0.0) or 0.0)
        # Signed gross exposure + cash for portfolio denominator.
        beginning_security = sum(float(row.market_value) for row in previous.positions)
        beginning_nav = beginning_security + cash
        if abs(beginning_nav) <= 1e-12:
            continue
        beginning_nav_by_day[current_date] = beginning_nav
        current_by_key = {
            _instrument_key(row.symbol, row.con_id): row
            for row in current.positions
        }
        for prior in previous.positions:
            beginning_value = float(prior.market_value)
            if abs(beginning_value) <= 1e-12 or prior.market_price == 0:
                continue
            key = _instrument_key(prior.symbol, prior.con_id)
            current_row = current_by_key.get(key)
            if current_row is not None and current_row.market_price != 0 and prior.market_price != 0:
                # Signed quantity path: short price rise is negative local return.
                price_return = (float(current_row.market_price) / float(prior.market_price)) - 1.0
            else:
                price_return = _exit_price_return_from_transactions(
                    symbol=prior.symbol,
                    con_id=prior.con_id,
                    prior_price=float(prior.market_price),
                    beginning_value=beginning_value,
                    day=current_date,
                    transactions=transactions,
                )
                if price_return is None:
                    _record_exit_evidence_missing(
                        quality_findings,
                        instrument_key=key,
                        day=current_date,
                    )
                    continue
            inputs.append(
                DailySecurityInput(
                    date=current_date,
                    instrument_key=key,
                    sector=_sector_for_symbol(prior.symbol, positions),
                    beginning_weight=beginning_value / beginning_nav,
                    total_return=price_return,
                )
            )

    if transactions:
        enriched, _cash = enrich_security_inputs_with_ledger_legs(
            inputs,
            transactions,
            beginning_nav_by_day=beginning_nav_by_day,
        )
        return enriched
    return inputs


def build_daily_security_inputs_from_daily_positions(
    account_id: str,
    *,
    period_start: date,
    period_end: date,
    positions: list[Position],
    transactions: list[Transaction] | None = None,
    quality_findings: list[dict[str, object]] | None = None,
) -> list[DailySecurityInput]:
    from app.db.daily_position_repo import read_daily_positions

    days = trading_days_in_range(period_start, period_end)
    if len(days) < 2:
        return []

    by_date: dict[date, list[dict]] = {}
    for day in days:
        try:
            rows = read_daily_positions(account_id, day)
        except Exception:
            rows = []
        if rows:
            by_date[day] = rows

    dated = sorted(by_date)
    if transactions is None:
        try:
            from app.services.portfolio.transaction_store import get_transactions

            transactions = get_transactions(account_id)
        except Exception:
            transactions = []

    inputs: list[DailySecurityInput] = []
    beginning_nav_by_day: dict[date, float] = {}
    for previous_date, current_date in zip(dated, dated[1:], strict=False):
        previous_rows = by_date[previous_date]
        current_rows = by_date[current_date]
        beginning_nav = 0.0
        for row in previous_rows:
            value = float(row.get("base_market_value") or row.get("market_value") or 0.0)
            beginning_nav += value
        cash = 0.0
        for row in previous_rows:
            if str(row.get("asset_class") or "").lower() == "cash":
                cash += float(row.get("base_market_value") or row.get("market_value") or 0.0)
        if abs(beginning_nav) <= 1e-12:
            continue
        beginning_nav_by_day[current_date] = beginning_nav
        current_by_key = {
            _instrument_key(str(row.get("symbol", "")), row.get("con_id")): row
            for row in current_rows
        }
        for prior in previous_rows:
            beginning_value = float(prior.get("base_market_value") or prior.get("market_value") or 0.0)
            prior_price = float(prior.get("market_price") or 0.0)
            if abs(beginning_value) <= 1e-12 or prior_price == 0:
                continue
            key = _instrument_key(str(prior.get("symbol", "")), prior.get("con_id"))
            current_row = current_by_key.get(key)
            if current_row is not None:
                current_price = float(current_row.get("market_price") or 0.0)
                if current_price == 0:
                    continue
                price_return = (current_price / prior_price) - 1.0
            else:
                price_return = _exit_price_return_from_transactions(
                    symbol=str(prior.get("symbol", "")),
                    con_id=prior.get("con_id"),
                    prior_price=prior_price,
                    beginning_value=beginning_value,
                    day=current_date,
                    transactions=transactions,
                )
                if price_return is None:
                    _record_exit_evidence_missing(
                        quality_findings,
                        instrument_key=key,
                        day=current_date,
                    )
                    continue
            sector = str(prior.get("sector") or _sector_for_symbol(str(prior.get("symbol", "")), positions))
            inputs.append(
                DailySecurityInput(
                    date=current_date,
                    instrument_key=key,
                    sector=sector,
                    beginning_weight=beginning_value / beginning_nav,
                    total_return=price_return,
                )
            )

    if transactions:
        enriched, _cash = enrich_security_inputs_with_ledger_legs(
            inputs,
            transactions,
            beginning_nav_by_day=beginning_nav_by_day,
        )
        return enriched
    return inputs


def _sector_portfolio_return(
    security_rows: list[DailySecurityInput],
    sector: str,
) -> float | None:
    sector_rows = [row for row in security_rows if row.sector == sector]
    sector_beginning_weight = sum(row.beginning_weight for row in sector_rows)
    if abs(sector_beginning_weight) <= 1e-12:
        return None
    return (
        sum(row.beginning_weight * row.composed_total_return for row in sector_rows)
        / sector_beginning_weight
    )


def build_daily_attribution_contributions(
    *,
    positions: list[Position],
    period_start: date,
    period_end: date,
    portfolio_sector_weights: dict[str, float],
    allow_mock: bool,
    history: list[PortfolioPnLSnapshot] | None = None,
    benchmark_id: str = "SPY",
    account_id: str | None = None,
    security_inputs: list[DailySecurityInput] | None = None,
    transactions: list[Transaction] | None = None,
    cash_sleeve_returns: dict[date, dict[str, float]] | None = None,
) -> tuple[list[DailyContribution], str, dict[str, object]]:
    """Build daily Brinson contributions.

    Prefers holdings-based DailySecurityInput rows. Falls back to experimental
    static sector-weight attribution only when security-level inputs are absent.

    Returns (contributions, status, data_quality extras including cash residual).
    """
    quality: dict[str, object] = {}
    findings: list[dict[str, object]] = []
    benchmark_sector_weights = benchmark_sector_weights_as_of(
        period_start,
        allow_mock=allow_mock,
        benchmark_id=benchmark_id,
    )
    if not benchmark_sector_weights:
        return [], DAILY_ATTRIBUTION_STATUS, quality

    resolved_inputs = list(security_inputs or [])
    resolved_cash = dict(cash_sleeve_returns or {})
    ledger_txns = list(transactions or [])

    if not resolved_inputs and account_id:
        if not ledger_txns:
            try:
                from app.services.portfolio.transaction_store import get_transactions

                ledger_txns = get_transactions(account_id)
            except Exception:
                ledger_txns = []
        resolved_inputs = build_daily_security_inputs_from_daily_positions(
            account_id,
            period_start=period_start,
            period_end=period_end,
            positions=positions,
            transactions=ledger_txns or None,
            quality_findings=findings,
        )
    if not resolved_inputs and history:
        if ledger_txns or account_id:
            if not ledger_txns and account_id:
                try:
                    from app.services.portfolio.transaction_store import get_transactions

                    ledger_txns = get_transactions(account_id)
                except Exception:
                    ledger_txns = []
            resolved_inputs = build_daily_security_inputs_from_history(
                history,
                period_start=period_start,
                period_end=period_end,
                positions=positions,
                transactions=ledger_txns or None,
                quality_findings=findings,
            )
        else:
            resolved_inputs = build_daily_security_inputs_from_history(
                history,
                period_start=period_start,
                period_end=period_end,
                positions=positions,
                quality_findings=findings,
            )

    if findings:
        quality["data_quality_findings"] = findings
        if any(item.get("code") == "exit_execution_evidence_missing" for item in findings):
            quality["exit_execution_evidence_missing"] = True

    if resolved_inputs and ledger_txns and not any(row.legs_from_ledger for row in resolved_inputs):
        resolved_inputs, resolved_cash = enrich_security_inputs_with_ledger_legs(
            resolved_inputs,
            ledger_txns,
        )

    if resolved_inputs:
        contributions = _build_holdings_based_contributions(
            security_inputs=resolved_inputs,
            portfolio_sector_weights=portfolio_sector_weights,
            benchmark_sector_weights=benchmark_sector_weights,
            allow_mock=allow_mock,
            period_start=period_start,
            period_end=period_end,
            cash_sleeve_returns=resolved_cash,
            quality=quality,
            history=history,
        )
        if (
            _non_price_legs_observed(resolved_inputs)
            and quality.get("nav_residual_within_tolerance") is True
            and quality.get("contribution_identity_ok") is True
        ):
            status = TOTAL_RETURN_DAILY_ATTRIBUTION_STATUS
        elif _legs_populated(resolved_inputs) and quality.get("contribution_identity_ok") is False:
            status = WITHHELD_ATTRIBUTION_STATUS
        elif _legs_populated(resolved_inputs):
            status = PARTIAL_LEDGER_ATTRIBUTION_STATUS
        else:
            status = HOLDINGS_DAILY_ATTRIBUTION_STATUS
        return contributions, status, quality

    contributions = _build_static_weight_contributions(
        positions=positions,
        period_start=period_start,
        period_end=period_end,
        portfolio_sector_weights=portfolio_sector_weights,
        benchmark_sector_weights=benchmark_sector_weights,
        allow_mock=allow_mock,
        history=history,
        quality=quality,
    )
    return contributions, DAILY_ATTRIBUTION_STATUS, quality


def _build_holdings_based_contributions(
    *,
    security_inputs: list[DailySecurityInput],
    portfolio_sector_weights: dict[str, float],
    benchmark_sector_weights: dict[str, float],
    allow_mock: bool,
    period_start: date,
    period_end: date,
    cash_sleeve_returns: dict[date, dict[str, float]] | None = None,
    quality: dict[str, object] | None = None,
    history: list[PortfolioPnLSnapshot] | None = None,
) -> list[DailyContribution]:
    from app.core.config import settings

    by_day: dict[date, list[DailySecurityInput]] = {}
    for row in security_inputs:
        if period_start <= row.date <= period_end:
            by_day.setdefault(row.date, []).append(row)

    nav_returns, nav_fallback_days = _daily_returns_from_history(history or [], period_start, period_end)
    sectors = sorted(set(portfolio_sector_weights) | set(benchmark_sector_weights))
    contributions: list[DailyContribution] = []
    cash_totals: list[float] = []
    nav_residuals: list[float] = []
    identity_ok = True
    for day in trading_days_in_range(period_start, period_end):
        day_rows = by_day.get(day, [])
        if not day_rows:
            continue
        price_daily = sum(row.beginning_weight * row.price_return for row in day_rows)
        # Evaluate ledger vs weight-scaled legs row-by-row so mixed days do not mis-scale.
        income_daily = 0.0
        fx_daily = 0.0
        fee_daily = 0.0
        tax_daily = 0.0
        corp_daily = 0.0
        for row in day_rows:
            if row.legs_from_ledger:
                income_daily += row.income_return
                fx_daily += row.fx_return
                fee_daily += row.fee_return
                tax_daily += row.tax_return
                corp_daily += row.corp_action_return
            else:
                income_daily += row.beginning_weight * row.income_return
                fx_daily += row.beginning_weight * row.fx_return
                fee_daily += row.beginning_weight * row.fee_return
                tax_daily += row.beginning_weight * row.tax_return
                corp_daily += row.beginning_weight * row.corp_action_return

        cash_legs = (cash_sleeve_returns or {}).get(day, {})
        cash_income = float(cash_legs.get("income", 0.0))
        cash_fx = float(cash_legs.get("fx", 0.0))
        cash_fee = float(cash_legs.get("fee", 0.0))
        cash_tax = float(cash_legs.get("tax", 0.0))
        cash_corp = float(cash_legs.get("corp_action", 0.0))
        cash_contribution = cash_income + cash_fx + cash_fee + cash_tax + cash_corp

        security_total = price_daily + income_daily + fx_daily + fee_daily + tax_daily + corp_daily
        portfolio_daily = security_total + cash_contribution
        cash_totals.append(cash_contribution)

        income_daily += cash_income
        fx_daily += cash_fx
        fee_daily += cash_fee
        tax_daily += cash_tax
        corp_daily += cash_corp

        folded_total = (
            price_daily + income_daily + fx_daily + fee_daily + tax_daily + corp_daily
        )
        if abs(folded_total - portfolio_daily) > settings.attribution_reconciliation_tolerance:
            identity_ok = False

        if day in nav_returns:
            residual = portfolio_daily - float(nav_returns[day])
            nav_residuals.append(residual)
        else:
            identity_ok = False

        beginning_weight_sum = sum(abs(row.beginning_weight) for row in day_rows)
        if beginning_weight_sum > 1.0 + settings.attribution_reconciliation_tolerance * 100:
            identity_ok = False

        benchmark_daily = _etf_daily_return("SPY", day, allow_mock=allow_mock) or 0.0

        allocation = 0.0
        selection = 0.0
        interaction = 0.0
        for sector in sectors:
            etf = SECTOR_BENCHMARK_ETF.get(sector, "SPY")
            sector_benchmark_daily = _etf_daily_return(etf, day, allow_mock=allow_mock)
            if sector_benchmark_daily is None:
                continue
            weight_p = sum(row.beginning_weight for row in day_rows if row.sector == sector)
            if abs(weight_p) <= 1e-12:
                weight_p = portfolio_sector_weights.get(sector, 0.0)
            weight_b = benchmark_sector_weights.get(sector, 0.0)
            sector_portfolio_daily = _sector_portfolio_return(day_rows, sector)
            if sector_portfolio_daily is None:
                continue
            allocation += (weight_p - weight_b) * sector_benchmark_daily
            selection += weight_b * (sector_portfolio_daily - sector_benchmark_daily)
            interaction += (weight_p - weight_b) * (sector_portfolio_daily - sector_benchmark_daily)

        contributions.append(
            DailyContribution(
                contribution_date=day,
                security_contribution=price_daily,
                income_contribution=income_daily,
                fx_contribution=fx_daily,
                fee_contribution=fee_daily,
                tax_contribution=tax_daily,
                corp_action_contribution=corp_daily,
                cash_contribution=cash_contribution,
                allocation_effect=allocation,
                selection_effect=selection,
                interaction_effect=interaction,
                portfolio_return=portfolio_daily,
                benchmark_return=benchmark_daily,
            )
        )

    if quality is not None:
        quality["cash_sleeve_contribution_sum"] = round(sum(cash_totals), 8)
        quality["security_plus_cash_days"] = len(contributions)
        max_abs_nav_residual = max((abs(value) for value in nav_residuals), default=None)
        quality["nav_residual_max_abs"] = (
            round(max_abs_nav_residual, 8) if max_abs_nav_residual is not None else None
        )
        quality["nav_residual_within_tolerance"] = bool(
            max_abs_nav_residual is not None
            and max_abs_nav_residual <= settings.attribution_reconciliation_tolerance
            and identity_ok
            and bool(nav_residuals)
        )
        quality["contribution_identity_ok"] = identity_ok
        if nav_fallback_days:
            quality["investment_return_non_authoritative"] = True
            quality["investment_return_degraded_days"] = sorted(
                day.isoformat() for day in nav_fallback_days
            )
            quality["investment_return_source"] = "nav_change_fallback"
            findings = list(quality.get("data_quality_findings") or [])
            findings.append(
                {
                    "code": "investment_return_nav_fallback",
                    "status": "non_authoritative",
                    "days": quality["investment_return_degraded_days"],
                }
            )
            quality["data_quality_findings"] = findings
    return contributions


def _build_static_weight_contributions(
    *,
    positions: list[Position],
    period_start: date,
    period_end: date,
    portfolio_sector_weights: dict[str, float],
    benchmark_sector_weights: dict[str, float],
    allow_mock: bool,
    history: list[PortfolioPnLSnapshot] | None,
    quality: dict[str, object] | None = None,
) -> list[DailyContribution]:
    _ = positions
    portfolio_returns, nav_fallback_days = _daily_returns_from_history(
        history or [], period_start, period_end
    )
    if quality is not None and nav_fallback_days:
        quality["investment_return_non_authoritative"] = True
        quality["investment_return_degraded_days"] = sorted(
            day.isoformat() for day in nav_fallback_days
        )
        quality["investment_return_source"] = "nav_change_fallback"
        findings = list(quality.get("data_quality_findings") or [])
        findings.append(
            {
                "code": "investment_return_nav_fallback",
                "status": "non_authoritative",
                "days": quality["investment_return_degraded_days"],
            }
        )
        quality["data_quality_findings"] = findings
    sectors = sorted(set(portfolio_sector_weights) | set(benchmark_sector_weights))
    total_portfolio_weight = sum(portfolio_sector_weights.values()) or 1.0
    contributions: list[DailyContribution] = []

    for day in trading_days_in_range(period_start, period_end):
        portfolio_daily = portfolio_returns.get(day)
        if portfolio_daily is None:
            continue

        benchmark_daily = _etf_daily_return("SPY", day, allow_mock=allow_mock) or 0.0
        allocation = 0.0
        selection = 0.0
        interaction = 0.0
        for sector in sectors:
            etf = SECTOR_BENCHMARK_ETF.get(sector, "SPY")
            sector_benchmark_daily = _etf_daily_return(etf, day, allow_mock=allow_mock)
            if sector_benchmark_daily is None:
                continue
            weight_p = portfolio_sector_weights.get(sector, 0.0)
            weight_b = benchmark_sector_weights.get(sector, 0.0)
            if weight_p > 0:
                sector_portfolio_daily = portfolio_daily * (weight_p / total_portfolio_weight)
            else:
                continue
            allocation += (weight_p - weight_b) * sector_benchmark_daily
            selection += weight_b * (sector_portfolio_daily - sector_benchmark_daily)
            interaction += (weight_p - weight_b) * (sector_portfolio_daily - sector_benchmark_daily)

        contributions.append(
            DailyContribution(
                contribution_date=day,
                security_contribution=portfolio_daily,
                income_contribution=0.0,
                fx_contribution=0.0,
                fee_contribution=0.0,
                tax_contribution=0.0,
                allocation_effect=allocation,
                selection_effect=selection,
                interaction_effect=interaction,
                portfolio_return=portfolio_daily,
                benchmark_return=benchmark_daily,
            )
        )
    return contributions
