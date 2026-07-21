"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { createTradePlan, listTradePlans } from "@/lib/api";
import { useAppRouter } from "@/lib/use-app-router";
import { useClientResource } from "@/lib/use-client-resource";

type Plan = Record<string, unknown>;

const STATUS_TONE: Record<string, string> = {
  draft: "bg-zinc-100 text-zinc-700",
  under_review: "bg-amber-100 text-amber-800",
  approved_for_manual_consideration: "bg-emerald-100 text-emerald-800",
  rejected: "bg-red-100 text-red-700",
  deferred: "bg-blue-100 text-blue-700",
};

function TradePlansContent() {
  const router = useAppRouter();
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || "MOCK-001";
  const [reloadKey, setReloadKey] = useState(0);
  const [instrumentId, setInstrumentId] = useState("");
  const [direction, setDirection] = useState("buy");
  const [sizing, setSizing] = useState("fixed_percent");
  const [riskPct, setRiskPct] = useState("2");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const { data, error, loading } = useClientResource(
    () => listTradePlans(accountId),
    [accountId, reloadKey],
  );

  const plans = (data?.trade_plans as Plan[] | undefined) ?? [];

  async function onCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!instrumentId.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      const created = await createTradePlan({
        account_id: accountId,
        instrument_id: instrumentId.trim().toUpperCase(),
        direction,
        sizing_method: sizing,
        risk_budget_pct: Number(riskPct) || null,
      });
      router.push(`/trade-plans/${encodeURIComponent(String(created.trade_plan_id))}`);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Failed to create plan");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Trade Plans</p>
        <h2 className="text-3xl font-semibold">Plan, size, and review — never execute</h2>
        <p className="text-sm text-zinc-600">
          Trade Plans are auditable intentions. The strongest state is “approved for manual
          consideration”; execution stays in your broker.
        </p>
      </div>
      <Disclaimer />

      <form onSubmit={onCreate} className="grid gap-3 rounded-md border border-line bg-white p-4 md:grid-cols-5">
        <input
          className="rounded-md border border-line px-3 py-2 text-sm md:col-span-2"
          placeholder="Instrument id (e.g. MSFT or MSFT:272093)"
          value={instrumentId}
          onChange={(e) => setInstrumentId(e.target.value)}
          aria-label="Instrument id"
        />
        <select className="rounded-md border border-line px-3 py-2 text-sm" value={direction} onChange={(e) => setDirection(e.target.value)} aria-label="Direction">
          <option value="buy">Buy</option>
          <option value="add">Add</option>
          <option value="trim">Trim</option>
          <option value="exit">Exit</option>
        </select>
        <select className="rounded-md border border-line px-3 py-2 text-sm" value={sizing} onChange={(e) => setSizing(e.target.value)} aria-label="Sizing method">
          <option value="fixed_percent">Fixed %</option>
          <option value="max_loss">Max loss</option>
          <option value="atr">ATR</option>
          <option value="volatility">Volatility</option>
          <option value="user_entered">User entered</option>
        </select>
        <div className="flex gap-2">
          <input
            className="w-20 rounded-md border border-line px-3 py-2 text-sm"
            placeholder="risk %"
            value={riskPct}
            onChange={(e) => setRiskPct(e.target.value)}
            aria-label="Risk budget percent"
          />
          <button type="submit" disabled={busy} className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel disabled:opacity-50">
            {busy ? "…" : "Draft"}
          </button>
        </div>
      </form>
      {note ? <PageErrorBanner message={note} /> : null}

      {loading ? <PageLoading /> : null}
      {error ? <PageErrorBanner message={error} /> : null}

      {!loading && !error ? (
        <div className="grid gap-2">
          {plans.length === 0 ? (
            <p className="text-sm text-zinc-600">No trade plans yet. Draft one above.</p>
          ) : (
            plans.map((plan) => (
              <Link
                key={String(plan.trade_plan_id)}
                href={`/trade-plans/${encodeURIComponent(String(plan.trade_plan_id))}`}
                className="flex items-center justify-between rounded-md border border-line bg-white p-3 hover:bg-panel"
              >
                <div>
                  <div className="text-sm font-semibold">
                    {String(plan.symbol)} · {String(plan.direction)}
                  </div>
                  <p className="text-xs text-zinc-600">
                    Qty {String(plan.proposed_quantity ?? "—")} · Max loss {String(plan.maximum_loss ?? "—")}
                  </p>
                </div>
                <span className={`rounded-full px-2 py-1 text-xs ${STATUS_TONE[String(plan.status)] ?? "bg-zinc-100 text-zinc-700"}`}>
                  {String(plan.status).replaceAll("_", " ")}
                </span>
              </Link>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function TradePlansPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <TradePlansContent />
    </Suspense>
  );
}
