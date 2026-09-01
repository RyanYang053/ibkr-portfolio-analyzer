import type { ReactNode } from "react";

import { humanizeCode } from "@/lib/format";

export type BadgeTone = "neutral" | "accent" | "positive" | "warning" | "negative" | "info";

const tones: Record<BadgeTone, string> = {
  neutral: "border-hairline bg-panel text-zinc-600",
  accent: "border-accent-border bg-accent-soft text-accent",
  positive: "border-positive-border bg-positive-soft text-positive",
  warning: "border-warning-border bg-warning-soft text-warning",
  negative: "border-negative-border bg-negative-soft text-negative",
  info: "border-info-border bg-info-soft text-info",
};

export function Badge({
  children,
  tone = "neutral",
  className = "",
  title,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4 ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/**
 * Severity words the backend uses, mapped to a consistent colour so "high" is
 * the same red everywhere it appears.
 */
const SEVERITY_TONES: Record<string, BadgeTone> = {
  critical: "negative",
  high: "negative",
  urgent: "negative",
  elevated: "warning",
  medium: "warning",
  moderate: "warning",
  this_week: "warning",
  attention_required: "warning",
  provisional: "warning",
  experimental: "warning",
  low: "neutral",
  routine: "neutral",
  info: "info",
  healthy: "positive",
  ok: "positive",
  available: "positive",
  sufficient: "positive",
  approved_for_personal_use: "positive",
  missing: "negative",
  unavailable: "negative",
  insufficient: "negative",
  failed: "negative",
};

export function toneForStatus(value: unknown): BadgeTone {
  if (value === null || value === undefined) return "neutral";
  return SEVERITY_TONES[String(value).toLowerCase()] ?? "neutral";
}

/** Badge for a backend status/severity code, humanised and colour-mapped. */
export function StatusBadge({ value, className = "" }: { value: unknown; className?: string }) {
  return (
    <Badge tone={toneForStatus(value)} className={className}>
      {humanizeCode(value)}
    </Badge>
  );
}
