from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.domain import FundamentalSnapshot
from app.services.valuation.models.bank_residual_income import BankResidualIncomeInputs, evaluate_bank_residual_income
from app.services.valuation.models.base import ValuationOutput, ValuationScenario
from app.services.valuation.models.dcf import DcfInputs, evaluate_dcf
from app.services.valuation.models.reit_nav_affo import ReitNavAffoInputs, evaluate_reit_nav_affo
from app.services.valuation.models.utility_rate_base import UtilityRateBaseInputs, evaluate_utility_rate_base


class ScenarioValuationResult(BaseModel):
    symbol: str
    company_type: str
    valuation_status: str = "unavailable"
    fair_value_low: float | None = None
    fair_value_mid: float | None = None
    fair_value_high: float | None = None
    methodology: str
    assumptions: dict[str, float | str] = Field(default_factory=dict)
    data_quality: dict[str, str] = Field(default_factory=dict)
    unavailable_reasons: list[str] = Field(default_factory=list)


def _company_type_from_sector(sector: str, stock_type: str) -> str:
    if stock_type == "reit_heuristic" or sector == "Real Estate":
        return "reit"
    if stock_type == "financials_heuristic" or sector == "Financials":
        return "bank"
    if stock_type == "utilities_heuristic" or sector == "Utilities":
        return "utility"
    return "general_operating"


def _default_scenarios() -> list[ValuationScenario]:
    return [
        ValuationScenario(name="base", assumptions={}),
        ValuationScenario(name="bull", assumptions={}),
        ValuationScenario(name="bear", assumptions={}),
    ]


def _decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _evaluate_model(
    snapshot: FundamentalSnapshot,
    company_type: str,
    *,
    market_price: float | None,
) -> ValuationOutput:
    source_ids = [snapshot.source]
    as_of = snapshot.report_date
    currency = "USD"
    scenarios = _default_scenarios()

    if company_type == "bank":
        return evaluate_bank_residual_income(
            BankResidualIncomeInputs(
                tangible_common_equity=None,
                tangible_book_per_share=_decimal_or_none(snapshot.price_to_tangible_book),
                normalized_roe=_decimal_or_none(snapshot.return_on_equity),
                cost_of_equity=None,
                retention_ratio=None,
                share_count=None,
                currency=currency,
                as_of=as_of,
                source_ids=source_ids,
            ),
            scenarios,
        )
    if company_type == "reit":
        return evaluate_reit_nav_affo(
            ReitNavAffoInputs(
                affo_per_share=_decimal_or_none(snapshot.affo_per_share),
                ffo_per_share=_decimal_or_none(snapshot.ffo_per_share),
                net_debt=_decimal_or_none(snapshot.total_debt),
                share_count=None,
                justified_affo_multiple=None,
                currency=currency,
                as_of=as_of,
                source_ids=source_ids,
            ),
            scenarios,
        )
    if company_type == "utility":
        return evaluate_utility_rate_base(
            UtilityRateBaseInputs(
                rate_base=None,
                allowed_roe=_decimal_or_none(snapshot.allowed_roe),
                equity_capitalization=None,
                capex=None,
                debt_financing=None,
                share_count=None,
                currency=currency,
                as_of=as_of,
                source_ids=source_ids,
            ),
            scenarios,
        )

    return evaluate_dcf(
        DcfInputs(
            ttm_revenue=None,
            operating_margin=_decimal_or_none(snapshot.operating_margin),
            tax_rate=None,
            depreciation_amortization=None,
            capex=None,
            working_capital_change=None,
            net_debt=_decimal_or_none(snapshot.total_debt),
            diluted_share_count=None,
            wacc=Decimal("0.10"),
            terminal_growth=Decimal("0.03"),
            currency=currency,
            as_of=as_of,
            source_ids=source_ids,
        ),
        scenarios,
    )


def _output_to_result(
    snapshot: FundamentalSnapshot,
    company_type: str,
    output: ValuationOutput,
    *,
    market_price: float | None,
) -> ScenarioValuationResult:
    if output.status == "available" and output.per_share_value is not None:
        per_share = float(output.per_share_value)
        return ScenarioValuationResult(
            symbol=snapshot.symbol,
            company_type=company_type,
            valuation_status="available",
            fair_value_low=round(per_share * 0.9, 2),
            fair_value_mid=round(per_share, 2),
            fair_value_high=round(per_share * 1.1, 2),
            methodology=f"Validated {company_type} valuation model.",
            assumptions={
                "report_date": snapshot.report_date.isoformat(),
                "source": snapshot.source,
                "market_price": round(market_price, 4) if market_price is not None else "",
            },
            data_quality={"inputs": snapshot.source, "scenario_date": date.today().isoformat()},
            unavailable_reasons=[],
        )

    reasons = list(output.exclusions) or [f"{company_type}_valuation_model_not_validated"]
    return ScenarioValuationResult(
        symbol=snapshot.symbol,
        company_type=company_type,
        valuation_status="unavailable",
        methodology=(
            "Fair value is withheld because a validated, unit-consistent "
            f"{company_type} valuation model is not yet available."
        ),
        assumptions={
            "report_date": snapshot.report_date.isoformat(),
            "source": snapshot.source,
            "market_price": round(market_price, 4) if market_price is not None else "",
        },
        data_quality={"inputs": snapshot.source},
        unavailable_reasons=reasons,
    )


def run_scenario_valuation(
    snapshot: FundamentalSnapshot,
    *,
    sector: str = "Unknown",
    stock_type: str = "universal",
    market_price: float | None = None,
) -> ScenarioValuationResult:
    company_type = _company_type_from_sector(sector, stock_type)
    if market_price is None or market_price <= 0:
        return ScenarioValuationResult(
            symbol=snapshot.symbol,
            company_type=company_type,
            valuation_status="unavailable",
            methodology=(
                "Fair value is withheld because a validated, unit-consistent "
                f"{company_type} valuation model is not yet available."
            ),
            assumptions={
                "report_date": snapshot.report_date.isoformat(),
                "source": snapshot.source,
            },
            data_quality={"inputs": snapshot.source},
            unavailable_reasons=["market_price_unavailable", f"{company_type}_valuation_model_not_validated"],
        )

    output = _evaluate_model(snapshot, company_type, market_price=market_price)
    return _output_to_result(snapshot, company_type, output, market_price=market_price)
