"use client";

import { Suspense } from "react";
import { Disclaimer } from "@/components/Disclaimer";
import { DegradedStateBanner } from "@/components/DegradedStateBanner";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { StatCard } from "@/components/StatCard";
import { getMarketCalendar, getMarketOverview } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

type Rec = Record<string, unknown>;

function str(v: unknown, f = "—"): string {
  return v === null || v === undefined || v === "" ? f : String(v);
}

function MarketsContent() {
  const { data, error, loading } = useClientResource(
    () => Promise.all([getMarketOverview(), getMarketCalendar()]),
    [],
  );
  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  const [overview, calendar] = data ?? [null, null];
  const regime = (overview?.regime ?? null) as Rec | null;
  const indicators = (overview?.indicators as Rec[] | undefined) ?? [];
  const events = (calendar?.events as Rec[] | undefined) ?? [];
  const regimeLabel = str(regime?.label).replaceAll("_", " ");
  const insufficient = regime?.label === "insufficient_data";

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Markets</p>
        <h2 className="text-3xl font-semibold">Market context &amp; regime</h2>
        <p className="text-sm text-zinc-600">
          The regime is classified by an explainable rule engine — never by an AI model. Indicators
          without a configured provider are shown as unavailable, not invented.
        </p>
      </div>
      <Disclaimer />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Regime" value={regimeLabel} detail={`confidence ${str(regime?.confidence)}`} tone={insufficient ? "warn" : "good"} />
        <StatCard label="Prev regime" value={str(regime?.previous_regime).replaceAll("_", " ")} />
        <StatCard label="Changed dims" value={String(((regime?.changed_dimensions as unknown[]) ?? []).length)} />
        <StatCard label="Method" value={str(regime?.methodology)} />
      </section>

      {insufficient ? (
        <DegradedStateBanner message="Not enough reliable market dimensions to classify a regime — reported as insufficient data rather than guessed." />
      ) : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 text-lg font-semibold">Why this regime</h3>
          <div className="grid gap-3 text-sm">
            <div>
              <p className="text-zinc-500">Supporting</p>
              <ul className="list-disc pl-5">
                {((regime?.supporting_evidence as string[]) ?? []).map((e) => <li key={e}>{e}</li>)}
                {((regime?.supporting_evidence as string[]) ?? []).length === 0 ? <li className="text-zinc-500">none</li> : null}
              </ul>
            </div>
            <div>
              <p className="text-zinc-500">Contradicting</p>
              <ul className="list-disc pl-5">
                {((regime?.contradicting_evidence as string[]) ?? []).map((e) => <li key={e}>{e}</li>)}
                {((regime?.contradicting_evidence as string[]) ?? []).length === 0 ? <li className="text-zinc-500">none</li> : null}
              </ul>
            </div>
            <div>
              <p className="text-zinc-500">Portfolio implications</p>
              <ul className="list-disc pl-5">
                {((regime?.portfolio_implications as string[]) ?? []).map((e) => <li key={e}>{e}</li>)}
              </ul>
            </div>
          </div>
        </div>

        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 text-lg font-semibold">Indicators</h3>
          <div className="grid gap-1 text-sm">
            {indicators.map((ind) => (
              <div key={String(ind.key)} className="flex items-center justify-between border-t border-line py-1 first:border-0">
                <span>{str(ind.label)}</span>
                <span className={ind.status === "available" ? "text-emerald-700" : "text-zinc-400"}>
                  {ind.status === "available" ? str(ind.value) : "unavailable"}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-zinc-500">{str((overview?.data_quality as Rec)?.note, "")}</p>
        </div>
      </section>

      <section className="rounded-md border border-line bg-white p-4">
        <h3 className="mb-3 text-lg font-semibold">Economic &amp; earnings calendar</h3>
        {events.length === 0 ? (
          <p className="text-sm text-zinc-600">
            No events loaded. They appear when imported or supplied by a data provider.
          </p>
        ) : (
          <ul className="grid gap-1 text-sm">
            {events.map((ev) => (
              <li key={String(ev.event_id)} className="flex justify-between border-t border-line py-1 first:border-0">
                <span>{str(ev.name)}</span>
                <span className="text-zinc-500">{str(ev.event_time)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export default function MarketsPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <MarketsContent />
    </Suspense>
  );
}
