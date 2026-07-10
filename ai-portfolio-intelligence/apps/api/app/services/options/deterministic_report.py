from __future__ import annotations

from datetime import date
from typing import Any

from app.schemas.domain import Position
from app.services.options.engine import (
    OptionContract,
    calculate_cash_secured_put_metrics,
    calculate_covered_call_metrics,
    evaluate_strategy_eligibility,
)


def build_deterministic_options_report(
    position: Position,
    chain: list[OptionContract],
    *,
    cash_available: float,
    account_type: str,
    chain_source: str,
) -> dict[str, Any]:
    """Compute validated strategy economics without an LLM."""
    from app.schemas.domain import utc_now

    if not chain:
        raise ValueError("options chain is required")

    calls = [contract for contract in chain if contract.right.upper() == "C"]
    puts = [contract for contract in chain if contract.right.upper() == "P"]
    calls = sorted(calls, key=lambda item: abs(item.strike - position.market_price))
    puts = sorted(puts, key=lambda item: abs(item.strike - position.market_price))

    strategies: list[dict[str, Any]] = []
    if calls:
        call = calls[min(1, len(calls) - 1)] if len(calls) > 1 else calls[0]
        metrics = calculate_covered_call_metrics(position.market_price, call.strike, call.mid)
        eligible, reason = evaluate_strategy_eligibility(
            "Covered Call (Educational Candidate)",
            call.strike,
            position.market_price,
            position.quantity,
            cash_available,
            account_type,
        )
        strategies.append(
            {
                "name": "Covered Call (Educational Candidate)",
                "type": "income",
                "expiration": call.expiration.isoformat(),
                "strikes": f"Sell ${call.strike:.2f} Call",
                "net_premium": call.mid,
                "premium_type": "credit",
                "net_credit_debit": call.mid,
                "max_profit": metrics["max_profit"],
                "max_loss": metrics["max_loss"],
                "breakeven": metrics["breakeven"],
                "probability_of_profit": None,
                "rationale": "Deterministic covered-call candidate from live option chain economics.",
                "eligible": eligible,
                "eligibility_reason": reason,
            }
        )

    if puts:
        put = puts[min(1, len(puts) - 1)] if len(puts) > 1 else puts[0]
        metrics = calculate_cash_secured_put_metrics(put.strike, put.mid)
        eligible, reason = evaluate_strategy_eligibility(
            "Cash-Secured Put (Educational Candidate)",
            put.strike,
            position.market_price,
            position.quantity,
            cash_available,
            account_type,
        )
        strategies.append(
            {
                "name": "Cash-Secured Put (Educational Candidate)",
                "type": "income",
                "expiration": put.expiration.isoformat(),
                "strikes": f"Sell ${put.strike:.2f} Put",
                "net_premium": put.mid,
                "premium_type": "credit",
                "net_credit_debit": put.mid,
                "max_profit": metrics["max_profit"],
                "max_loss": metrics["max_loss"],
                "breakeven": metrics["breakeven"],
                "probability_of_profit": None,
                "rationale": "Deterministic cash-secured put candidate from live option chain economics.",
                "eligible": eligible,
                "eligibility_reason": reason,
            }
        )

    atm = min(chain, key=lambda item: abs(item.strike - position.market_price))
    atm_iv = atm.implied_volatility
    days = max((atm.expiration - date.today()).days, 1)
    return {
        "symbol": position.symbol,
        "stock_price": position.market_price,
        "implied_volatility": atm_iv,
        "iv_percentile": None,
        "implied_move_percent": round(atm_iv * (days / 365.0) ** 0.5 * 100.0, 2),
        "implied_move_horizon_days": days,
        "strategies": strategies,
        "market_sentiment": "Deterministic economics from validated option chain quotes.",
        "human_review_required": True,
        "disclaimer": "Educational options analysis only. Verify quotes before trading.",
        "provider": "deterministic_options_engine",
        "asOf": utc_now().isoformat(),
        "dataSource": chain_source,
        "isMock": False,
        "warnings": ["Deterministic strategy economics; narrative explanation omitted without Gemini."],
        "provenance": {
            "options_chain_source": chain_source,
            "deterministic_engine": True,
            "llm_narrative": False,
        },
    }
