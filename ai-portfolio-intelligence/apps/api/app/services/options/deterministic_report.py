from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.schemas.domain import Position
from app.services.options.contract_filters import OptionLiquidityPolicy, is_liquid, is_otm_call, is_otm_put
from app.services.options.engine import (
    OptionContract,
    calculate_cash_secured_put_metrics,
    calculate_covered_call_metrics,
    evaluate_strategy_eligibility,
)


def _relaxed_policy_for_demo() -> OptionLiquidityPolicy:
    return OptionLiquidityPolicy(
        max_quote_age_seconds=86_400,
        max_bid_ask_spread_percent=100.0,
        min_open_interest=0,
        min_volume=0,
        require_open_interest=False,
        require_volume=False,
        min_bid=0.0,
    )


def _select_covered_call(calls: list[OptionContract], spot: float) -> OptionContract | None:
    eligible = [contract for contract in calls if contract.strike >= spot]
    if not eligible:
        return None
    return min(eligible, key=lambda contract: (contract.strike - spot, contract.expiration))


def _select_cash_secured_put(puts: list[OptionContract], spot: float) -> OptionContract | None:
    eligible = [contract for contract in puts if contract.strike <= spot]
    if not eligible:
        return None
    return max(eligible, key=lambda contract: (contract.strike, contract.expiration))


def _liquid_contracts(
    chain: list[OptionContract],
    spot: float,
    policy: OptionLiquidityPolicy,
    now: datetime,
) -> tuple[list[OptionContract], list[OptionContract]]:
    calls = [
        contract
        for contract in chain
        if contract.right.upper() == "C" and is_otm_call(contract, spot) and is_liquid(contract, policy, now=now)
    ]
    puts = [
        contract
        for contract in chain
        if contract.right.upper() == "P" and is_otm_put(contract, spot) and is_liquid(contract, policy, now=now)
    ]
    return calls, puts


def _strategy_payload(
    *,
    name: str,
    contract: OptionContract,
    position: Position,
    cash_available: float,
    account_type: str,
    metrics: dict[str, Any],
    rationale: str,
) -> dict[str, Any]:
    multiplier = contract.multiplier or 100.0
    eligible, reason = evaluate_strategy_eligibility(
        name,
        contract.strike,
        position.market_price,
        position.quantity,
        cash_available,
        account_type,
        contract_multiplier=multiplier,
        contract_currency=contract.currency or position.currency,
        account_currency=position.currency,
    )
    right_label = "Call" if contract.right.upper() == "C" else "Put"
    return {
        "name": name,
        "type": "income",
        "expiration": contract.expiration.isoformat(),
        "strikes": f"Sell ${contract.strike:.2f} {right_label}",
        "target_contract_symbols": [contract.symbol],
        "net_premium": contract.mid,
        "premium_cash": round(contract.mid * multiplier, 2),
        "premium_type": "credit",
        "net_credit_debit": contract.mid,
        "max_profit": metrics["max_profit"],
        "max_loss": metrics["max_loss"],
        "breakeven": metrics["breakeven"],
        "probability_of_profit": None,
        "rationale": rationale,
        "eligible": eligible,
        "eligibility_reason": reason,
        "contract_multiplier": multiplier,
        "contract_currency": contract.currency or position.currency,
    }


def build_validated_strategy_candidates(
    position: Position,
    chain: list[OptionContract],
    *,
    cash_available: float,
    account_type: str,
    is_demo: bool = False,
    liquidity_policy: OptionLiquidityPolicy | None = None,
) -> list[dict[str, Any]]:
    policy = liquidity_policy or (_relaxed_policy_for_demo() if is_demo else OptionLiquidityPolicy())
    now = datetime.now(timezone.utc)
    spot = position.market_price
    calls, puts = _liquid_contracts(chain, spot, policy, now)
    candidates: list[dict[str, Any]] = []

    call = _select_covered_call(calls, spot)
    if call:
        multiplier = call.multiplier or 100.0
        metrics = calculate_covered_call_metrics(position.market_price, call.strike, call.mid, multiplier=multiplier)
        candidates.append(
            _strategy_payload(
                name="Covered Call (Educational Candidate)",
                contract=call,
                position=position,
                cash_available=cash_available,
                account_type=account_type,
                metrics=metrics,
                rationale="Validated covered-call candidate from production liquidity gates.",
            )
        )

    put = _select_cash_secured_put(puts, spot)
    if put:
        multiplier = put.multiplier or 100.0
        metrics = calculate_cash_secured_put_metrics(put.strike, put.mid, multiplier=multiplier)
        candidates.append(
            _strategy_payload(
                name="Cash-Secured Put (Educational Candidate)",
                contract=put,
                position=position,
                cash_available=cash_available,
                account_type=account_type,
                metrics=metrics,
                rationale="Validated cash-secured put candidate from production liquidity gates.",
            )
        )
    return candidates


def build_deterministic_options_report(
    position: Position,
    chain: list[OptionContract],
    *,
    cash_available: float,
    account_type: str,
    chain_source: str,
    is_demo: bool = False,
    liquidity_policy: OptionLiquidityPolicy | None = None,
) -> dict[str, Any]:
    """Compute validated strategy economics without an LLM."""
    from app.schemas.domain import utc_now

    if not chain:
        raise ValueError("options chain is required")

    policy = liquidity_policy or (_relaxed_policy_for_demo() if is_demo else OptionLiquidityPolicy())
    datetime.now(timezone.utc)
    strategies = build_validated_strategy_candidates(
        position,
        chain,
        cash_available=cash_available,
        account_type=account_type,
        is_demo=is_demo,
        liquidity_policy=policy,
    )

    atm = min(chain, key=lambda item: abs(item.strike - position.market_price))
    atm_iv = atm.implied_volatility
    days = max((atm.expiration - date.today()).days, 1)
    base_report = {
        "symbol": position.symbol,
        "stock_price": position.market_price,
        "implied_volatility": atm_iv,
        "iv_percentile": None,
        "implied_move_percent": round(atm_iv * (days / 365.0) ** 0.5 * 100.0, 2),
        "implied_move_horizon_days": days,
        "market_sentiment": "Deterministic economics from validated option chain quotes.",
        "human_review_required": True,
        "disclaimer": "Educational options analysis only. Verify quotes before trading.",
        "provider": "deterministic_options_engine",
        "asOf": utc_now().isoformat(),
        "dataSource": chain_source,
        "isMock": is_demo,
        "provenance": {
            "options_chain_source": chain_source,
            "deterministic_engine": True,
            "llm_narrative": False,
        },
    }

    if not strategies:
        return {
            **base_report,
            "status": "withheld_no_liquid_contracts",
            "strategies": [],
            "warnings": ["No contracts passed production liquidity and freshness gates."],
        }

    return {
        **base_report,
        "strategies": strategies,
        "warnings": ["Deterministic strategy economics; narrative explanation omitted without Gemini."],
    }
