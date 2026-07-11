from typing import Any

from app.schemas.domain import DISCLAIMER

# SEC/FINRA Compliance standard robo-advisory disclosure text
ROBO_DISCLOSURE = (
    "Disclaimer: This system provides algorithmic, read-only decision support for portfolio analysis. "
    "All outputs, scores, and rebalancing suggestions are generated deterministically based on default "
    "or user-defined settings and do not constitute personalized financial, tax, or investment advice. "
    "The system does not possess order-entry or execution capabilities. Users must independently review, "
    "verify, and confirm suitability of all suggestions before making actual transactions in a broker account."
)


def apply_recommendation_guardrails(
    action: str,
    symbol: str,
    suitability_warnings: list[str]
) -> tuple[str, str]:
    """Screen the proposed action against suitability warnings.
    
    If warnings exist, override actions to review zones.
    """
    symbol_warnings = [w for w in suitability_warnings if symbol in w]
    
    if symbol_warnings:
        # If there's a serious violation, restrict buying or adding
        if action in ("Strong Add", "Add"):
            override_action = "Exit Review" if "unsuitable" in "".join(symbol_warnings).lower() else "Trim Review"
            reason = f"Override: Action adjusted to {override_action} due to suitability warnings: {'; '.join(symbol_warnings)}"
            return override_action, reason
            
    return action, ""


def append_compliance_disclaimer(content: dict[str, Any]) -> dict[str, Any]:
    """Inject disclosures and ensure no execution-capable text exists in AI output."""
    content["disclaimer"] = DISCLAIMER
    content["robo_advisor_disclosure"] = ROBO_DISCLOSURE
    content["human_review_required"] = True
    
    restricted_phrases = ["order submitted", "trade executed", "broker will buy", "broker will sell"]
    return _sanitize_nested(content, restricted_phrases)


def _sanitize_nested(value: Any, restricted_phrases: list[str]) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_nested(item, restricted_phrases) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_nested(item, restricted_phrases) for item in value]
    if not isinstance(value, str):
        return value

    sanitized = value
    for phrase in restricted_phrases:
        start = sanitized.lower().find(phrase)
        while start >= 0:
            sanitized = sanitized[:start] + "decision-support review" + sanitized[start + len(phrase):]
            start = sanitized.lower().find(phrase)
    return sanitized
