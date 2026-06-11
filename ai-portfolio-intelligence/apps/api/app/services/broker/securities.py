from typing import Any

# Map symbol -> (company_name, asset_class, exchange, currency, sector, industry, stock_type, is_etf, is_speculative)
SECURITIES_DB = {
    "QQQ": ("Invesco QQQ Trust", "ETF", "NASDAQ", "USD", "Technology", "Index ETF", "etf", True, False),
    "SPY": ("SPDR S&P 500 ETF Trust", "ETF", "NYSEARCA", "USD", "Diversified", "Index ETF", "etf", True, False),
    "MSFT": ("Microsoft Corporation", "STK", "NASDAQ", "USD", "Technology", "Software", "mega_cap_quality", False, False),
    "META": ("Meta Platforms", "STK", "NASDAQ", "USD", "Communication Services", "Internet", "mega_cap_quality", False, False),
    "GOOGL": ("Alphabet", "STK", "NASDAQ", "USD", "Communication Services", "Internet", "mega_cap_quality", False, False),
    "SOXX": ("iShares Semiconductor ETF", "ETF", "NASDAQ", "USD", "Technology", "Semiconductors", "etf", True, False),
    "SOFI": ("SoFi Technologies", "STK", "NASDAQ", "USD", "Financials", "Fintech", "fintech", False, False),
    "CRM": ("Salesforce", "STK", "NYSE", "USD", "Technology", "Software", "software", False, False),
    "CELH": ("Celsius Holdings", "STK", "NASDAQ", "USD", "Consumer Defensive", "Beverages", "consumer", False, False),
    "NKE": ("Nike", "STK", "NYSE", "USD", "Consumer Cyclical", "Apparel", "consumer", False, False),
    "IONQ": ("IonQ", "STK", "NYSE", "USD", "Technology", "Quantum Computing", "speculative_growth", False, True),
    "LAES": ("SEALSQ", "STK", "NASDAQ", "USD", "Technology", "Semiconductors", "speculative_growth", False, True),
    "INFQ": ("Infinite Acquisition Corp", "STK", "NASDAQ", "USD", "Technology", "Speculative", "speculative_growth", False, True),
    # Additional common assets
    "AMZN": ("Amazon.com Inc.", "STK", "NASDAQ", "USD", "Consumer Cyclical", "Internet Retail", "mega_cap_quality", False, False),
    "AAPL": ("Apple Inc.", "STK", "NASDAQ", "USD", "Technology", "Consumer Electronics", "mega_cap_quality", False, False),
    "NVDA": ("NVIDIA Corporation", "STK", "NASDAQ", "USD", "Technology", "Semiconductors", "mega_cap_quality", False, False),
    "TSLA": ("Tesla Inc.", "STK", "NASDAQ", "USD", "Consumer Cyclical", "Auto Manufacturers", "large_cap_growth", False, False),
}

def classify_security(symbol: str, sec_type: str = "STK") -> dict[str, Any]:
    sym = symbol.upper().strip()
    if sym in SECURITIES_DB:
        company, asset_class, exchange, currency, sector, industry, stock_type, is_etf, is_speculative = SECURITIES_DB[sym]
        return {
            "company_name": company,
            "asset_class": asset_class,
            "exchange": exchange,
            "currency": currency,
            "sector": sector,
            "industry": industry,
            "stock_type": stock_type,
            "is_etf": is_etf,
            "is_speculative": is_speculative
        }
    
    # Generic fallback rules
    is_etf = (sec_type == "ETF")
    return {
        "company_name": sym,
        "asset_class": sec_type,
        "exchange": "",
        "currency": "USD",
        "sector": "Technology" if is_etf else "Unknown",
        "industry": "Index ETF" if is_etf else "Unknown",
        "stock_type": "etf" if is_etf else "unknown",
        "is_etf": is_etf,
        "is_speculative": False
    }
