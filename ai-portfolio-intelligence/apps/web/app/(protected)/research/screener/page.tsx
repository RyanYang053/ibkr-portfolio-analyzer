"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import {
  createScreener,
  listScreeners,
  promoteScreenResult,
  runScreener,
} from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

type Rec = Record<string, unknown>;

const FIELDS = [
  "revenue_growth_yoy",
  "gross_margin",
  "operating_margin",
  "fcf_yield",
  "pe_forward",
] as const;

function ScreenerContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || "MOCK-001";
  const [reloadKey, setReloadKey] = useState(0);
  const [name, setName] = useState("Quality growth");
  const [field, setField] = useState<string>("revenue_growth_yoy");
  const [op, setOp] = useState("gte");
  const [value, setValue] = useState("0.1");
  const [run, setRun] = useState<Rec | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const { data } = useClientResource(() => listScreeners(accountId), [accountId, reloadKey]);
  const screens = (data?.screeners as Rec[] | undefined) ?? [];

  async function createAndRun(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNote(null);
    try {
      const created = await createScreener(accountId, {
        name,
        filters: [{ field, op, value: Number(value) }],
      });
      const result = await runScreener(String(created.screen_id), accountId);
      setRun(result);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Screen failed");
    } finally {
      setBusy(false);
    }
  }

  async function promote(resultId: string) {
    try {
      await promoteScreenResult(resultId, accountId);
      setNote(`Promoted ${resultId} to the research queue.`);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Promote failed");
    }
  }

  const results = (run?.results as Rec[] | undefined) ?? [];

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Screener</p>
        <h2 className="text-3xl font-semibold">Surface research candidates</h2>
        <p className="text-sm text-zinc-600">
          Screens your holdings and watchlist. Results are research candidates, never buy
          recommendations — a filter over unavailable data is shown as missing, not passed.
        </p>
        <Link className="text-sm text-accent hover:underline" href="/research">← Research</Link>
      </div>
      <Disclaimer />

      <form onSubmit={createAndRun} className="grid gap-3 rounded-md border border-line bg-white p-4 md:grid-cols-5">
        <input className="rounded-md border border-line px-3 py-2 text-sm md:col-span-2" value={name} onChange={(e) => setName(e.target.value)} aria-label="Screen name" />
        <select className="rounded-md border border-line px-3 py-2 text-sm" value={field} onChange={(e) => setField(e.target.value)} aria-label="Field">
          {FIELDS.map((f) => <option key={f} value={f}>{f.replaceAll("_", " ")}</option>)}
        </select>
        <select className="rounded-md border border-line px-3 py-2 text-sm" value={op} onChange={(e) => setOp(e.target.value)} aria-label="Operator">
          <option value="gte">≥</option>
          <option value="lte">≤</option>
          <option value="gt">&gt;</option>
          <option value="lt">&lt;</option>
        </select>
        <div className="flex gap-2">
          <input className="w-20 rounded-md border border-line px-3 py-2 text-sm" value={value} onChange={(e) => setValue(e.target.value)} aria-label="Value" />
          <button type="submit" disabled={busy} className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel disabled:opacity-50">
            {busy ? "…" : "Run"}
          </button>
        </div>
      </form>
      {note ? <PageErrorBanner message={note} /> : null}

      {run ? (
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 text-lg font-semibold">
            Results · {results.length} candidate(s) · universe {String(run.universe_size)}
          </h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-zinc-500">
                <th className="py-1">#</th>
                <th>Symbol</th>
                <th>Matched</th>
                <th>Missing</th>
                <th>Fit</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={String(r.result_id)} className="border-t border-line">
                  <td className="py-1">{String(r.rank)}</td>
                  <td className="font-semibold">
                    <Link className="text-accent hover:underline" href={`/securities/${encodeURIComponent(String(r.instrument_id))}`}>
                      {String(r.symbol)}
                    </Link>
                  </td>
                  <td>{((r.matched_criteria as string[]) ?? []).length}</td>
                  <td className={((r.missing_data as string[]) ?? []).length ? "text-amber-700" : ""}>
                    {((r.missing_data as string[]) ?? []).join(", ") || "—"}
                  </td>
                  <td>{(r.portfolio_fit as Rec)?.already_owned ? "owned" : "new"}</td>
                  <td>
                    <button onClick={() => promote(String(r.result_id))} className="rounded-md border border-line px-2 py-1 text-xs hover:bg-panel">
                      → research queue
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {screens.length > 0 ? (
        <p className="text-xs text-zinc-500">{screens.length} saved screen(s).</p>
      ) : null}
    </div>
  );
}

export default function ScreenerPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <ScreenerContent />
    </Suspense>
  );
}
