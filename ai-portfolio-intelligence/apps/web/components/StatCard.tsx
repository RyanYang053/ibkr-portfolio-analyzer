import type { ReactNode } from "react";

type StatCardProps = {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad";
  /** Optional sparkline, gauge or bar rendered beneath the figure. */
  visual?: ReactNode;
  hint?: string;
};

const tones = {
  neutral: { border: "border-hairline", value: "text-zinc-900" },
  good: { border: "border-positive-border", value: "text-positive" },
  warn: { border: "border-warning-border", value: "text-warning" },
  bad: { border: "border-negative-border", value: "text-negative" },
} as const;

/**
 * One headline figure.
 *
 * The value truncates rather than overflowing its card: several backend status
 * codes are long enough to run past the edge otherwise, and `title` keeps the
 * full text reachable.
 */
export function StatCard({ label, value, detail, tone = "neutral", visual, hint }: StatCardProps) {
  const palette = tones[tone];
  return (
    <div
      className={`flex flex-col justify-between rounded-lg border bg-surface p-3.5 shadow-sm ${palette.border}`}
    >
      <div className="min-w-0">
        <div
          className="truncate text-[11px] font-semibold uppercase tracking-wider text-zinc-500"
          title={hint ?? label}
        >
          {label}
        </div>
        <div
          className={`num mt-1.5 truncate text-[22px] font-semibold leading-8 tracking-tight ${palette.value}`}
          title={typeof value === "string" ? value : undefined}
        >
          {value}
        </div>
        {detail ? <div className="mt-0.5 truncate text-xs text-zinc-500">{detail}</div> : null}
      </div>
      {visual ? <div className="mt-2">{visual}</div> : null}
    </div>
  );
}
