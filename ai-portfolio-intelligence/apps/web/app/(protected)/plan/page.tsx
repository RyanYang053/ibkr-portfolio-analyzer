"use client";

import { useState } from "react";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getFinancialPlan, getPlanFeasibility, requireJson } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

export default function PlanPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const { data, error, loading } = useClientResource(
    () =>
      Promise.all([
        getFinancialPlan(),
        getPlanFeasibility().catch(() => ({ feasibility: [] as Array<Record<string, unknown>> })),
      ]),
    [refreshKey],
  );

  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  const [plan, feasibilityPayload] = data ?? [{}, { feasibility: [] }];
  const goals = (plan?.goals as Array<Record<string, unknown>> | undefined) ?? [];
  const roles = (plan?.account_roles as Array<Record<string, unknown>> | undefined) ?? [];
  const policy = (plan?.policy as Record<string, unknown> | undefined) ?? null;
  const feasibility = Array.isArray(feasibilityPayload?.feasibility)
    ? (feasibilityPayload.feasibility as Array<Record<string, unknown>>)
    : Array.isArray(plan?.feasibility)
      ? (plan.feasibility as Array<Record<string, unknown>>)
      : [];
  const exists = plan?.exists !== false && (plan?.plan_id || policy || goals.length);

  async function createDefaultPlan() {
    setBusy(true);
    setNote(null);
    try {
      await requireJson("/planning/plan?plan_id=default", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          owner_label: "personal",
          base_currency: "USD",
          planning_horizon_years: 20,
          goals: [
            {
              goal_id: "retirement",
              name: "Retirement",
              goal_type: "retirement",
              target_amount: 1000000,
              currency: "USD",
              priority: 1,
              funded_amount: 0,
              status: "active",
            },
          ],
          account_roles: [
            {
              account_id: "primary",
              role: "growth",
              tax_wrapper: "taxable",
              contribution_priority: 1,
            },
          ],
          policy: {
            policy_id: "default",
            version: "1.0.0",
            risk_tolerance: "moderate",
            max_single_position_pct: 12,
            max_sector_pct: 35,
            max_speculative_pct: 5,
            min_cash_pct: 10,
            rebalance_band_pct: 5,
            tax_loss_harvesting: false,
            constraints: { core_etf: "VOO" },
          },
          notes: "Created from Plan UI",
        }),
      });
      setNote("Default financial plan saved.");
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Unable to save plan");
    } finally {
      setBusy(false);
    }
  }

  async function addEmergencyGoal() {
    setBusy(true);
    setNote(null);
    try {
      await requireJson("/planning/goals?plan_id=default", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal_id: `emergency_${Date.now()}`,
          name: "Emergency reserve",
          goal_type: "emergency",
          target_amount: 50000,
          currency: "USD",
          priority: 1,
          funded_amount: 0,
          status: "active",
        }),
      });
      setNote("Goal added.");
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Unable to add goal");
    } finally {
      setBusy(false);
    }
  }

  async function deleteGoal(goalId: string) {
    setBusy(true);
    setNote(null);
    try {
      await requireJson(`/planning/goals/${encodeURIComponent(goalId)}?plan_id=default`, {
        method: "DELETE",
      });
      setNote(`Deleted goal ${goalId}`);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Unable to delete goal");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Financial plan</p>
        <h2 className="text-3xl font-semibold">Plan & Policy</h2>
      </div>
      <Disclaimer />
      {!exists ? (
        <div className="rounded-md border border-line bg-white p-4 text-sm text-zinc-700">
          <p>No plan yet. Create a starter plan with moderate risk defaults.</p>
          <button
            type="button"
            className="mt-3 rounded-md border border-line px-3 py-2 hover:bg-panel disabled:opacity-50"
            onClick={createDefaultPlan}
            disabled={busy}
          >
            {busy ? "Saving…" : "Create default plan"}
          </button>
          {note ? <p className="mt-2 text-amber-800">{note}</p> : null}
        </div>
      ) : (
        <>
          <section className="rounded-md border border-line bg-white p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-semibold">Goals</h3>
              <button
                type="button"
                className="rounded-md border border-line px-2 py-1 text-xs hover:bg-panel disabled:opacity-50"
                onClick={addEmergencyGoal}
                disabled={busy}
              >
                Add emergency goal
              </button>
            </div>
            {goals.length === 0 ? (
              <p className="text-sm text-zinc-600">No goals defined.</p>
            ) : (
              <ul className="grid gap-2 text-sm">
                {goals.map((g) => (
                  <li key={String(g.goal_id)} className="flex items-start justify-between gap-3 border-b border-line py-2">
                    <div>
                      <div className="font-medium">{String(g.name)}</div>
                      <div className="text-zinc-600">
                        Target {String(g.target_amount)} {String(g.currency || "")} · Funded{" "}
                        {String(g.funded_amount ?? 0)}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="text-xs text-amber-800 hover:underline disabled:opacity-50"
                      onClick={() => deleteGoal(String(g.goal_id))}
                      disabled={busy}
                    >
                      Delete
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="rounded-md border border-line bg-white p-4">
            <h3 className="mb-3 font-semibold">Goal feasibility</h3>
            {feasibility.length === 0 ? (
              <p className="text-sm text-zinc-600">No feasibility assessments yet.</p>
            ) : (
              <ul className="grid gap-2 text-sm">
                {feasibility.map((row) => (
                  <li key={String(row.goal_id)} className="border-b border-line py-2">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-medium">{String(row.goal_id)}</div>
                        <div className="text-zinc-600">
                          Projected {String(row.projected_funded_amount ?? "—")} · Shortfall{" "}
                          {String(row.shortfall ?? "—")}
                          {row.required_monthly_contribution != null
                            ? ` · Required monthly ${String(row.required_monthly_contribution)}`
                            : ""}
                        </div>
                        {Array.isArray(row.blockers) && (row.blockers as string[]).length ? (
                          <div className="mt-1 text-amber-800">
                            {(row.blockers as string[]).join(", ")}
                          </div>
                        ) : null}
                      </div>
                      <span className={row.feasible ? "text-emerald-700" : "text-amber-800"}>
                        {row.feasible ? "feasible" : "shortfall"}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="rounded-md border border-line bg-white p-4">
            <h3 className="mb-3 font-semibold">Account roles</h3>
            {roles.length === 0 ? (
              <p className="text-sm text-zinc-600">No account roles mapped.</p>
            ) : (
              <ul className="grid gap-2 text-sm">
                {roles.map((role) => (
                  <li key={String(role.account_id)} className="border-b border-line py-2">
                    {String(role.account_id)} · {String(role.role)}
                    {role.tax_wrapper ? ` · ${String(role.tax_wrapper)}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="rounded-md border border-line bg-white p-4">
            <h3 className="mb-3 font-semibold">Investment policy</h3>
            {policy ? (
              <dl className="grid gap-2 text-sm md:grid-cols-2">
                <div>Risk: {String(policy.risk_tolerance)}</div>
                <div>Max single position: {String(policy.max_single_position_pct)}%</div>
                <div>Max sector: {String(policy.max_sector_pct)}%</div>
                <div>Min cash: {String(policy.min_cash_pct)}%</div>
              </dl>
            ) : (
              <p className="text-sm text-zinc-600">No policy on file.</p>
            )}
          </section>
          {note ? <p className="text-sm text-zinc-600">{note}</p> : null}
        </>
      )}
    </div>
  );
}
