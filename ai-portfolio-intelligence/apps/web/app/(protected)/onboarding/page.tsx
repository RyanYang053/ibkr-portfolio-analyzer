"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import {
  getBrokerStatus,
  getDataHealth,
  getDecisionQueue,
  getFinancialPlan,
  getOnboardingState,
  updateOnboardingStage,
} from "@/lib/api";

// Each step maps to a persisted backend stage (§21). SQLite is the source of
// truth — not localStorage — so setup survives reinstalls.
const STEPS = [
  { id: "data_location", stage: "local_storage", title: "Application data location", href: "/settings", detail: "Confirm local Application Support path and backups." },
  { id: "base_currency", stage: "currency_locale", title: "Base currency", href: "/plan", detail: "Set reporting currency in the financial plan." },
  { id: "tax_jurisdiction", stage: "tax_residency", title: "Tax jurisdiction", href: "/plan", detail: "Record Canada / US / other for tax-lot methods." },
  { id: "account_roles", stage: "account_role_mapping", title: "Account roles", href: "/plan", detail: "Map each account to growth, income, or tax wrapper roles." },
  { id: "ibkr", stage: "ibkr_connection", title: "IBKR connection", href: "/settings", detail: "Connect Gateway in read-only mode." },
  { id: "flex", stage: "flex_configuration", title: "Flex token", href: "/settings", detail: "Store Flex token in the OS keychain." },
  { id: "historical_import", stage: "historical_import", title: "Historical import", href: "/data-health", detail: "Import activity and verify ledger coverage." },
  { id: "affiliated", stage: "reconciliation", title: "Reconciliation", href: "/plan", detail: "Reconcile transactions and tax lots; list affiliated accounts." },
  { id: "plan_basics", stage: "financial_goals", title: "Financial-plan basics", href: "/plan", detail: "Emergency reserve, contributions, drawdown limit." },
  { id: "backup", stage: "backup_creation", title: "Backup configuration", href: "/settings", detail: "Enable encrypted backups and restore verification." },
  { id: "data_health", stage: "data_health_validation", title: "Initial data-health check", href: "/data-health", detail: "Confirm broker sync, methodology, and job status." },
  { id: "first_packet", stage: "first_decision_packet", title: "First packet evaluation", href: "/decisions", detail: "Open the decision queue. No orders are generated." },
] as const;

type BoolMap = Record<string, boolean>;

export default function ProtectedOnboardingPage() {
  const [persisted, setPersisted] = useState<BoolMap>({});
  const [detected, setDetected] = useState<BoolMap>({});
  const [readiness, setReadiness] = useState<Record<string, number>>({});

  const loadState = useCallback(async () => {
    try {
      const state = await getOnboardingState();
      const stages = (state.stages as Array<Record<string, unknown>> | undefined) ?? [];
      const map: BoolMap = {};
      for (const s of stages) {
        if (s.status === "complete") map[String(s.stage)] = true;
      }
      setPersisted(map);
      setReadiness((state.readiness as Record<string, number>) ?? {});
    } catch {
      setPersisted({});
    }
  }, []);

  useEffect(() => {
    void loadState();
  }, [loadState]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next: BoolMap = {};
      try {
        const broker = await getBrokerStatus();
        next.ibkr_connection = String(broker.status || "").toLowerCase().includes("connected") || broker.mode === "mock_ibkr_readonly";
        next.flex_configuration = Boolean((broker as { flex_configured?: boolean }).flex_configured);
      } catch {
        next.ibkr_connection = false;
      }
      try {
        const plan = await getFinancialPlan();
        const hasPlan = Boolean(plan && (plan.plan_id || plan.base_currency));
        next.currency_locale = hasPlan && Boolean(plan.base_currency);
        next.financial_goals = hasPlan;
        next.account_role_mapping = Array.isArray(plan.account_roles) && plan.account_roles.length > 0;
      } catch {
        next.financial_goals = false;
      }
      try {
        const health = await getDataHealth();
        next.data_health_validation = String(health.overall_status || "") !== "attention_required";
        next.historical_import = Array.isArray(health.checks)
          ? (health.checks as Array<Record<string, string>>).some((c) => c.id === "ledger" || c.id === "broker")
          : false;
        next.backup_creation = Array.isArray(health.checks)
          ? (health.checks as Array<Record<string, string>>).some((c) => c.id === "backup")
          : false;
        next.local_storage = true;
      } catch {
        next.data_health_validation = false;
      }
      try {
        const queue = await getDecisionQueue();
        next.first_decision_packet = Array.isArray(queue.queue) && queue.queue.length > 0;
      } catch {
        next.first_decision_packet = false;
      }
      if (!cancelled) setDetected(next);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const effective = useMemo(() => {
    const merged: BoolMap = { ...persisted };
    for (const [key, value] of Object.entries(detected)) {
      if (value) merged[key] = true;
    }
    return merged;
  }, [persisted, detected]);

  const completedCount = useMemo(
    () => STEPS.filter((step) => effective[step.stage]).length,
    [effective],
  );

  async function markDone(stage: string) {
    setPersisted((prev) => ({ ...prev, [stage]: true }));
    try {
      await updateOnboardingStage(stage, "complete");
      await loadState();
    } catch {
      /* keep optimistic state; will reconcile on next load */
    }
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Onboarding</p>
        <h2 className="text-3xl font-semibold">Personal Decision OS setup</h2>
        <p className="text-sm text-zinc-600">
          Local single-owner mode. No login. Read-only forever. Progress {completedCount}/{STEPS.length}. Saved to
          SQLite, not the browser.
        </p>
      </div>
      <Disclaimer />

      {Object.keys(readiness).length ? (
        <section className="grid gap-2 rounded-md border border-line bg-white p-4 md:grid-cols-3 xl:grid-cols-6">
          {["portfolio_data", "tax_data", "research", "decision", "backup", "overall"].map((key) => (
            <div key={key} className="text-sm">
              <div className="text-xs uppercase tracking-wide text-zinc-500">{key.replaceAll("_", " ")}</div>
              <div className="text-lg font-semibold">{Math.round((readiness[key] ?? 0) * 100)}%</div>
            </div>
          ))}
        </section>
      ) : null}

      <ol className="space-y-3">
        {STEPS.map((step, index) => (
          <li key={step.id} className="rounded-md border border-line bg-white p-4 text-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold">
                  {index + 1}. {step.title}
                  {effective[step.stage] ? " (done)" : ""}
                  {detected[step.stage] && !persisted[step.stage] ? " · auto-detected" : ""}
                </div>
                <p className="mt-1 text-zinc-700">{step.detail}</p>
                <Link className="mt-2 inline-block text-accent hover:underline" href={step.href}>
                  Open
                </Link>
              </div>
              <button
                type="button"
                className="shrink-0 rounded-md border border-line px-2 py-1 text-xs hover:bg-panel"
                onClick={() => markDone(step.stage)}
                disabled={Boolean(effective[step.stage])}
              >
                {effective[step.stage] ? "Completed" : "Mark done"}
              </button>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
