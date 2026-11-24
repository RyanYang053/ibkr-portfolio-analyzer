from __future__ import annotations
import argparse
import html
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
STYLE = "body{background:#101827;color:#e6edf7;font:16px/1.55 system-ui,sans-serif;margin:0}main{max-width:1000px;margin:auto;padding:44px 24px}h1{font-size:clamp(28px,4vw,44px);margin:0}h2{margin-top:32px}p{color:#aebcd0}section,pre{background:#19263a;border:1px solid #33455f;border-radius:12px;padding:18px;overflow:auto}table{width:100%;border-collapse:collapse;text-align:left}td,th{padding:8px 12px;border-bottom:1px solid #33455f}th{color:#9dbce5}pre{white-space:pre-wrap;overflow-wrap:anywhere}small{color:#a7e3ce;font-weight:700}"
def esc(v):
    return html.escape(str(v), quote=True)
def table(headers, rows):
    return "<section><table><thead><tr>" + "".join("<th>"+esc(x)+"</th>" for x in headers) + "</tr></thead><tbody>" + "".join("<tr>"+"".join("<td>"+esc(x)+"</td>" for x in row)+"</tr>" for row in rows) + "</tbody></table></section>"
def write_report(path, title, summary, body):
    document = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src &apos;none&apos;; style-src &apos;unsafe-inline&apos;; base-uri &apos;none&apos;; form-action &apos;none&apos;"><title>'+esc(title)+'</title><style>'+STYLE+'</style></head><body><main><small>SYNTHETIC RESEARCH DEMO</small><h1>'+esc(title)+'</h1><p>'+esc(summary)+'</p>'+body+'<p>Fixture data only. No investment recommendation or live performance claim.</p></main></body></html>'
    with path.open("x", encoding="utf-8") as handle:
        handle.write(document)
    print(f"Report: {path.resolve()}")
def output_path():
    parser = argparse.ArgumentParser(description="Generate a local fixture-based HTML preview.")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args().output

import sys
def main():
    out = output_path()
    sys.path.insert(0, str(ROOT / "ai-portfolio-intelligence" / "apps" / "api"))
    from app.services.broker.mock_ibkr import MockIBKRAdapter
    adapter = MockIBKRAdapter()
    body = ""
    for account in adapter.get_accounts():
        summary = adapter.get_account_summary(account.id)
        body += "<h2>"+esc(account.account_alias)+"</h2>"
        body += table(["Currency","Net liquidation","Cash","Unrealized P&L"], [(summary.base_currency, f"{summary.net_liquidation:,.2f}", f"{summary.cash:,.2f}", f"{summary.total_unrealized_pnl:,.2f}")])
        positions = sorted(adapter.get_positions(account.id), key=lambda p: p.market_value, reverse=True)
        body += "<h3>Invested allocation</h3><section>"
        for p in positions[:6]:
            weight = max(0, min(100, float(p.portfolio_weight)))
            body += "<p>"+esc(p.symbol)+" · "+esc(f"{weight:.2f}%")+"<br><meter min='0' max='100' value='"+esc(f"{weight:.2f}")+"' style='width:100%;height:20px'></meter></p>"
        body += "</section>"
        rows = [(p.symbol, p.currency, f"{p.quantity:g}", f"{p.market_value:,.2f}", f"{p.unrealized_pnl:,.2f}", f"{p.portfolio_weight:.2f}%") for p in positions]
        body += table(["Symbol","Currency","Quantity","Value","Unrealized P&L","Invested weight"], rows)
    body += "<p>Account values are kept separate by currency; no FX conversion or consolidated total is implied.</p>"
    write_report(out, "Portfolio Analyzer sample holdings", "Mock adapter output, not a screenshot of the full app.", body)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
