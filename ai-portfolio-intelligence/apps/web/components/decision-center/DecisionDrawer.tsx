"use client";

import { LensGrid } from "@/components/decision-center/LensGrid";
import { ThesisEditor } from "@/components/decision-center/ThesisEditor";

type DrawerProps = {
  open: boolean;
  onClose: () => void;
  symbol?: string;
  instrumentKey?: string;
  action?: string;
  outcome?: string;
  priority?: string;
  confidenceStatus?: string;
  blockers?: string[];
  gates?: Array<{ gate_id?: string; passed?: boolean; severity?: string; blockers?: string[] }>;
  evidence?: Array<{
    evidence_id?: string;
    evidence_type?: string;
    quality_status?: string;
    provisional?: boolean;
  }>;
  scenarios?: Array<{
    scenario_id?: string;
    scenario_type?: string;
    proposed_weight_percent?: number | null;
    implementation_ready?: boolean;
    blockers?: string[];
  }>;
  lenses?: Array<{ lens_id?: string; score?: number | null; status?: string }>;
  thesisText?: string;
  accountId?: string;
};

export function DecisionDrawer({
  open,
  onClose,
  symbol,
  instrumentKey,
  action,
  outcome,
  priority,
  confidenceStatus,
  blockers = [],
  gates = [],
  evidence = [],
  scenarios = [],
  lenses = [],
  thesisText = "",
  accountId,
}: DrawerProps) {
  if (!open || !instrumentKey) return null;
  const failed = gates.filter((g) => g.passed === false);
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/20">
      <button type="button" className="flex-1" aria-label="Close drawer" onClick={onClose} />
      <aside className="h-full w-full max-w-xl overflow-y-auto border-l border-line bg-white p-5 shadow-xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">Holding decision</p>
            <h3 className="text-2xl font-semibold">{symbol}</h3>
            <p className="text-sm text-zinc-600">
              Outcome: {outcome ?? action ?? "—"} · Priority: {priority ?? "routine"} · Confidence:{" "}
              {confidenceStatus ?? "provisional"}
            </p>
          </div>
          <button type="button" className="text-sm text-zinc-500 hover:text-zinc-900" onClick={onClose}>
            Close
          </button>
        </div>

        {blockers.length ? (
          <section className="mb-4 rounded-md border border-line bg-amber-50 p-3 text-sm text-amber-900">
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">Blockers</h4>
            <ul className="list-disc pl-4">
              {blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </section>
        ) : null}

        <section className="mb-6 grid gap-2">
          <h4 className="text-sm font-semibold">Gates</h4>
          {gates.length === 0 ? (
            <p className="text-sm text-zinc-600">No gate results attached.</p>
          ) : (
            <ul className="grid gap-1 text-sm">
              {gates.map((g) => (
                <li key={g.gate_id} className="flex justify-between border-b border-line py-1">
                  <span>{g.gate_id}</span>
                  <span className={g.passed ? "text-emerald-700" : "text-amber-800"}>
                    {g.passed ? "pass" : "fail"}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {failed.length ? (
            <p className="text-xs text-zinc-500">{failed.length} gate(s) blocking implementation readiness.</p>
          ) : null}
        </section>

        <section className="mb-6 grid gap-2">
          <h4 className="text-sm font-semibold">Evidence</h4>
          {evidence.length === 0 ? (
            <p className="text-sm text-zinc-600">No evidence refs.</p>
          ) : (
            <ul className="grid gap-1 text-sm">
              {evidence.slice(0, 12).map((item) => (
                <li key={item.evidence_id} className="border-b border-line py-1">
                  {item.evidence_type} · {item.quality_status || "—"}
                  {item.provisional ? " · provisional" : ""}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="mb-6 grid gap-2">
          <h4 className="text-sm font-semibold">Scenarios</h4>
          {scenarios.length === 0 ? (
            <p className="text-sm text-zinc-600">No scenarios.</p>
          ) : (
            <ul className="grid gap-1 text-sm">
              {scenarios.map((s) => (
                <li key={s.scenario_id} className="flex justify-between border-b border-line py-1">
                  <span>{s.scenario_type}</span>
                  <span>{s.implementation_ready ? "ready" : "blocked"}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="mb-6 grid gap-2">
          <h4 className="text-sm font-semibold">Investor lenses (evidence)</h4>
          <LensGrid lenses={lenses} />
        </section>
        <section className="mb-6">
          <ThesisEditor instrumentKey={instrumentKey} initialText={thesisText} accountId={accountId} />
        </section>
        <section className="rounded-md border border-line bg-panel p-3 text-xs text-zinc-600">
          Decision Center is authoritative. Lenses and AI are evidence only. This UI does not place orders.
        </section>
      </aside>
    </div>
  );
}
