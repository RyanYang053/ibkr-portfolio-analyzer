"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getDecisionQueue } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";
import { requireJson } from "@/lib/api";

function HistoryContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const [instrumentKey, setInstrumentKey] = useState("");
  const [history, setHistory] = useState<Array<Record<string, unknown>> | null>(null);
  const [observations, setObservations] = useState<Array<Record<string, unknown>> | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const { data, error, loading } = useClientResource(() => getDecisionQueue(accountId), [accountId]);

  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  const queue = data?.queue ?? [];

  async function loadHistory(key: string) {
    setInstrumentKey(key);
    setHistoryError(null);
    try {
      const query = accountId ? `?account_id=${encodeURIComponent(accountId)}` : "";
      const payload = await requireJson<{
        history?: Array<Record<string, unknown>>;
        observations?: Array<Record<string, unknown>>;
      }>(`/decisions/history/${encodeURIComponent(key)}${query}`);
      setHistory(payload.history ?? []);
      setObservations(payload.observations ?? []);
    } catch (err) {
      setHistory([]);
      setObservations([]);
      setHistoryError(err instanceof Error ? err.message : "Unable to load history");
    }
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">History</p>
        <h2 className="text-3xl font-semibold">Decision and outcome history</h2>
      </div>
      <Disclaimer />
      <section className="rounded-md border border-line bg-white p-4">
        <h3 className="mb-3 font-semibold">Recent decision queue instruments</h3>
        <div className="flex flex-wrap gap-2">
          {queue.length === 0 ? (
            <p className="text-sm text-zinc-600">No queue items. Open Decision Center after sync.</p>
          ) : (
            queue.map((row) => (
              <button
                key={row.decision_id}
                type="button"
                className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-panel"
                onClick={() => loadHistory(row.instrument_key)}
              >
                {row.symbol}
              </button>
            ))
          )}
        </div>
      </section>
      {instrumentKey ? (
        <section className="rounded-md border border-line bg-white p-4 text-sm">
          <h3 className="mb-3 font-semibold">History for {instrumentKey}</h3>
          {historyError ? <PageErrorBanner message={historyError} /> : null}
          {history && history.length === 0 ? (
            <p className="text-zinc-600">No stored outcome transitions yet.</p>
          ) : (
            <ul className="space-y-2">
              {(history || []).map((row, idx) => (
                <li key={`${row.decision_id}-${idx}`} className="border-b border-line py-2">
                  <div className="font-medium">
                    {String(row.previous_outcome || "—")} → {String(row.outcome || "—")}
                  </div>
                  <div className="text-xs text-zinc-600">
                    {String(row.decision_id || "")} · {String(row.recorded_at || row.as_of || "")}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <h4 className="mb-2 mt-5 font-semibold">Observation windows</h4>
          {observations && observations.length === 0 ? (
            <p className="text-zinc-600">No 30/90/180/365 observation windows recorded yet.</p>
          ) : (
            <ul className="space-y-2">
              {(observations || []).map((row, idx) => (
                <li key={`${row.window_days}-${idx}`} className="border-b border-line py-2">
                  <div className="font-medium">
                    {String(row.window_days || row.window || "—")} day window ·{" "}
                    {String(row.label || row.realized_label || "pending")}
                  </div>
                  <div className="text-xs text-zinc-600">
                    {String(row.decision_id || "")} · {String(row.recorded_at || row.as_of || "")}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
      <Link className="text-sm text-accent hover:underline" href="/decisions">
        Back to decision queue
      </Link>
    </div>
  );
}

export default function HistoryPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <HistoryContent />
    </Suspense>
  );
}
