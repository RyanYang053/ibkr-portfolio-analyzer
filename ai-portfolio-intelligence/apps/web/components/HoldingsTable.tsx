import Link from "next/link";
import type { Position } from "@/lib/types";

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
          {positions.map((position) => (
            <tr key={position.symbol} className="border-t border-line">
              <td className="px-3 py-3 font-semibold">
                <Link className="text-accent hover:underline" href={`/holdings/${position.symbol}`}>
                  {position.symbol}
                </Link>
              </td>
              <td className="px-3 py-3">{position.company_name}</td>
              <td className="px-3 py-3">{position.stock_type.replaceAll("_", " ")}</td>
              <td className="px-3 py-3 text-right">{position.portfolio_weight.toFixed(2)}%</td>
              <td className="px-3 py-3 text-right">${position.market_value.toLocaleString()}</td>
              <td className={`px-3 py-3 text-right ${position.unrealized_pnl >= 0 ? "text-accent" : "text-danger"}`}>
                ${position.unrealized_pnl.toLocaleString()}
              </td>
              <td className="px-3 py-3 text-xs text-zinc-600">Human review required</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
