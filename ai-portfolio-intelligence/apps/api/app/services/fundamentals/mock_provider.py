from __future__ import annotations

import sys

from app.core.config import settings
from app.schemas.domain import FundamentalSnapshot, recent_mock_date
from app.services.fundamentals.providers.yahoo_enrichment import enrich_sector_fields, resolve_sector_from_yahoo


class MockFundamentalProvider:
    def __init__(self, allow_mock: bool | None = None) -> None:
        self.allow_mock = (
            allow_mock
            if allow_mock is not None
            else settings.broker_mode == "mock_ibkr_readonly" or "pytest" in sys.modules
        )

    def get_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        is_speculative = symbol.upper() in {"IONQ", "LAES", "INFQ"}

        if self.allow_mock:
            return self._mock_fundamentals(symbol, is_speculative)

        from app.services.broker.securities import classify_security
        sec_info = classify_security(symbol)
        is_etf = sec_info.get("is_etf", False) or sec_info.get("asset_class", "") == "ETF"

        import httpx
        client = httpx.Client(headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        try:
            # Fetch Yahoo Finance cookies and crumbs
            client.get("https://fc.yahoo.com", timeout=3.0)
            crumb_resp = client.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=3.0)
            if crumb_resp.status_code == 200:
                crumb = crumb_resp.text.strip()
                url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol.upper()}?crumb={crumb}&modules=defaultKeyStatistics,financialData,secFilings,assetProfile,summaryProfile"
                resp = client.get(url, timeout=5.0)
                if resp.status_code == 200:
                    res = resp.json()["quoteSummary"]["result"][0]
                    findata = res.get("financialData", {}) or {}
                    stats = res.get("defaultKeyStatistics", {}) or {}
                    asset_profile = res.get("assetProfile", {}) or {}
                    summary_profile = res.get("summaryProfile", {}) or {}
                    sector = resolve_sector_from_yahoo(
                        sec_info.get("sector", "Unknown"),
                        asset_profile=asset_profile,
                        summary_profile=summary_profile,
                    )

                    if is_etf:
                        total_assets = stats.get("totalAssets", {}).get("raw", 0.0)
                        from datetime import date
                        return FundamentalSnapshot(
                            symbol=symbol.upper(),
                            period="TTM",
                            report_date=date.today(),
                            revenue_growth_yoy=0.0,
                            gross_margin=0.0,
                            operating_margin=0.0,
                            free_cash_flow=0.0,
                            cash=float(total_assets) if total_assets is not None else 0.0,
                            total_debt=0.0,
                            pe_forward=None,
                            ev_sales=None,
                            fcf_yield=None,
                            source="live_yahoo_finance_etf",
                        )

                    revenue_growth = findata.get("revenueGrowth", {}).get("raw")
                    gross_margin = findata.get("grossMargins", {}).get("raw")
                    operating_margin = findata.get("operatingMargins", {}).get("raw")
                    fcf = findata.get("freeCashflow", {}).get("raw")

                    cash = findata.get("totalCash", {}).get("raw")
                    total_debt = findata.get("totalDebt", {}).get("raw")

                    pe_forward = stats.get("forwardPE", {}).get("raw")
                    ev_sales = stats.get("enterpriseToRevenue", {}).get("raw")
                    most_recent_quarter = stats.get("mostRecentQuarter", {}).get("raw")
                    from datetime import date as date_type
                    from datetime import datetime, timezone

                    filing_date = None
                    sec_filings = res.get("secFilings", {}) or {}
                    filings = sec_filings.get("filings", []) if isinstance(sec_filings, dict) else []
                    for filing in filings:
                        filing_type = str(filing.get("type") or "")
                        if filing_type not in {"10-Q", "10-K"}:
                            continue
                        filed_on = filing.get("date")
                        if filed_on is None:
                            continue
                        if isinstance(filed_on, str):
                            candidate = date_type.fromisoformat(filed_on[:10])
                        else:
                            candidate = datetime.fromtimestamp(float(filed_on), tz=timezone.utc).date()
                        if filing_date is None or candidate > filing_date:
                            filing_date = candidate

                    # Compute FCF yield
                    fcf_yield = None
                    shares = stats.get("sharesOutstanding", {}).get("raw")
                    price = findata.get("currentPrice", {}).get("raw")
                    if fcf and shares and price:
                        mcap = shares * price
                        if mcap > 0:
                            fcf_yield = fcf / mcap
                    required = [revenue_growth, gross_margin, operating_margin, fcf, cash, total_debt, most_recent_quarter]
                    if any(value is None for value in required):
                        raise RuntimeError(f"Live fundamental data incomplete for {symbol.upper()}")

                    report_date = datetime.fromtimestamp(float(most_recent_quarter), tz=timezone.utc).date()
                    observed_at = datetime.now(timezone.utc)
                    as_of_date = observed_at.date()

                    from app.schemas.domain import FundamentalSnapshotRecord
                    from app.services.fundamentals.snapshot_store import save_snapshot_record

                    snapshot = enrich_sector_fields(
                        FundamentalSnapshot(
                            symbol=symbol.upper(),
                            period="TTM",
                            report_date=report_date,
                            revenue_growth_yoy=float(revenue_growth),
                            gross_margin=float(gross_margin),
                            operating_margin=float(operating_margin),
                            free_cash_flow=float(fcf),
                            cash=float(cash),
                            total_debt=float(total_debt),
                            pe_forward=float(pe_forward) if pe_forward is not None else None,
                            ev_sales=float(ev_sales) if ev_sales is not None else None,
                            fcf_yield=float(fcf_yield) if fcf_yield is not None else None,
                            source="live_yahoo_finance",
                        ),
                        sector,
                        stats=stats,
                        financial_data=findata,
                    )
                    save_snapshot_record(
                        FundamentalSnapshotRecord(
                            symbol=snapshot.symbol,
                            as_of_date=as_of_date,
                            snapshot=snapshot,
                            point_in_time=False,
                            source=snapshot.source,
                            report_period=snapshot.period,
                            filing_date=filing_date,
                            ingested_at=datetime.now(timezone.utc),
                            synthetic_demo=False,
                        )
                    )
                    return snapshot
        except Exception as exc:
            raise RuntimeError(f"Live fundamental data unavailable for {symbol.upper()}") from exc
        finally:
            close = getattr(client, "close", None)
            if close:
                close()

        raise RuntimeError(f"Live fundamental data unavailable for {symbol.upper()}")

    def _mock_fundamentals(self, symbol: str, is_speculative: bool) -> FundamentalSnapshot:
        from app.services.broker.securities import classify_security

        sec_info = classify_security(symbol.upper())
        snapshot = FundamentalSnapshot(
            symbol=symbol.upper(),
            period="TTM",
            report_date=recent_mock_date(42),
            revenue_growth_yoy=0.18 if not is_speculative else 0.42,
            gross_margin=0.62 if not is_speculative else 0.28,
            operating_margin=0.29 if not is_speculative else -0.65,
            free_cash_flow=12_000_000_000 if not is_speculative else -80_000_000,
            cash=78_000_000_000 if not is_speculative else 420_000_000,
            total_debt=31_000_000_000 if not is_speculative else 18_000_000,
            pe_forward=28 if not is_speculative else None,
            ev_sales=9.5 if not is_speculative else 24.0,
            fcf_yield=0.031 if not is_speculative else None,
        )
        sector = sec_info.get("sector", "Unknown")
        if sector == "Financials":
            return snapshot.model_copy(
                update={
                    "price_to_tangible_book": 1.3,
                    "return_on_equity": 0.14,
                    "net_interest_margin": 0.032,
                }
            )
        if sector == "Real Estate":
            return snapshot.model_copy(update={"ffo_per_share": 4.2, "occupancy_rate": 0.96})
        if sector == "Utilities":
            return snapshot.model_copy(update={"rate_base_growth": 0.03, "allowed_roe": 0.10})
        return snapshot
