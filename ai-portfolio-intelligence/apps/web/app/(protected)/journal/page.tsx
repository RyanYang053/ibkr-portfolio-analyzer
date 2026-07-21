"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Disclaimer } from "@/components/Disclaimer";
import { DegradedStateBanner } from "@/components/DegradedStateBanner";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { StatCard } from "@/components/StatCard";
import {
  addJournalReview,
  createJournalEntry,
  getJournalAnalytics,
  listJournal,
  updateJournalEntry,
} from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

type Entry = Record<string, unknown>;

function str(v: unknown, f = "—"): string {
  return v === null || v === undefined || v === "" ? f : String(v);
}
function pct(v: unknown): string {
  return v === null || v === undefined ? "—" : `${(Number(v) * 100).toFixed(1)}%`;
}

function JournalContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || "MOCK-001";
  const [reloadKey, setReloadKey] = useState(0);
  const [thesis, setThesis] = useState("");
  const [instrument, setInstrument] = useState("");
  const [note, setNote] = useState<string | null>(null);

  const { data, error, loading } = useClientResource(
    () => Promise.all([listJournal(accountId), getJournalAnalytics(accountId)]),
    [accountId, reloadKey],
  );
  const [entriesData, analytics] = data ?? [null, null];
  const entries = (entriesData?.entries as Entry[] | undefined) ?? [];
  const metrics = (analytics?.metrics ?? null) as Record<string, unknown> | null;
  const analyticsStatus = str(analytics?.status);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!instrument.trim()) return;
    setNote(null);
    try {
      await createJournalEntry({
        account_id: accountId,
        instrument_id: instrument.trim().toUpperCase(),
        entry_thesis: thesis,
      });
      setThesis("");
      setInstrument("");
      setReloadKey((k) => k + 1);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Failed to create entry");
    }
  }

  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Trade Journal</p>
        <h2 className="text-3xl font-semibold">Learn from your process</h2>
        <p className="text-sm text-zinc-600">
          These metrics evaluate decision quality — not trade frequency. They are withheld until
          there are enough closed trades to be meaningful.
        </p>
      </div>
      <Disclaimer />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {metrics ? (
          <>
            <StatCard label="Win rate" value={pct(metrics.win_rate)} detail={`${str(analytics?.closed_count)} closed`} />
            <StatCard label="Expectancy" value={pct(metrics.expectancy)} tone={Number(metrics.expectancy) >= 0 ? "good" : "warn"} />
            <StatCard label="Payoff ratio" value={str(metrics.payoff_ratio)} />
            <StatCard label="Plan adherence" value={metrics.plan_adherence_rate != null ? pct(metrics.plan_adherence_rate) : "—"} />
          </>
        ) : (
          <div className="md:col-span-4">
            <DegradedStateBanner
              message={
                analyticsStatus === "insufficient_sample"
                  ? "Not enough closed trades yet — process analytics are withheld rather than shown on a tiny sample."
                  : "Process analytics are unavailable."
              }
            />
          </div>
        )}
      </section>

      <form onSubmit={create} className="grid gap-3 rounded-md border border-line bg-white p-4 md:grid-cols-3">
        <input className="rounded-md border border-line px-3 py-2 text-sm" placeholder="Instrument id (e.g. MSFT)" value={instrument} onChange={(e) => setInstrument(e.target.value)} aria-label="Instrument" />
        <input className="rounded-md border border-line px-3 py-2 text-sm md:col-span-1" placeholder="Entry thesis" value={thesis} onChange={(e) => setThesis(e.target.value)} aria-label="Entry thesis" />
        <button type="submit" className="justify-self-start rounded-md border border-line px-3 py-2 text-sm hover:bg-panel">New entry</button>
      </form>
      {note ? <PageErrorBanner message={note} /> : null}

      <div className="grid gap-2">
        {entries.length === 0 ? (
          <p className="text-sm text-zinc-600">No journal entries yet.</p>
        ) : (
          entries.map((entry) => (
            <JournalRow key={String(entry.entry_id)} entry={entry} onChanged={() => setReloadKey((k) => k + 1)} />
          ))
        )}
      </div>
    </div>
  );
}

function JournalRow({ entry, onChanged }: { entry: Entry; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [ret, setRet] = useState("");
  const [outcome, setOutcome] = useState("win_good_process");
  const [reviewNote, setReviewNote] = useState("");
  const closed = entry.realized_return != null;

  async function close() {
    await updateJournalEntry(String(entry.entry_id), {
      realized_return: ret ? Number(ret) / 100 : null,
      outcome_classification: outcome,
      exit_price: null,
    });
    onChanged();
  }
  async function review() {
    await addJournalReview(String(entry.entry_id), { interval: "thirty_day", note: reviewNote });
    setReviewNote("");
    onChanged();
  }

  return (
    <div className="rounded-md border border-line bg-white p-3">
      <button type="button" className="flex w-full items-center justify-between text-left" onClick={() => setOpen((v) => !v)}>
        <div>
          <div className="text-sm font-semibold">{str(entry.symbol)}</div>
          <p className="text-xs text-zinc-600">{str(entry.entry_thesis, "no thesis")}</p>
        </div>
        <span className="rounded-full bg-zinc-100 px-2 py-1 text-xs text-zinc-700">
          {str(entry.outcome_classification).replaceAll("_", " ")}
          {closed ? ` · ${pct(entry.realized_return)}` : ""}
        </span>
      </button>
      {open ? (
        <div className="mt-3 grid gap-3 border-t border-line pt-3 text-sm md:grid-cols-2">
          {!closed ? (
            <div className="grid gap-2">
              <span className="text-zinc-500">Close trade</span>
              <div className="flex gap-2">
                <input className="w-24 rounded-md border border-line px-2 py-1" placeholder="return %" value={ret} onChange={(e) => setRet(e.target.value)} aria-label="Return percent" />
                <select className="rounded-md border border-line px-2 py-1" value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label="Outcome">
                  <option value="win_good_process">Win · good process</option>
                  <option value="win_lucky">Win · lucky</option>
                  <option value="loss_good_process">Loss · good process</option>
                  <option value="loss_mistake">Loss · mistake</option>
                  <option value="scratch">Scratch</option>
                </select>
                <button onClick={close} className="rounded-md border border-line px-2 py-1 hover:bg-panel">Close</button>
              </div>
            </div>
          ) : (
            <div className="grid gap-2">
              <span className="text-zinc-500">Add review</span>
              <div className="flex gap-2">
                <input className="flex-1 rounded-md border border-line px-2 py-1" placeholder="review note" value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} aria-label="Review note" />
                <button onClick={review} className="rounded-md border border-line px-2 py-1 hover:bg-panel">Review</button>
              </div>
              <p className="text-xs text-zinc-500">{((entry.reviews as unknown[]) ?? []).length} review(s)</p>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function JournalPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <JournalContent />
    </Suspense>
  );
}
