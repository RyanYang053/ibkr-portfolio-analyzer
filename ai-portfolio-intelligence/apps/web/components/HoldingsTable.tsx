"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";

import { AppLink as Link } from "@/components/AppLink";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatCurrency, formatPercent, humanizeCode, toneClass } from "@/lib/format";
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

function reportedValue(position: Position): number {
  return position.market_value_base ?? position.market_value_native ?? position.market_value;
}

type SortKey = "symbol" | "type" | "weight" | "value" | "pnl";

const COLUMNS: Array<{ key: SortKey; label: string; align: "left" | "right"; hint?: string }> = [
  { key: "symbol", label: "Ticker", align: "left" },
  { key: "type", label: "Type", align: "left" },
  { key: "weight", label: "Weight", align: "right", hint: "Share of net liquidation, the same basis as the IPS single-name limit" },
  { key: "value", label: "Market value", align: "right" },
  { key: "pnl", label: "Unrealized P&L", align: "right" },
];

function compare(a: Position, b: Position, key: SortKey): number {
  switch (key) {
    case "symbol":
      return (a.local_symbol ?? a.symbol).localeCompare(b.local_symbol ?? b.symbol);
    case "type":
      return a.stock_type.localeCompare(b.stock_type);
    case "weight":
      return a.portfolio_weight - b.portfolio_weight;
    case "value":
      return reportedValue(a) - reportedValue(b);
    case "pnl":
      return a.unrealized_pnl - b.unrealized_pnl;
  }
}

/**
 * The holdings grid.
 *
 * Sorting is client-side over an already-loaded page of positions, so
 * re-ordering never triggers a request. Weight is drawn as a bar behind the
 * number, which makes concentration visible at a glance without a second chart.
 */
export function HoldingsTable({ positions }: { positions: Position[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("value");
  const [ascending, setAscending] = useState(false);

  const rows = useMemo(() => {
    const sorted = [...positions].sort((a, b) => compare(a, b, sortKey));
    return ascending ? sorted : sorted.reverse();
  }, [positions, sortKey, ascending]);

  const maxWeight = useMemo(
    () => Math.max(1, ...positions.map((position) => position.portfolio_weight)),
    [positions],
  );

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setAscending((current) => !current);
      return;
    }
    setSortKey(key);
    // Names read best A→Z; money reads best largest-first.
    setAscending(key === "symbol" || key === "type");
  }

  if (positions.length === 0) {
    return (
      <EmptyState
        title="No positions in this account"
        description="Once the broker connection returns holdings they appear here, largest first."
      />
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-hairline bg-surface shadow-sm">
      <table className="min-w-full text-sm">
        <caption className="sr-only">
          Portfolio holdings, sortable by ticker, type, weight, market value and unrealized profit or loss.
        </caption>
        <thead className="bg-panel text-left text-[11px] uppercase tracking-wider text-zinc-500">
          <tr>
            {COLUMNS.map((column) => {
              const active = sortKey === column.key;
              const SortIcon = !active ? ChevronsUpDown : ascending ? ArrowUp : ArrowDown;
              return (
                <th
                  key={column.key}
                  scope="col"
                  title={column.hint}
                  aria-sort={active ? (ascending ? "ascending" : "descending") : "none"}
                  className={`px-3 py-2.5 font-semibold ${column.align === "right" ? "text-right" : ""}`}
                >
                  <button
                    type="button"
                    onClick={() => toggleSort(column.key)}
                    className={`inline-flex items-center gap-1 uppercase tracking-wider transition-colors hover:text-zinc-900 ${
                      active ? "text-zinc-900" : ""
                    } ${column.align === "right" ? "flex-row-reverse" : ""}`}
                  >
                    {column.label}
                    <SortIcon size={11} aria-hidden className={active ? "" : "opacity-40"} />
                  </button>
                </th>
              );
            })}
            <th scope="col" className="px-3 py-2.5 font-semibold">
              Review
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((position) => {
            const reportingCurrency = position.reporting_currency ?? position.currency;
            const marketValue = reportedValue(position);
            const showNative =
              position.market_value_native != null &&
              position.reporting_currency &&
              position.currency !== position.reporting_currency;

            return (
              <tr key={positionRowKey(position)} className="border-t border-hairline transition-colors hover:bg-panel/60">
                <td className="px-3 py-2.5 font-semibold">
                  <Link className="text-accent hover:underline" href={positionHref(position)}>
                    {position.local_symbol ?? position.symbol}
                  </Link>
                  <div className="max-w-[22ch] truncate text-xs font-normal text-zinc-500">
                    {position.company_name}
                  </div>
                </td>
                <td className="px-3 py-2.5 text-xs text-zinc-600">{humanizeCode(position.stock_type)}</td>
                <td className="relative px-3 py-2.5 text-right">
                  {/* Concentration bar, behind the figure it describes. */}
                  <span
                    aria-hidden
                    className="absolute inset-y-1.5 right-2 rounded-sm bg-accent-soft"
                    style={{ width: `${(position.portfolio_weight / maxWeight) * 68}%` }}
                  />
                  <span className="num relative">{formatPercent(position.portfolio_weight)}</span>
                </td>
                <td className="num px-3 py-2.5 text-right">
                  <div>{formatCurrency(marketValue, { currency: reportingCurrency })}</div>
                  {showNative ? (
                    <div className="text-xs text-zinc-500">
                      Native:{" "}
                      {formatCurrency(position.market_value_native, { currency: position.currency })}
                    </div>
                  ) : null}
                </td>
                <td className={`num px-3 py-2.5 text-right font-medium ${toneClass(position.unrealized_pnl)}`}>
                  {formatCurrency(position.unrealized_pnl, { currency: position.currency, signed: true })}
                </td>
                <td className="px-3 py-2.5 text-xs text-zinc-600">Human review required</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
