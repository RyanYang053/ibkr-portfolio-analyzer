"use client";

import { useEffect, useMemo, useState } from "react";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { getBrokerStatus, getDataHealth, getDecisionQueue, getFinancialPlan } from "@/lib/api";

const STEPS = [
  { id: "data_location", title: "Application data location", href: "/settings", detail: "Confirm local Application Support path and backups." },
  { id: "base_currency", title: "Base currency", href: "/plan", detail: "Set reporting currency in the financial plan." },
  { id: "tax_jurisdiction", title: "Tax jurisdiction", href: "/plan", detail: "Record Canada / US / other for tax-lot methods." },
  { id: "account_roles", title: "Account roles", href: "/plan", detail: "Map each account to growth, income, or tax wrapper roles." },
  { id: "ibkr", title: "IBKR connection", href: "/settings", detail: "Connect Gateway in read-only mode." },
  { id: "flex", title: "Flex token", href: "/settings", detail: "Store Flex token in the OS keychain." },
  { id: "historical_import", title: "Historical import", href: "/data-health", detail: "Import activity and verify ledger coverage." },
  { id: "affiliated", title: "Affiliated accounts", href: "/plan", detail: "List related accounts for wash-sale / superficial-loss evidence." },
  { id: "plan_basics", title: "Financial-plan basics", href: "/plan", detail: "Emergency reserve, contributions, drawdown limit." },
  { id: "backup", title: "Backup configuration", href: "/settings", detail: "Enable encrypted backups and restore verification." },
  { id: "data_health", title: "Initial data-health check", href: "/data-health", detail: "Confirm broker sync, methodology, and job status." },
  { id: "first_packet", title: "First packet evaluation", href: "/decisions", detail: "Open the decision queue. No orders are generated." },
] as const;

const STORAGE_KEY = "decision_os_onboarding_done";

export default function ProtectedOnboardingPage() {
  const [done, setDone] = useState<Record<string, boolean>>(() => {
    if (typeof window === "undefined") return {};
    try {
      return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}") as Record<string, boolean>;
    } catch {
      return {};
    }
  });
  const [detected, setDetected] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next: Record<string, boolean> = {};
      try {
        const broker = await getBrokerStatus();
        next.ibkr = String(broker.status || "").toLowerCase().includes("connected") || broker.mode === "mock_ibkr_readonly";
        next.flex = Boolean((broker as { flex_configured?: boolean }).flex_configured);
      } catch {
        next.ibkr = false;
      }
      try {
        const plan = await getFinancialPlan();
        const hasPlan = Boolean(plan && (plan.plan_id || plan.base_currency));
        next.base_currency = hasPlan && Boolean(plan.base_currency);
        next.plan_basics = hasPlan;
        next.account_roles = Array.isArray(plan.account_roles) && plan.account_roles.length > 0;
        next.tax_jurisdiction = Boolean(
          (plan as { tax_jurisdiction?: string }).tax_jurisdiction ||
            (plan.policy as { constraints?: Record<string, unknown> } | null)?.constraints?.tax_jurisdiction,
        );
        next.affiliated = Array.isArray((plan as { affiliated_accounts?: unknown[] }).affiliated_accounts)
          ? Boolean(((plan as { affiliated_accounts?: unknown[] }).affiliated_accounts || []).length)
          : false;
      } catch {
        next.plan_basics = false;
      }
      try {
        const health = await getDataHealth();
        next.data_health = String(health.overall_status || "") !== "attention_required";
        next.historical_import = Array.isArray(health.checks)
          ? (health.checks as Array<Record<string, string>>).some(
              (c) => c.id === "ledger" || c.id === "broker",
            )
          : false;
        next.backup = Array.isArray(health.checks)
          ? (health.checks as Array<Record<string, string>>).some((c) => c.id === "backup")
          : false;
        next.data_location = true;
      } catch {
        next.data_health = false;
      }
      try {
        const queue = await getDecisionQueue();
        next.first_packet = Array.isArray(queue.queue) && queue.queue.length > 0;
      } catch {
        next.first_packet = false;
      }
      if (!cancelled) setDetected(next);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const effective = useMemo(() => {
    const merged: Record<string, boolean> = { ...done };
    for (const [key, value] of Object.entries(detected)) {
      if (value) merged[key] = true;
    }
    return merged;
  }, [done, detected]);

  const completedCount = useMemo(
    () => STEPS.filter((step) => effective[step.id]).length,
    [effective],
  );

  function markDone(id: string) {
    const next = { ...done, [id]: true };
    setDone(next);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Onboarding</p>
        <h2 className="text-3xl font-semibold">Personal Decision OS setup</h2>
        <p className="text-sm text-zinc-600">
          Local single-owner mode. No login. Read-only forever. Progress {completedCount}/{STEPS.length}.
        </p>
      </div>
      <Disclaimer />
      <ol className="space-y-3">
        {STEPS.map((step, index) => (
          <li key={step.id} className="rounded-md border border-line bg-white p-4 text-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold">
                  {index + 1}. {step.title}
                  {effective[step.id] ? " (done)" : ""}
                  {detected[step.id] && !done[step.id] ? " · auto-detected" : ""}
                </div>
                <p className="mt-1 text-zinc-700">{step.detail}</p>
                <Link className="mt-2 inline-block text-accent hover:underline" href={step.href}>
                  Open
                </Link>
              </div>
              <button
                type="button"
                className="shrink-0 rounded-md border border-line px-2 py-1 text-xs hover:bg-panel"
                onClick={() => markDone(step.id)}
                disabled={Boolean(effective[step.id])}
              >
                {effective[step.id] ? "Completed" : "Mark done"}
              </button>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
