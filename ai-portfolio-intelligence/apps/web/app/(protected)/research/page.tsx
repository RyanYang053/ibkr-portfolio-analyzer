"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { DegradedStateBanner } from "@/components/DegradedStateBanner";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getResearchChangeFeed, getResearchQueue } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

function ResearchContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const { data, error, loading } = useClientResource(
    () =>
      Promise.all([
        getResearchQueue(accountId),
        // P0.7 / §15.3: tag a failed change-feed fetch as degraded rather than empty.
        getResearchChangeFeed(accountId).catch(() => ({ changes: [], __degraded: true })),
      ]),
    [accountId],
  );
  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  const [queuePayload, changePayload] = data ?? [{ queue: [], catalysts: [] }, { changes: [] }];
  const changeFeedDegraded = Boolean((changePayload as { __degraded?: boolean }).__degraded);
  const queue = Array.isArray(queuePayload?.queue)
    ? (queuePayload.queue as Array<Record<string, unknown>>)
    : Array.isArray(queuePayload?.items)
      ? (queuePayload.items as Array<Record<string, unknown>>)
      : [];
  const catalysts = Array.isArray(queuePayload?.catalysts)
    ? (queuePayload.catalysts as Array<Record<string, unknown>>)
    : [];
  const changes = Array.isArray(changePayload?.changes)
    ? (changePayload.changes as Array<Record<string, unknown>>)
    : [];

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Research</p>
        <h2 className="text-3xl font-semibold">Queue and change feed</h2>
        <p className="text-sm text-zinc-600">
          Universe limited to holdings, watchlist, approved ETFs, and manually approved names.
        </p>
      </div>
      <Disclaimer />
      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 font-semibold">Research queue</h3>
          <div className="grid gap-2 text-sm">
            {queue.length === 0 ? (
              <p className="text-zinc-600">No ranked research tasks.</p>
            ) : (
              queue.slice(0, 20).map((row, idx) => (
                <div key={String(row.candidate_id || row.instrument_key || idx)} className="rounded-md border border-line p-3">
                  <div className="font-medium">
                    {String(row.symbol || row.instrument_key || "—")} · {String(row.priority || row.rank || "")}
                  </div>
                  <p className="text-xs text-zinc-600">{String(row.reason || row.outcome || "")}</p>
                </div>
              ))
            )}
          </div>
        </div>
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 font-semibold">Change feed</h3>
          <div className="grid gap-2 text-sm">
            {changeFeedDegraded ? (
              <DegradedStateBanner message="Change feed unavailable — the request failed. This is not a confirmation that nothing changed." />
            ) : changes.length === 0 ? (
              <p className="text-zinc-600">No material changes detected.</p>
            ) : (
              changes.slice(0, 20).map((row, idx) => (
                <div key={`${row.decision_id}-${idx}`} className="rounded-md border border-line p-3">
                  <div className="font-medium">
                    {String(row.symbol)} · {String(row.change_code)}
                  </div>
                  <p className="text-xs text-zinc-600">Severity {String(row.severity)}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </section>
      <section className="rounded-md border border-line bg-white p-4">
        <h3 className="mb-3 font-semibold">Catalyst calendar</h3>
        <div className="grid gap-2 text-sm">
          {catalysts.length === 0 ? (
            <p className="text-zinc-600">
              No catalyst windows loaded. Option expiries and news-derived windows appear when
              holdings or watchlist symbols have usable evidence.
            </p>
          ) : (
            catalysts.slice(0, 20).map((event, idx) => (
              <div key={`${event.symbol}-${event.event_date}-${idx}`} className="rounded-md border border-line p-3">
                <div className="font-medium">
                  {String(event.symbol)} · {String(event.catalyst_type || event.event_type || "catalyst")}
                </div>
                <p className="text-xs text-zinc-600">
                  {String(event.event_date || event.date || "")}
                  {event.provisional ? " · provisional" : ""}
                  {event.source ? ` · ${String(event.source)}` : ""}
                </p>
              </div>
            ))
          )}
        </div>
      </section>
      <div className="flex flex-wrap gap-4">
        <Link className="text-sm text-accent hover:underline" href="/research/screener">
          Open screener
        </Link>
        <Link className="text-sm text-accent hover:underline" href="/research/notes">
          Research notes
        </Link>
        <Link className="text-sm text-accent hover:underline" href="/research/compare">
          Compare candidates
        </Link>
        <Link className="text-sm text-accent hover:underline" href="/watchlist">
          Open watchlist
        </Link>
      </div>
    </div>
  );
}

export default function ResearchPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <ResearchContent />
    </Suspense>
  );
}
