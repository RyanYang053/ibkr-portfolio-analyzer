"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowUpRight, Search } from "lucide-react";

import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { StatusBadge } from "@/components/ui/Badge";
import { getDecisionQueue } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";
import { humanizeCode, humanizeCodeList } from "@/lib/format";

/** Urgent work first; within a band, keep the server's order. */
const PRIORITY_ORDER: Record<string, number> = {
  critical: 0,
  urgent: 1,
  high: 1,
  this_week: 2,
  routine: 3,
  low: 4,
};

function priorityRank(value: unknown): number {
  return PRIORITY_ORDER[String(value ?? "routine").toLowerCase()] ?? 3;
}

function DecisionsContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const { data, error, loading, refreshing, stale, reload } = useClientResource(
    () => getDecisionQueue(accountId),
    [accountId],
  );
  const [filter, setFilter] = useState("");

  const queue = useMemo(() => {
    const rows = [...(data?.queue ?? [])].sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority));
    const term = filter.trim().toLowerCase();
    if (!term) return rows;
    return rows.filter((row) =>
      [row.symbol, row.outcome, row.priority, row.confidence_status, ...(row.blockers ?? [])]
        .join(" ")
        .toLowerCase()
        .includes(term),
    );
  }, [data, filter]);

  if (loading) return <PageLoading variant="table" label="Loading decision queue" />;

  const total = data?.queue?.length ?? 0;

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Decision queue"
        title="Decisions"
        description="One open packet per holding. Every outcome is a review instruction — nothing here reaches a broker."
        refreshing={refreshing}
        stale={stale}
        actions={
          <Link
            className="inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-sm font-medium transition-colors hover:bg-panel"
            href="/decision-center"
          >
            Decision Center <ArrowUpRight size={14} aria-hidden />
          </Link>
        }
      />
      <Disclaimer />
      {error ? <PageErrorBanner message={error} onRetry={reload} /> : null}

      {total > 0 ? (
        <div className="relative max-w-xs">
          <label htmlFor="decision-filter" className="sr-only">
            Filter decisions
          </label>
          <input
            id="decision-filter"
            type="search"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder={`Filter ${total} decisions…`}
            className="w-full rounded-md border border-hairline bg-surface py-1.5 pl-8 pr-3 text-sm text-zinc-900 placeholder-zinc-400 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
          <Search className="pointer-events-none absolute left-2.5 top-2 text-zinc-400" size={14} aria-hidden />
        </div>
      ) : null}

      {total === 0 ? (
        <EmptyState
          title="No decisions requiring review"
          description="Monitors keep running in Decision Center; nothing currently needs an answer from you."
          action={
            <Link className="text-sm font-medium text-accent hover:underline" href="/decision-center">
              Open Decision Center
            </Link>
          }
        />
      ) : queue.length === 0 ? (
        <EmptyState title="No decisions match this filter" description={`Nothing in the queue matches “${filter}”.`} />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-hairline bg-surface shadow-sm">
          <table className="min-w-full text-left text-sm">
            <caption className="sr-only">Open decision packets, highest priority first.</caption>
            <thead className="border-b border-hairline bg-panel text-[11px] uppercase tracking-wider text-zinc-500">
              <tr>
                <th scope="col" className="px-3 py-2.5 font-semibold">Symbol</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Outcome</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Priority</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Confidence</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Blockers</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">
                  <span className="sr-only">Open packet</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {queue.map((row) => (
                <tr key={row.decision_id} className="border-b border-hairline transition-colors last:border-0 hover:bg-panel/60">
                  <td className="px-3 py-2.5 font-semibold text-zinc-900">{row.symbol}</td>
                  <td className="px-3 py-2.5">{humanizeCode(row.outcome)}</td>
                  <td className="px-3 py-2.5">
                    <StatusBadge value={row.priority ?? "routine"} />
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusBadge value={row.confidence_status} />
                  </td>
                  <td className="max-w-[32ch] px-3 py-2.5 text-xs text-zinc-600">
                    {humanizeCodeList((row.blockers || []).slice(0, 2))}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <Link
                      className="text-accent hover:underline"
                      href={`/decisions/${encodeURIComponent(row.decision_id)}`}
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function DecisionsPage() {
  return (
    <Suspense fallback={<PageLoading variant="table" />}>
      <DecisionsContent />
    </Suspense>
  );
}
