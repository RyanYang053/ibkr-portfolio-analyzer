import { ShieldCheck } from "lucide-react";

/**
 * Standing compliance notice.
 *
 * Deliberately low-contrast: it appears on every page, so it has to stay
 * legible and findable without competing with the numbers for attention.
 */
export function Disclaimer() {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-accent-border bg-accent-soft px-3.5 py-2.5 text-[13px] leading-6 text-zinc-700">
      <ShieldCheck size={15} aria-hidden className="mt-1 shrink-0 text-accent" />
      <p className="m-0">
        <strong className="font-semibold text-zinc-900">Research and decision-support only.</strong>{" "}
        This system does not execute trades, does not submit orders to IBKR, and requires human review
        before any investment decision.
      </p>
    </div>
  );
}
