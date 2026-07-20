import Link from "next/link";
import type { Position } from "@/lib/types";

function positionRowKey(position: Position): string {
  return `${position.account_id}:${position.con_id ?? position.local_symbol ?? position.symbol}`;
}

function positionHref(position: Position): string {
  const params = new URLSearchParams();
  const isDerivative =
    position.asset_class === "OPT" ||
    position.asset_class === "FOP" ||
    position.asset_class === "FUT" ||
    (position.multiplier ?? 1) !== 1;
  params.set(
    "symbol",
    isDerivative && position.local_symbol ? position.local_symbol : position.symbol,
  );
  if (position.account_id && position.account_id !== "all") {
    params.set("account_id", position.account_id);
  }
  if (position.con_id != null) {
    params.set("con_id", String(position.con_id));
  }
  return `/holdings/detail?${params.toString()}`;
}

function formatMoney(value: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency || "USD",
  }).format(value);
}

export function HoldingsTable({ positions }: { positions: Position[] }) {
  return (
    <div className="overflow-x-auto rounded-md border border-line bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-panel text-left text-xs uppercase tracking-wide text-zinc-500">
          <tr>
            <th className="px-3 py-3">Ticker</th>
            <th className="px-3 py-3">Name</th>
            <th className="px-3 py-3">Type</th>
            <th className="px-3 py-3 text-right">Weight</th>
            <th className="px-3 py-3 text-right">Market Value</th>
            <th className="px-3 py-3 text-right">Unrealized P&L</th>
            <th className="px-3 py-3">Review</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => {
            const reportingCurrency = position.reporting_currency ?? position.currency;
            const marketValue = position.market_value_base ?? position.market_value_native ?? position.market_value;
            const showNative =
              position.market_value_native != null &&
              position.reporting_currency &&
              position.currency !== position.reporting_currency;

            return (
              <tr key={positionRowKey(position)} className="border-t border-line">
                <td className="px-3 py-3 font-semibold">
                  <Link className="text-accent hover:underline" href={positionHref(position)}>
                    {position.local_symbol ?? position.symbol}
                  </Link>
                </td>
                <td className="px-3 py-3">{position.company_name}</td>
                <td className="px-3 py-3">{position.stock_type.replaceAll("_", " ")}</td>
                <td className="px-3 py-3 text-right">{position.portfolio_weight.toFixed(2)}%</td>
                <td className="px-3 py-3 text-right">
                  <div>{formatMoney(marketValue, reportingCurrency)}</div>
                  {showNative ? (
                    <div className="text-xs text-zinc-500">
                      Native: {formatMoney(position.market_value_native as number, position.currency)}
                    </div>
                  ) : null}
                </td>
                <td className={`px-3 py-3 text-right ${position.unrealized_pnl >= 0 ? "text-accent" : "text-danger"}`}>
                  {formatMoney(position.unrealized_pnl, position.currency)}
                </td>
                <td className="px-3 py-3 text-xs text-zinc-600">Human review required</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
