"use client";

import { Suspense, use, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { StatCard } from "@/components/StatCard";
import {
  evaluateTradePlan,
  getTradePlan,
  matchTradePlanExecution,
  transitionTradePlan,
  updateTradePlan,
} from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

type Plan = Record<string, unknown>;
type Check = { check_id: string; passed: boolean; detail: string; waived: boolean };

function str(v: unknown, f = "—"): string {
  return v === null || v === undefined || v === "" ? f : String(v);
}

function PlanDetail({ planId }: { planId: string }) {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || "MOCK-001";
  const [reloadKey, setReloadKey] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const { data, error, loading } = useClientResource(() => getTradePlan(planId), [planId, reloadKey]);
  const plan = (data ?? {}) as Plan;
  const checklist = (plan.checklist ?? null) as { checks?: Check[]; ready?: boolean; blocking?: string[] } | null;

  async function run(action: () => Promise<unknown>, ok: string) {
    setBusy(true);
    setNote(null);
    try {
      await action();
      setNote(ok);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  return (
    <div className="grid gap-6">
      <div className="flex items-end justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-accent">Trade Plan</p>
          <h2 className="text-3xl font-semibold">
            {str(plan.symbol)} · {str(plan.direction)}
          </h2>
          <p className="text-sm text-zinc-600">Status: {str(plan.status).replaceAll("_", " ")} · order generated: never</p>
        </div>
        <Link className="text-sm text-accent hover:underline" href="/trade-plans">
          ← All plans
        </Link>
      </div>
      <Disclaimer />

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Proposed qty" value={str(plan.proposed_quantity)} detail={str(plan.sizing_method, "")} />
        <StatCard label="Notional" value={plan.proposed_notional != null ? `$${Number(plan.proposed_notional).toLocaleString()}` : "—"} />
        <StatCard label="Max loss" value={plan.maximum_loss != null ? `$${Number(plan.maximum_loss).toLocaleString()}` : "—"} tone="warn" />
        <StatCard label="Invalidation" value={str(plan.invalidation_price)} />
      </section>

      {note ? <div className="rounded-md border border-line bg-panel p-3 text-sm">{note}</div> : null}

      <div className="flex flex-wrap gap-2">
        <button disabled={busy} onClick={() => run(() => evaluateTradePlan(planId, accountId), "Evaluated")} className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel disabled:opacity-50">
          Evaluate (size + checklist)
        </button>
        <button disabled={busy} onClick={() => run(() => transitionTradePlan(planId, "approve"), "Approved for manual consideration")} className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 hover:bg-emerald-100 disabled:opacity-50">
          Approve for manual consideration
        </button>
        <button disabled={busy} onClick={() => run(() => transitionTradePlan(planId, "defer"), "Deferred")} className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel disabled:opacity-50">
          Defer
        </button>
        <button disabled={busy} onClick={() => run(() => transitionTradePlan(planId, "reject"), "Rejected")} className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 hover:bg-red-100 disabled:opacity-50">
          Reject
        </button>
        <button disabled={busy} onClick={() => run(() => matchTradePlanExecution(planId), "Matched imported executions")} className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel disabled:opacity-50">
          Match imported executions
        </button>
      </div>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-line bg-white p-4">
          <h3 className="mb-3 text-lg font-semibold">Pre-trade checklist</h3>
          {checklist?.checks ? (
            <ul className="grid gap-1 text-sm">
              {checklist.checks.map((c) => (
                <li key={c.check_id} className="flex items-center justify-between">
                  <span>{c.check_id.replaceAll("_", " ")}</span>
                  <span className={c.passed ? "text-emerald-700" : c.waived ? "text-zinc-400" : "text-red-600"}>
                    {c.passed ? "pass" : c.waived ? "waived" : "blocking"}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-zinc-600">Run “Evaluate” to compute the checklist.</p>
          )}
          {checklist && !checklist.ready ? (
            <p className="mt-2 text-xs text-red-600">
              Blocking: {(checklist.blocking ?? []).join(", ") || "—"}
            </p>
          ) : null}
        </div>

        <PlanEditor
          plan={plan}
          onSaved={() => setReloadKey((k) => k + 1)}
          onError={(m) => setNote(m)}
        />
      </section>
    </div>
  );
}

function PlanEditor({
  plan,
  onSaved,
  onError,
}: {
  plan: Plan;
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  const [invalidation, setInvalidation] = useState(str(plan.invalidation_price, ""));
  const [target, setTarget] = useState(str(plan.target_high, ""));
  const [horizon, setHorizon] = useState(str(plan.holding_period, ""));
  const [ack, setAck] = useState(Boolean(plan.user_acknowledged_limitations));
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      await updateTradePlan(String(plan.trade_plan_id), {
        invalidation_price: invalidation ? Number(invalidation) : null,
        target_high: target ? Number(target) : null,
        holding_period: horizon || null,
        user_acknowledged_limitations: ack,
      });
      onSaved();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-md border border-line bg-white p-4">
      <h3 className="mb-3 text-lg font-semibold">Plan inputs</h3>
      <div className="grid gap-3 text-sm">
        <label className="grid gap-1">
          <span className="text-zinc-500">Invalidation price</span>
          <input className="rounded-md border border-line px-3 py-2" value={invalidation} onChange={(e) => setInvalidation(e.target.value)} />
        </label>
        <label className="grid gap-1">
          <span className="text-zinc-500">Target (high)</span>
          <input className="rounded-md border border-line px-3 py-2" value={target} onChange={(e) => setTarget(e.target.value)} />
        </label>
        <label className="grid gap-1">
          <span className="text-zinc-500">Holding period</span>
          <input className="rounded-md border border-line px-3 py-2" value={horizon} onChange={(e) => setHorizon(e.target.value)} placeholder="e.g. 6-12 months" />
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          <span>I acknowledge the limitations of this analysis</span>
        </label>
        <button disabled={busy} onClick={save} className="justify-self-start rounded-md border border-line px-3 py-2 hover:bg-panel disabled:opacity-50">
          {busy ? "Saving…" : "Save inputs"}
        </button>
      </div>
    </div>
  );
}

export default function TradePlanPage({ params }: { params: Promise<{ planId: string }> }) {
  const { planId } = use(params);
  return (
    <Suspense fallback={<PageLoading />}>
      <PlanDetail planId={decodeURIComponent(planId)} />
    </Suspense>
  );
}
