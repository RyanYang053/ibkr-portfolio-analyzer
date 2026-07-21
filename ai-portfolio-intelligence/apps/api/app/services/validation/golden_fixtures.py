"""Golden fixture runners for valuation methodology validation."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.services.valuation.models.bank_residual_income import (
    BankResidualIncomeInputs,
    evaluate_bank_residual_income,
)
from app.services.valuation.models.base import ValuationScenario
from app.services.valuation.models.dcf import DcfInputs, evaluate_dcf
from app.services.valuation.models.reit_nav_affo import ReitNavAffoInputs, evaluate_reit_nav_affo
from app.services.valuation.models.utility_rate_base import (
    UtilityRateBaseInputs,
    evaluate_utility_rate_base,
)

_API_ROOT = Path(__file__).resolve().parents[3]
_VALUATION_FIXTURE_DIR = _API_ROOT / "tests" / "fixtures" / "valuation"

VALUATION_MODEL_IDS: tuple[str, ...] = (
    "general_operating_dcf",
    "bank_residual_income",
    "reit_nav_affo",
    "utility_rate_base",
)


def _fixture_path(model_id: str) -> Path:
    return _VALUATION_FIXTURE_DIR / f"{model_id}.json"


def load_fixture(path: str | Path) -> dict[str, Any]:
    fixture_path = Path(path)
    if not fixture_path.is_absolute():
        fixture_path = _API_ROOT / fixture_path
    with fixture_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Fixture must be a JSON object: {fixture_path}")
    return payload


def fixture_sha256(path: str | Path) -> str:
    fixture_path = Path(path)
    if not fixture_path.is_absolute():
        fixture_path = _API_ROOT / fixture_path
    digest = hashlib.sha256()
    digest.update(fixture_path.read_bytes())
    return digest.hexdigest()


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _scenarios(raw: list[dict[str, Any]]) -> list[ValuationScenario]:
    scenarios: list[ValuationScenario] = []
    for item in raw:
        assumptions = {
            str(key): Decimal(str(val))
            for key, val in dict(item.get("assumptions") or {}).items()
        }
        scenarios.append(ValuationScenario(name=str(item["name"]), assumptions=assumptions))
    return scenarios


def _within_tol(actual: float, expected: float, *, tol_rel: float, tol_abs: float = 0.0) -> bool:
    if tol_abs > 0 and abs(actual - expected) <= tol_abs:
        return True
    if expected == 0:
        return abs(actual) <= tol_rel
    return abs(actual - expected) / abs(expected) <= tol_rel


def _run_model(model_id: str, fixture: dict[str, Any]) -> float:
    inputs = dict(fixture.get("inputs") or {})
    scenarios = _scenarios(list(fixture.get("scenarios") or []))

    if model_id == "general_operating_dcf":
        output = evaluate_dcf(
            DcfInputs(
                ttm_revenue=_as_decimal(inputs.get("ttm_revenue")),
                operating_margin=_as_decimal(inputs.get("operating_margin")),
                tax_rate=_as_decimal(inputs.get("tax_rate")),
                depreciation_amortization=_as_decimal(inputs.get("depreciation_amortization")),
                capex=_as_decimal(inputs.get("capex")),
                working_capital_change=_as_decimal(inputs.get("working_capital_change")),
                net_debt=_as_decimal(inputs.get("net_debt")),
                diluted_share_count=_as_decimal(inputs.get("diluted_share_count")),
                wacc=_as_decimal(inputs.get("wacc")) or Decimal("0"),
                terminal_growth=_as_decimal(inputs.get("terminal_growth")) or Decimal("0"),
                currency=str(inputs.get("currency") or "USD"),
                as_of=_as_date(inputs.get("as_of")),
                source_ids=list(inputs.get("source_ids") or ["golden_fixture"]),
            ),
            scenarios,
        )
    elif model_id == "bank_residual_income":
        output = evaluate_bank_residual_income(
            BankResidualIncomeInputs(
                tangible_common_equity=_as_decimal(inputs.get("tangible_common_equity")),
                tangible_book_per_share=_as_decimal(inputs.get("tangible_book_per_share")),
                normalized_roe=_as_decimal(inputs.get("normalized_roe")),
                cost_of_equity=_as_decimal(inputs.get("cost_of_equity")),
                retention_ratio=_as_decimal(inputs.get("retention_ratio")),
                share_count=_as_decimal(inputs.get("share_count")),
                currency=str(inputs.get("currency") or "USD"),
                as_of=_as_date(inputs.get("as_of")),
                source_ids=list(inputs.get("source_ids") or ["golden_fixture"]),
                forecast_horizon=int(inputs.get("forecast_horizon") or 5),
                terminal_growth=_as_decimal(inputs.get("terminal_growth")) or Decimal("0.03"),
            ),
            scenarios,
        )
    elif model_id == "reit_nav_affo":
        output = evaluate_reit_nav_affo(
            ReitNavAffoInputs(
                property_noi=_as_decimal(inputs.get("property_noi")),
                cap_rate=_as_decimal(inputs.get("cap_rate")),
                net_debt=_as_decimal(inputs.get("net_debt")),
                preferred_equity=_as_decimal(inputs.get("preferred_equity")),
                share_count=_as_decimal(inputs.get("share_count")),
                affo_per_share=_as_decimal(inputs.get("affo_per_share")),
                justified_affo_multiple=_as_decimal(inputs.get("justified_affo_multiple")),
                currency=str(inputs.get("currency") or "USD"),
                as_of=_as_date(inputs.get("as_of")),
                source_ids=list(inputs.get("source_ids") or ["golden_fixture"]),
            ),
            scenarios,
        )
    elif model_id == "utility_rate_base":
        output = evaluate_utility_rate_base(
            UtilityRateBaseInputs(
                rate_base=_as_decimal(inputs.get("rate_base")),
                allowed_roe=_as_decimal(inputs.get("allowed_roe")),
                equity_capitalization=_as_decimal(inputs.get("equity_capitalization")),
                regulatory_lag_years=_as_decimal(inputs.get("regulatory_lag_years")),
                capex=_as_decimal(inputs.get("capex")),
                debt_financing=_as_decimal(inputs.get("debt_financing")),
                debt_cost=_as_decimal(inputs.get("debt_cost")),
                payout_ratio=_as_decimal(inputs.get("payout_ratio")),
                share_count=_as_decimal(inputs.get("share_count")),
                currency=str(inputs.get("currency") or "USD"),
                as_of=_as_date(inputs.get("as_of")),
                source_ids=list(inputs.get("source_ids") or ["golden_fixture"]),
            ),
            scenarios,
        )
    else:
        raise ValueError(f"Unsupported valuation model_id: {model_id}")

    if output.status != "available" or output.per_share_value is None:
        raise RuntimeError(
            f"{model_id} golden run withheld: {output.exclusions}"
        )
    base = next((item for item in output.scenarios if item.name == "base"), None)
    if base is not None:
        return float(base.per_share_value)
    return float(output.per_share_value)


def run_valuation_golden(model_id: str) -> dict[str, Any]:
    path = _fixture_path(model_id)
    fixture = load_fixture(path)
    artifact = fixture_sha256(path)
    expected_block = dict(fixture.get("expected") or {})
    expected = float(
        expected_block.get("base_per_share", expected_block.get("per_share", 0.0))
    )
    tol_rel = float(expected_block.get("tol_rel", 0.02))
    tol_abs = float(expected_block.get("tol_abs", 0.0))
    actual = _run_model(model_id, fixture)
    ok = _within_tol(actual, expected, tol_rel=tol_rel, tol_abs=tol_abs)
    return {
        "ok": ok,
        "model_id": model_id,
        "expected": expected,
        "actual": actual,
        "tol_rel": tol_rel,
        "artifact_sha256": artifact,
        "fixture_path": str(path.relative_to(_API_ROOT)),
    }


def run_all_valuation_goldens() -> list[dict[str, Any]]:
    return [run_valuation_golden(model_id) for model_id in VALUATION_MODEL_IDS]


def promote_personal_use_after_goldens(methodology_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Promote methodologies to approved_for_personal_use after golden fixtures pass."""
    from app.services.validation.methodology_validation import record_approval

    ids = list(methodology_ids or VALUATION_MODEL_IDS)
    results: list[dict[str, Any]] = []
    for methodology_id in ids:
        golden = run_valuation_golden(methodology_id)
        if not golden["ok"]:
            results.append({**golden, "promoted": False, "reason": "golden_failed"})
            continue
        approval = record_approval(
            methodology_id=methodology_id,
            version="1.0.0",
            approver="golden_fixtures",
            notes=f"Promoted after golden fixture sha256={golden['artifact_sha256']}",
        )
        results.append({**golden, "promoted": True, "approval": approval})
    return results
