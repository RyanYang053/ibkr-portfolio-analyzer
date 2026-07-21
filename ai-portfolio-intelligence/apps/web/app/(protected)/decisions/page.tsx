"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getDecisionQueue } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

function DecisionsContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const { data, error, loading } = useClientResource(() => getDecisionQueue(accountId), [accountId]);

  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  const queue = data?.queue ?? [];
  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Decision queue</p>
        <h2 className="text-3xl font-semibold">Decisions</h2>
      </div>
      <Disclaimer />
      <div className="overflow-x-auto rounded-md border border-line bg-white">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-line bg-panel text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Outcome</th>
              <th className="px-3 py-2">Priority</th>
              <th className="px-3 py-2">Confidence</th>
              <th className="px-3 py-2">Blockers</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {queue.length === 0 ? (
              <tr>
                <td className="px-3 py-4 text-zinc-600" colSpan={6}>
                  No decisions requiring review. Check the Decision Center matrix for monitors.
                </td>
              </tr>
            ) : (
              queue.map((row) => (
                <tr key={row.decision_id} className="border-b border-line last:border-0">
                  <td className="px-3 py-2 font-medium">{row.symbol}</td>
                  <td className="px-3 py-2">{row.outcome}</td>
                  <td className="px-3 py-2">{row.priority}</td>
                  <td className="px-3 py-2">{row.confidence_status}</td>
                  <td className="px-3 py-2 text-amber-800">{(row.blockers || []).slice(0, 2).join(", ") || "—"}</td>
                  <td className="px-3 py-2">
                    <Link className="text-accent hover:underline" href={`/decisions/${encodeURIComponent(row.decision_id)}`}>
                      Open
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <Link className="text-sm text-accent hover:underline" href="/decision-center">
        Open classic Decision Center
      </Link>
    </div>
  );
}

export default function DecisionsPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <DecisionsContent />
    </Suspense>
  );
}
