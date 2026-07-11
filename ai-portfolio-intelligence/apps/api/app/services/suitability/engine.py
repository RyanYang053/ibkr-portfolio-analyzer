import json
import os

from app.schemas.domain import InvestorProfile, Position, Recommendation
from app.services.tenant_scope import auth_scoped_defaults_enabled

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
PROFILE_FILE = os.path.join(DATA_DIR, "investor_profile.json")

DEFAULT_PROFILE = {
    "objective": "Growth",
    "time_horizon_years": 10,
    "risk_tolerance": "High",
    "risk_capacity": "Medium",
    "liquidity_needs": 10000.0,
    "net_worth_range": "100k-500k",
    "tax_residency": "Canada",
    "account_type": "Tax-Free",
    "restrictions": []
}


def get_investor_profile(account_id: str, *, user_id: str) -> InvestorProfile:
    """Load the investor profile for a tenant/account scope."""
    from app.db.legacy_bridge import read_json_with_legacy, write_json_state

    record_key = f"{user_id}:{account_id}"
    profile_path = os.path.join(DATA_DIR, f"investor_profile_{record_key.replace(':', '_')}.json")
    data = read_json_with_legacy(
        "investor_profile",
        record_key,
        profile_path if os.path.exists(profile_path) else None,
        default=None,
    )
    if data is None:
        if auth_scoped_defaults_enabled():
            return InvestorProfile(**DEFAULT_PROFILE)
        write_json_state("investor_profile", record_key, DEFAULT_PROFILE)
        return InvestorProfile(**DEFAULT_PROFILE)

    try:
        return InvestorProfile(**data)
    except Exception:
        return InvestorProfile(**DEFAULT_PROFILE)


def save_investor_profile(profile: InvestorProfile, account_id: str, *, user_id: str) -> None:
    """Save the investor profile for a tenant/account scope."""
    from app.db.legacy_bridge import write_json_state

    record_key = f"{user_id}:{account_id}"
    write_json_state("investor_profile", record_key, profile.model_dump())
    os.makedirs(DATA_DIR, exist_ok=True)
    profile_path = os.path.join(DATA_DIR, f"investor_profile_{record_key.replace(':', '_')}.json")
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile.model_dump(), f, indent=2)


def check_position_suitability(profile: InvestorProfile, position: Position) -> list[str]:
    """Verify if a holding is suitable based on the investor profile."""
    warnings = []

    # 1. Speculative assets vs. risk profile
    if position.is_speculative:
        if profile.risk_tolerance == "Low":
            warnings.append(
                f"Speculative asset {position.symbol} is unsuitable for Low Risk Tolerance."
            )
        if profile.risk_capacity == "Low":
            warnings.append(
                f"Speculative asset {position.symbol} is high risk for Low Risk Capacity."
            )
        if profile.objective == "Capital Preservation":
            warnings.append(
                f"Speculative asset {position.symbol} is unsuitable for Capital Preservation objective."
            )

    # 2. Speculative position concentration
    if position.is_speculative and position.portfolio_weight > 3.0:
        warnings.append(
            f"Speculative position {position.symbol} has excessive concentration ({position.portfolio_weight:.2f}% vs. max 3.0% limit)."
        )

    # 3. Restrictions check
    if position.symbol in profile.restrictions:
        warnings.append(f"Position {position.symbol} violates explicit investment restriction list.")

    # 4. Cash limits and time horizon
    if profile.time_horizon_years < 3 and position.is_speculative:
        warnings.append(
            f"Speculative asset {position.symbol} is unsuitable for short time horizon (< 3 years)."
        )

    return warnings


def check_recommendation_suitability(profile: InvestorProfile, rec: Recommendation) -> list[str]:
    """Verify if a recommendation aligns with suitability policy."""
    warnings = []
    
    if rec.action in ("Strong Add", "Add"):
        # Check if the symbol is in restrictions
        if rec.symbol in profile.restrictions:
            warnings.append(f"Adding {rec.symbol} violates explicit investment restriction list.")
        
        # Low risk profile filter
        if profile.risk_tolerance == "Low" and rec.score < 50:
            warnings.append(f"Adding lower-scored asset {rec.symbol} is unsuitable for low risk tolerance.")
            
    return warnings
