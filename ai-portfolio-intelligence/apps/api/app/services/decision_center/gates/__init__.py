"""Ordered Decision Center gates."""

from app.services.decision_center.gates.data_quality import DataQualityGate
from app.services.decision_center.gates.remaining import (
    FundamentalQualityGate,
    ImplementationGate,
    LiquidityGate,
    MethodologyGate,
    PortfolioFitGate,
    TaxGate,
    ValuationGate,
)
from app.services.decision_center.gates.source_integrity import SourceIntegrityGate
from app.services.decision_center.gates.suitability import RiskPolicyGate, SuitabilityGate, ThesisGate


def default_gates():
    return [
        SourceIntegrityGate(),
        DataQualityGate(),
        SuitabilityGate(),
        ThesisGate(),
        RiskPolicyGate(),
        FundamentalQualityGate(),
        ValuationGate(),
        PortfolioFitGate(),
        TaxGate(),
        LiquidityGate(),
        MethodologyGate(),
        ImplementationGate(),
    ]


__all__ = [
    "DataQualityGate",
    "FundamentalQualityGate",
    "ImplementationGate",
    "LiquidityGate",
    "MethodologyGate",
    "PortfolioFitGate",
    "RiskPolicyGate",
    "SourceIntegrityGate",
    "SuitabilityGate",
    "TaxGate",
    "ThesisGate",
    "ValuationGate",
    "default_gates",
]
