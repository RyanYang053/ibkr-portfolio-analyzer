from typing import Literal
from app.schemas.domain import (
    AccountSummary,
    InvestorProfile,
    InvestmentPolicyStatement,
    Position,
    RebalanceProposal,
    RebalanceProposalItem
)
from app.services.policy.engine import analyze_policy_drift

def generate_rebalance_proposal(
    positions: list[Position],
    summary: AccountSummary,
    policy: InvestmentPolicyStatement,
    profile: InvestorProfile
) -> RebalanceProposal:
    """Optimize portfolio weights by generating buy/sell proposals."""
    total_val = max(summary.net_liquidation, 1.0)
    current_cash = summary.cash
    
    # 1. Analyze drift first
    drift_analysis = analyze_policy_drift(positions, current_cash, total_val, policy)
    drifts = drift_analysis["drifts"]
    
    proposed_trades: list[RebalanceProposalItem] = []
    
    # 2. Determine target allocations
    target_cash_val = total_val * (policy.target_cash_percent / 100.0)
    
    # Minimum cash constraint: cash must be at least policy.minimum_cash
    cash_floor = max(policy.minimum_cash, target_cash_val)
    cash_diff = cash_floor - current_cash
    
    # We will accumulate adjustments
    cash_to_raise = 0.0
    if cash_diff > 0:
        # We need to raise cash
        cash_to_raise = cash_diff
        
    # Group positions into segments
    single_stocks = [p for p in positions if not p.is_etf and p.asset_class != "OPT"]
    speculative = [p for p in positions if p.is_speculative]
    etfs = [p for p in positions if p.is_etf]
    
    # 3. Check for specific concentration trims first
    # 3a. Single stock concentration limits
    for pos in single_stocks:
        weight = pos.portfolio_weight
        if weight > policy.max_single_stock_weight:
            excess_weight = weight - policy.max_single_stock_weight
            excess_val = total_val * (excess_weight / 100.0)
            
            qty = excess_val / max(pos.market_price, 0.01)
            proposed_trades.append(
                RebalanceProposalItem(
                    symbol=pos.symbol,
                    current_weight=round(pos.portfolio_weight, 2),
                    target_weight=round(policy.max_single_stock_weight, 2),
                    current_value=round(pos.market_value, 2),
                    proposed_trade_value=round(-excess_val, 2),
                    proposed_trade_qty=round(-qty, 2),
                    action="Sell",
                    reason=f"Trim single stock concentration (current weight {weight:.2f}% exceeds limit of {policy.max_single_stock_weight}%)."
                )
            )
            cash_to_raise -= excess_val # reduces cash_to_raise or increases cash pool
            
    # 3b. Speculative basket concentration limits
    total_spec_weight = drift_analysis["speculative_percent"]
    if total_spec_weight > policy.max_speculative_weight and speculative:
        spec_excess_weight = total_spec_weight - policy.max_speculative_weight
        spec_excess_val = total_val * (spec_excess_weight / 100.0)
        
        # Trim speculative positions pro-rata
        total_spec_val = sum(p.market_value for p in speculative) or 1.0
        for pos in speculative:
            # Check if this speculative stock wasn't already trimmed above
            existing_trade = next((t for t in proposed_trades if t.symbol == pos.symbol), None)
            if existing_trade:
                continue
                
            share = pos.market_value / total_spec_val
            trim_val = spec_excess_val * share
            qty = trim_val / max(pos.market_price, 0.01)
            
            target_weight = max(0.0, pos.portfolio_weight - (trim_val / total_val * 100))
            proposed_trades.append(
                RebalanceProposalItem(
                    symbol=pos.symbol,
                    current_weight=round(pos.portfolio_weight, 2),
                    target_weight=round(target_weight, 2),
                    current_value=round(pos.market_value, 2),
                    proposed_trade_value=round(-trim_val, 2),
                    proposed_trade_qty=round(-qty, 2),
                    action="Sell",
                    reason=f"Trim speculative exposure to stay under default {policy.max_speculative_weight}% spec limit."
                )
            )
            cash_to_raise -= trim_val

    # 4. Handle asset class drift
    # If equities is overall underweight (and we have excess cash), we buy benchmark ETFs
    equity_drift_pct = drifts["equity"]["drift"]
    if equity_drift_pct < -policy.rebalancing_drift_threshold and current_cash > cash_floor:
        # Underweight equity, buy benchmark ETF
        cash_pool = current_cash - cash_floor
        buy_val = min(cash_pool, abs(total_val * (equity_drift_pct / 100.0)))
        
        benchmark_symbol = policy.benchmark or "SPY"
        # See if we already hold it
        existing_pos = next((p for p in positions if p.symbol == benchmark_symbol), None)
        curr_w = existing_pos.portfolio_weight if existing_pos else 0.0
        curr_v = existing_pos.market_value if existing_pos else 0.0
        price = existing_pos.market_price if existing_pos else 500.0 # fallback price
        
        qty = buy_val / price
        target_w = curr_w + (buy_val / total_val * 100)
        
        proposed_trades.append(
            RebalanceProposalItem(
                symbol=benchmark_symbol,
                current_weight=round(curr_w, 2),
                target_weight=round(target_w, 2),
                current_value=round(curr_v, 2),
                proposed_trade_value=round(buy_val, 2),
                proposed_trade_qty=round(qty, 2),
                action="Buy",
                reason=f"Buy benchmark ETF {benchmark_symbol} to correct equity underweight drift ({equity_drift_pct:.2f}%)."
            )
        )
        cash_to_raise += buy_val

    # If equities is overall overweight, and we need to raise cash, trim ETFs or single stocks pro-rata
    if (equity_drift_pct > policy.rebalancing_drift_threshold or cash_to_raise > 0) and positions:
        # Filter proposed sells so far to count how much cash we already raised
        cash_raised_so_far = sum(abs(t.proposed_trade_value) for t in proposed_trades if t.action == "Sell")
        still_needed = max(0.0, cash_to_raise - cash_raised_so_far)
        
        if still_needed > 0:
            # Sell benchmark ETFs or largest holdings to raise cash
            sellable_etfs = [p for p in etfs if not next((t for t in proposed_trades if t.symbol == p.symbol), None)]
            if sellable_etfs:
                # Sell from ETFs first to preserve single names
                total_etf_mv = sum(p.market_value for p in sellable_etfs) or 1.0
                for pos in sellable_etfs:
                    share = pos.market_value / total_etf_mv
                    trim_val = min(pos.market_value * 0.5, still_needed * share)
                    qty = trim_val / max(pos.market_price, 0.01)
                    target_w = max(0.0, pos.portfolio_weight - (trim_val / total_val * 100))
                    proposed_trades.append(
                        RebalanceProposalItem(
                            symbol=pos.symbol,
                            current_weight=round(pos.portfolio_weight, 2),
                            target_weight=round(target_w, 2),
                            current_value=round(pos.market_value, 2),
                            proposed_trade_value=round(-trim_val, 2),
                            proposed_trade_qty=round(-qty, 2),
                            action="Sell",
                            reason=f"Trim ETF holding to raise required cash buffer."
                        )
                    )
            else:
                # Trimming core holdings if no ETFs are available
                sellable_core = [p for p in single_stocks if not p.is_speculative and not next((t for t in proposed_trades if t.symbol == p.symbol), None)]
                if sellable_core:
                    total_core_mv = sum(p.market_value for p in sellable_core) or 1.0
                    for pos in sellable_core:
                        share = pos.market_value / total_core_mv
                        trim_val = min(pos.market_value * 0.2, still_needed * share)
                        qty = trim_val / max(pos.market_price, 0.01)
                        target_w = max(0.0, pos.portfolio_weight - (trim_val / total_val * 100))
                        proposed_trades.append(
                            RebalanceProposalItem(
                                symbol=pos.symbol,
                                current_weight=round(pos.portfolio_weight, 2),
                                target_weight=round(target_w, 2),
                                current_value=round(pos.market_value, 2),
                                proposed_trade_value=round(-trim_val, 2),
                                proposed_trade_qty=round(-qty, 2),
                                action="Sell",
                                reason=f"Trim core holding pro-rata to raise cash floor."
                            )
                        )

    # 5. Apply Transaction Cost Rule: Filter out proposed trades under $100
    proposed_trades = [t for t in proposed_trades if abs(t.proposed_trade_value) >= 100.0]
    
    # 6. Calculate net cash impact of proposed trades
    net_cash_impact = sum(
        -t.proposed_trade_value if t.action == "Buy" else abs(t.proposed_trade_value)
        for t in proposed_trades
    )
    
    # 7. Apply Tax-Aware logic
    tax_warning = ""
    if profile.account_type in ("Taxable", "Margin"):
        sells = [t.symbol for t in proposed_trades if t.action == "Sell"]
        if sells:
            tax_warning = (
                f"WARNING: Account type is {profile.account_type}. Proposed sales of "
                f"{', '.join(sells)} may trigger immediate realized capital gains. "
                "Consider utilizing tax-loss harvesting or executing adjustments in "
                "tax-advantaged accounts (TFSA/RRSP) to optimize tax outcomes."
            )
        else:
            tax_warning = "Account is taxable, but proposed adjustments do not trigger immediate sales."
    else:
        tax_warning = (
            f"Tax-free status confirmed: Account type is {profile.account_type} (TFSA/RRSP/Roth equivalent). "
            "Trades can be executed without immediate tax liabilities."
        )
        
    return RebalanceProposal(
        proposed_trades=proposed_trades,
        cash_impact=round(net_cash_impact, 2),
        tax_impact_warning=tax_warning
    )
