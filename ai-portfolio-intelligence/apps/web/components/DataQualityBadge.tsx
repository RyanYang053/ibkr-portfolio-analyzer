import { displayValue, humanizeCode } from "@/lib/format";

type DataQualityBadgeProps = {
  label: string;
  status: string;
};

/**
 * Coverage codes are compound — `sufficient_modeled_current_holdings`,
 * `partial_modeled_current_holdings`. Matching the leading word rather than the
 * whole string means a compound code is coloured by what it actually says
 * instead of falling through to neutral grey.
 */
function tone(status: string): string {
  const first = status.toLowerCase().split(/[_\s-]/)[0];
  if (["sufficient", "approved", "yes", "complete", "available", "reconciled"].includes(first)) {
    return "border-positive-border bg-positive-soft text-positive";
  }
  if (["experimental", "provisional", "partial", "heuristic", "mock", "insufficient"].includes(first)) {
    return "border-warning-border bg-warning-soft text-warning";
  }
  if (["missing", "withheld", "failed", "invalid", "unavailable"].includes(first)) {
    return "border-negative-border bg-negative-soft text-negative";
  }
  // "none" is not a failure here: for the exclusion fields it means nothing had
  // to be dropped, which is the good outcome. Neutral rather than guessing.
  return "border-hairline bg-panel text-zinc-700";
}

export function DataQualityBadge({ label, status }: DataQualityBadgeProps) {
  return (
    <span
      title={`${label}: ${status}`}
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${tone(status)}`}
    >
      <span className="mr-1.5 text-[10px] uppercase tracking-wide text-zinc-500">{label}</span>
      {displayValue(status)}
    </span>
  );
}

/** Fields whose name states the unit render with it, e.g. `100.00` -> `100.00%`. */
function withUnit(label: string, status: string): string {
  if (/percent$/i.test(label) && /^-?\d+(\.\d+)?$/.test(status.trim())) {
    return `${status}%`;
  }
  return status;
}

export function DataQualityPanel({ dataQuality }: { dataQuality: Record<string, string> }) {
  const entries = Object.entries(dataQuality);
  if (!entries.length) {
    return null;
  }

  return (
    <div className="rounded-lg border border-hairline bg-surface p-4 shadow-sm">
      <h3 className="text-[15px] font-semibold text-zinc-900">Data coverage</h3>
      <p className="mt-0.5 text-xs text-zinc-500">
        What each risk input could actually be measured from. Hover a chip for its raw code.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {entries.map(([label, status]) => (
          <DataQualityBadge key={label} label={humanizeCode(label)} status={withUnit(label, status)} />
        ))}
      </div>
    </div>
  );
}
