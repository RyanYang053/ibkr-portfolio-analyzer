"use client";

import { LensGrid } from "@/components/decision-center/LensGrid";
import { ThesisEditor } from "@/components/decision-center/ThesisEditor";

type DrawerProps = {
  open: boolean;
  onClose: () => void;
  symbol?: string;
  instrumentKey?: string;
  action?: string;
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
  lenses = [],
  thesisText = "",
  accountId,
}: DrawerProps) {
  if (!open || !instrumentKey) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/20">
      <button type="button" className="flex-1" aria-label="Close drawer" onClick={onClose} />
      <aside className="h-full w-full max-w-xl overflow-y-auto border-l border-line bg-white p-5 shadow-xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-accent">Holding decision</p>
            <h3 className="text-2xl font-semibold">{symbol}</h3>
            <p className="text-sm text-zinc-600">Suggested review action: {action ?? "—"}</p>
          </div>
          <button type="button" className="text-sm text-zinc-500 hover:text-zinc-900" onClick={onClose}>
            Close
          </button>
        </div>
        <section className="mb-6 grid gap-2">
          <h4 className="text-sm font-semibold">Investor lenses</h4>
          <LensGrid lenses={lenses} />
        </section>
        <section className="mb-6">
          <ThesisEditor instrumentKey={instrumentKey} initialText={thesisText} accountId={accountId} />
        </section>
        <section className="rounded-md border border-line bg-panel p-3 text-xs text-zinc-600">
          Action simulator and monitoring rules are experimental. This UI does not place orders.
        </section>
      </aside>
    </div>
  );
}
