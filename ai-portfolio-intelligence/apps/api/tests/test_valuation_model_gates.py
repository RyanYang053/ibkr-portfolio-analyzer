from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.schemas.domain import FundamentalSnapshot
from app.services.valuation.models.bank_residual_income import BankResidualIncomeInputs, evaluate_bank_residual_income
from app.services.valuation.models.base import ValuationScenario
from app.services.valuation.models.dcf import DcfInputs, evaluate_dcf
from app.services.valuation.models.reit_nav_affo import ReitNavAffoInputs, evaluate_reit_nav_affo
from app.services.valuation.models.utility_rate_base import UtilityRateBaseInputs, evaluate_utility_rate_base
from app.services.valuation.scenario_valuation import run_scenario_valuation


def _snapshot(**overrides) -> FundamentalSnapshot:
    payload = dict(
        symbol="TEST",
        period="TTM",
        report_date=date(2025, 12, 31),
        revenue_growth_yoy=0.08,
        gross_margin=0.45,
        operating_margin=0.22,
        free_cash_flow=1_000_000.0,
        cash=5_000_000.0,
        total_debt=2_000_000.0,
        pe_forward=20.0,
        ev_sales=4.0,
        fcf_yield=0.05,
        source="test",
    )
    payload.update(overrides)
    return FundamentalSnapshot(**payload)


def _scenarios() -> list[ValuationScenario]:
    return [
        ValuationScenario(name="base", assumptions={"terminal_growth": Decimal("0.03")}),
        ValuationScenario(name="bull", assumptions={"terminal_growth": Decimal("0.04")}),
        ValuationScenario(name="bear", assumptions={"terminal_growth": Decimal("0.02")}),
    ]


def test_run_scenario_valuation_withholds_until_models_validated():
    result = run_scenario_valuation(
        _snapshot(symbol="MSFT"),
        sector="Technology",
        stock_type="mega_cap_quality",
        market_price=400.0,
    )
    assert result.valuation_status == "unavailable"
    assert result.fair_value_mid is None
    assert result.unavailable_reasons


def test_run_scenario_valuation_withholds_for_each_company_type():
    bank = run_scenario_valuation(
        _snapshot(symbol="JPM", price_to_tangible_book=1.2, return_on_equity=0.14),
        sector="Financials",
        stock_type="financials_heuristic",
        market_price=150.0,
    )
    assert bank.company_type == "bank"
    assert bank.valuation_status == "unavailable"
    assert bank.unavailable_reasons

    reit = run_scenario_valuation(
        _snapshot(symbol="O", affo_per_share=3.6),
        sector="Real Estate",
        stock_type="reit_heuristic",
        market_price=60.0,
    )
    assert reit.company_type == "reit"
    assert reit.unavailable_reasons


def test_dcf_model_requires_core_inputs():
    output = evaluate_dcf(
        DcfInputs(
            ttm_revenue=Decimal("1000000000"),
            operating_margin=Decimal("0.20"),
            tax_rate=Decimal("0.21"),
            depreciation_amortization=Decimal("50000000"),
            capex=Decimal("40000000"),
            working_capital_change=Decimal("10000000"),
            net_debt=Decimal("200000000"),
            diluted_share_count=Decimal("100000000"),
            wacc=Decimal("0.10"),
            terminal_growth=Decimal("0.03"),
            currency="USD",
            as_of=date(2025, 12, 31),
            source_ids=["sec_edgar_companyfacts"],
        ),
        _scenarios(),
    )
    assert output.status == "withheld"
    assert "general_operating_valuation_model_not_validated" in output.exclusions


def test_dcf_model_rejects_wacc_below_terminal_growth():
    output = evaluate_dcf(
        DcfInputs(
            ttm_revenue=Decimal("1000000000"),
            operating_margin=Decimal("0.20"),
            tax_rate=Decimal("0.21"),
            depreciation_amortization=Decimal("50000000"),
            capex=Decimal("40000000"),
            working_capital_change=Decimal("10000000"),
            net_debt=Decimal("200000000"),
            diluted_share_count=Decimal("100000000"),
            wacc=Decimal("0.02"),
            terminal_growth=Decimal("0.03"),
            currency="USD",
            as_of=date(2025, 12, 31),
            source_ids=["sec_edgar_companyfacts"],
        ),
        _scenarios(),
    )
    assert "wacc_must_exceed_terminal_growth" in output.exclusions


def test_bank_model_withholds_without_validated_reference():
    output = evaluate_bank_residual_income(
        BankResidualIncomeInputs(
            tangible_common_equity=Decimal("1000000000"),
            tangible_book_per_share=Decimal("80"),
            normalized_roe=Decimal("0.12"),
            cost_of_equity=Decimal("0.10"),
            retention_ratio=Decimal("0.60"),
            share_count=Decimal("100000000"),
            currency="USD",
            as_of=date(2025, 12, 31),
            source_ids=["sec_edgar_companyfacts"],
        ),
        _scenarios(),
    )
    assert output.status == "withheld"
    assert "bank_valuation_model_not_validated" in output.exclusions


def test_reit_model_flags_missing_affo_inputs():
    output = evaluate_reit_nav_affo(
        ReitNavAffoInputs(
            property_noi=None,
            cap_rate=None,
            net_debt=Decimal("1000000000"),
            preferred_equity=None,
            share_count=Decimal("500000000"),
            affo_per_share=None,
            justified_affo_multiple=Decimal("15"),
            currency="USD",
            as_of=date(2025, 12, 31),
            source_ids=["sec_edgar_companyfacts"],
        ),
        _scenarios(),
    )
    assert "affo_or_ffo_per_share_unavailable" in output.exclusions


def test_utility_model_withholds_without_rate_base():
    output = evaluate_utility_rate_base(
        UtilityRateBaseInputs(
            rate_base=None,
            allowed_roe=Decimal("0.095"),
            equity_capitalization=Decimal("0.55"),
            regulatory_lag_years=None,
            capex=Decimal("500000000"),
            debt_financing=Decimal("300000000"),
            debt_cost=None,
            payout_ratio=None,
            share_count=Decimal("200000000"),
            currency="USD",
            as_of=date(2025, 12, 31),
            source_ids=["sec_edgar_companyfacts"],
        ),
        _scenarios(),
    )
    assert "rate_base_unavailable" in output.exclusions
