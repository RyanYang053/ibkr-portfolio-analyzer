"use client";

import { Suspense, use, useState } from "react";
import type { ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { DegradedStateBanner } from "@/components/DegradedStateBanner";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { PerformanceSparkline } from "@/components/PerformanceSparkline";
import { StatCard } from "@/components/StatCard";
import {
  getChartData,
  getFundamentals,
  getInstrumentOverview,
  getStockValuation,
  getTechnicals,
} from "@/lib/api";
import { useAppRouter } from "@/lib/use-app-router";
import { useClientResource } from "@/lib/use-client-resource";

type Section = Record<string, unknown>;

const TABS = ["Overview", "Chart", "Technicals", "Financials", "Valuation"] as const;
type Tab = (typeof TABS)[number];

function str(value: unknown, fallback = "—"): string {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}
function num(value: unknown): string {
  return value === null || value === undefined || value === "" ? "—" : Number(value).toLocaleString();
}
function pct(value: unknown): string {
  return value === null || value === undefined ? "—" : `${(Number(value) * 100).toFixed(1)}%`;
}

function OverviewTab({ instrumentId, accountId }: { instrumentId: string; accountId?: string }) {
  const { data, error, loading } = useClientResource(
    () => getInstrumentOverview(instrumentId, accountId),
    [instrumentId, accountId],
  );
  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;
  if (!data) return <PageErrorBanner message="Security overview is unavailable." />;

  const instrument = (data.instrument ?? {}) as Section;
  const market = (data.market ?? {}) as Section;
  const position = (data.position ?? {}) as Section;
  const decision = (data.decision ?? {}) as Section;
  const owned = data.position_status === "owned";
  const priceLabel =
    market.status === "available" && market.price != null
      ? `${str(market.currency, "")} ${Number(market.price).toLocaleString()}`.trim()
      : "Unavailable";

  return (
    <div className="grid gap-4">
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Price" value={priceLabel} detail={str(market.source, "")} />
        <StatCard
          label="Position"
          value={owned ? num(position.quantity) : "None"}
          detail={owned ? `${str(position.portfolio_weight, "0")}% weight` : "Not held"}
        />
        <StatCard
          label="Unrealized P&L"
          value={owned && position.unrealized_pnl != null ? `$${num(position.unrealized_pnl)}` : "—"}
          tone={owned && Number(position.unrealized_pnl) >= 0 ? "good" : "neutral"}
        />
        <StatCard
          label="Decision"
          value={decision.status === "available" ? str(decision.outcome) : "None yet"}
          detail={decision.status === "available" ? `Priority ${str(decision.priority)}` : ""}
        />
      </section>
      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 text-lg font-semibold">Market</h3>
          {market.status === "available" ? (
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-zinc-500">Price</dt>
              <dd>{priceLabel}</dd>
              <dt className="text-zinc-500">As of</dt>
              <dd>{str(market.as_of)}</dd>
              <dt className="text-zinc-500">Source</dt>
              <dd>{str(market.source)}</dd>
            </dl>
          ) : (
            <DegradedStateBanner message="No quote source is configured for this security — a price is not shown rather than invented." />
          )}
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 text-lg font-semibold">Current decision</h3>
          {decision.status === "available" ? (
            <div className="grid gap-2 text-sm">
              <div className="flex justify-between">
                <span className="font-semibold">{str(decision.outcome)}</span>
                <span className="text-zinc-500">Priority {str(decision.priority)}</span>
              </div>
              <p className="text-xs text-zinc-600">
                Confidence {str(decision.confidence_status)} · Next review {str(decision.next_review_date)}
              </p>
              {Array.isArray(decision.top_risks) && (decision.top_risks as string[]).length > 0 ? (
                <ul className="mt-1 list-disc pl-5 text-xs text-zinc-700">
                  {(decision.top_risks as string[]).map((risk) => (
                    <li key={risk}>{risk.replaceAll("_", " ")}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : decision.status === "unavailable" ? (
            <DegradedStateBanner message="Decision data could not be loaded — this is a failure, not an absence of a decision." />
          ) : (
            <p className="text-sm text-zinc-600">No Decision Packet yet.</p>
          )}
        </div>
      </section>
      {owned ? (
        <Link
          className="text-sm text-accent hover:underline"
          href={`/holdings/${encodeURIComponent(instrumentId)}${accountId ? `?account_id=${accountId}` : ""}`}
        >
          Open full holding workspace →
        </Link>
      ) : null}
    </div>
  );
}

function DataTab<T>({
  loader,
  deps,
  render,
}: {
  loader: () => Promise<T>;
  deps: readonly unknown[];
  render: (data: T) => ReactNode;
}) {
  const { data, error, loading } = useClientResource(loader, deps);
  if (loading) return <p className="text-sm text-zinc-600">Loading…</p>;
  if (error)
    return (
      <DegradedStateBanner
        message={`This data is unavailable for this security (${error}). It may require a held position or a configured data provider.`}
      />
    );
  if (!data) return <DegradedStateBanner message="No data returned." />;
  return <>{render(data)}</>;
}

function SecurityWorkspace({ instrumentId }: { instrumentId: string }) {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const [tab, setTab] = useState<Tab>("Overview");
  const symbol = instrumentId.split(":")[0].toUpperCase();

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Security workspace</p>
        <h2 className="text-3xl font-semibold">{symbol}</h2>
        <p className="text-sm text-zinc-600">
          One workspace for owned, watchlist, benchmark, ETF, and unowned securities. Technicals are
          evidence, not trade instructions.
        </p>
      </div>
      <Disclaimer />

      <div className="flex flex-wrap gap-1 border-b border-line">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setTab(name)}
            className={`px-3 py-2 text-sm ${
              tab === name ? "border-b-2 border-accent font-semibold text-accent" : "text-zinc-600"
            }`}
          >
            {name}
          </button>
        ))}
      </div>

      {tab === "Overview" ? <OverviewTab instrumentId={instrumentId} accountId={accountId} /> : null}

      {tab === "Chart" ? (
        <DataTab
          loader={() => getChartData(symbol, "1y")}
          deps={[symbol]}
          render={(rows) => {
            const closes = rows.map((r) => r.close);
            return (
              <div className="rounded-md border border-line bg-white p-4">
                <h3 className="mb-3 text-lg font-semibold">Price ({rows.length} sessions)</h3>
                {closes.length >= 2 ? <PerformanceSparkline values={closes} /> : null}
                <table className="mt-3 w-full text-sm">
                  <thead>
                    <tr className="text-left text-zinc-500">
                      <th className="py-1">Date</th>
                      <th>Close</th>
                      <th>High</th>
                      <th>Low</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.slice(-10).reverse().map((r) => (
                      <tr key={r.date} className="border-t border-line">
                        <td className="py-1">{r.date}</td>
                        <td>{num(r.close)}</td>
                        <td>{num(r.high)}</td>
                        <td>{num(r.low)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }}
        />
      ) : null}

      {tab === "Technicals" ? (
        <DataTab
          loader={() => getTechnicals(symbol)}
          deps={[symbol]}
          render={(t) => (
            <div className="rounded-md border border-line bg-white p-4">
              <h3 className="mb-3 text-lg font-semibold">Technicals</h3>
              <dl className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
                <div><dt className="text-zinc-500">Trend</dt><dd>{str(t.trend_classification)}</dd></div>
                <div><dt className="text-zinc-500">RSI (14)</dt><dd>{num(t.rsi_14)}</dd></div>
                <div><dt className="text-zinc-500">ATR (14)</dt><dd>{num(t.atr_14)}</dd></div>
                <div><dt className="text-zinc-500">Drawdown 52w</dt><dd>{pct(t.drawdown_from_52w_high)}</dd></div>
              </dl>
              <p className="mt-3 text-xs text-zinc-500">Method: {str(t.methodology)} · {str(t.data_quality)}</p>
            </div>
          )}
        />
      ) : null}

      {tab === "Financials" ? (
        <DataTab
          loader={() => getFundamentals(symbol)}
          deps={[symbol]}
          render={(f) => (
            <div className="rounded-md border border-line bg-white p-4">
              <h3 className="mb-3 text-lg font-semibold">Financials · {str(f.period)} {str(f.report_date, "")}</h3>
              <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
                <div><dt className="text-zinc-500">Revenue growth YoY</dt><dd>{pct(f.revenue_growth_yoy)}</dd></div>
                <div><dt className="text-zinc-500">Gross margin</dt><dd>{pct(f.gross_margin)}</dd></div>
                <div><dt className="text-zinc-500">Operating margin</dt><dd>{pct(f.operating_margin)}</dd></div>
                <div><dt className="text-zinc-500">Free cash flow</dt><dd>{num(f.free_cash_flow)}</dd></div>
                <div><dt className="text-zinc-500">Total debt</dt><dd>{num(f.total_debt)}</dd></div>
                <div><dt className="text-zinc-500">Forward P/E</dt><dd>{num(f.pe_forward)}</dd></div>
              </dl>
            </div>
          )}
        />
      ) : null}

      {tab === "Valuation" ? (
        <DataTab
          loader={() => getStockValuation(symbol, accountId)}
          deps={[symbol, accountId]}
          render={(v) => {
            const val = v as Section;
            const status = str(val.status ?? val.data_quality_status ?? "");
            return (
              <div className="rounded-md border border-line bg-white p-4">
                <h3 className="mb-3 text-lg font-semibold">Valuation</h3>
                {status.toLowerCase().includes("withheld") ? (
                  <DegradedStateBanner message="Valuation is withheld until an approved methodology and sufficient data exist — no estimate is fabricated." />
                ) : (
                  <pre className="overflow-x-auto rounded bg-panel p-3 text-xs">
                    {JSON.stringify(val, null, 2)}
                  </pre>
                )}
              </div>
            );
          }}
        />
      ) : null}
    </div>
  );
}

function SecuritySearch() {
  const router = useAppRouter();
  const [q, setQ] = useState("");
  return (
    <form
      className="mb-4 flex gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        const value = q.trim().toUpperCase();
        if (value) router.push(`/securities/${encodeURIComponent(value)}`);
      }}
    >
      <input
        className="w-full max-w-xs rounded-md border border-line px-3 py-2 text-sm"
        placeholder="Jump to ticker (e.g. MSFT)"
        value={q}
        onChange={(event) => setQ(event.target.value)}
        aria-label="Security search"
      />
      <button className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel" type="submit">
        Open
      </button>
    </form>
  );
}

export default function SecurityPage({ params }: { params: Promise<{ instrumentId: string }> }) {
  const { instrumentId } = use(params);
  const decoded = decodeURIComponent(instrumentId);
  return (
    <Suspense fallback={<PageLoading />}>
      <SecuritySearch />
      <SecurityWorkspace instrumentId={decoded} />
    </Suspense>
  );
}
