"use client";

import { Suspense, use, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { DegradedStateBanner } from "@/components/DegradedStateBanner";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { StatCard } from "@/components/StatCard";
import { getInstrumentOverview } from "@/lib/api";
import { useAppRouter } from "@/lib/use-app-router";
import { useClientResource } from "@/lib/use-client-resource";

type Section = Record<string, unknown>;

function str(value: unknown, fallback = "—"): string {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function SecurityWorkspace({ instrumentId }: { instrumentId: string }) {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
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
  const symbol = str(instrument.symbol);

  const priceLabel =
    market.status === "available" && market.price != null
      ? `${str(market.currency, "")} ${Number(market.price).toLocaleString()}`.trim()
      : "Unavailable";

  return (
    <div className="grid gap-6">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-accent">Security workspace</p>
          <h2 className="text-3xl font-semibold">
            {symbol}
            <span className="ml-2 text-base font-normal text-zinc-500">{str(instrument.name, "")}</span>
          </h2>
          <p className="text-sm text-zinc-600">
            {str(instrument.asset_class, "instrument")} · {str(instrument.exchange, "—")} ·{" "}
            {owned ? "Owned" : "Not owned"}
            {instrument.provisional ? " · provisional identity" : ""}
          </p>
        </div>
        {owned ? (
          <Link
            className="inline-flex items-center gap-2 rounded-md border border-line px-3 py-2 text-sm hover:bg-panel"
            href={`/holdings/${encodeURIComponent(instrumentId)}${accountId ? `?account_id=${accountId}` : ""}`}
          >
            Open full holding workspace
          </Link>
        ) : null}
      </div>

      <Disclaimer />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Price" value={priceLabel} detail={str(market.source, "")} />
        <StatCard
          label="Position"
          value={owned ? str(position.quantity, "0") : "None"}
          detail={owned ? `${str(position.portfolio_weight, "0")}% weight` : "Not held"}
        />
        <StatCard
          label="Unrealized P&L"
          value={owned && position.unrealized_pnl != null ? `$${Number(position.unrealized_pnl).toLocaleString()}` : "—"}
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
            <p className="text-sm text-zinc-600">
              No Decision Packet yet. Owned holdings generate one in the Decision Center; unowned
              names get one after research.
            </p>
          )}
        </div>
      </section>

      <p className="text-xs text-zinc-500">
        Every value above carries a source and status. This workspace is the same for owned,
        watchlist, benchmark, ETF, and unowned securities.
      </p>
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
        placeholder="Ticker or instrument id (e.g. MSFT)"
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
