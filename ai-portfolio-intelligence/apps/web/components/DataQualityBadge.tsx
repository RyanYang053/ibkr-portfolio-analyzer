type DataQualityBadgeProps = {
  label: string;
  status: string;
};

function tone(status: string): string {
  const normalized = status.toLowerCase();
  if (["sufficient", "approved", "yes", "complete", "experimental"].includes(normalized)) {
    return "border-accent/30 bg-teal-50 text-accent";
  }
  if (["partial", "insufficient", "missing", "withheld", "not_computed"].includes(normalized)) {
    return "border-amber-300 bg-amber-50 text-amber-800";
  }
  return "border-line bg-panel text-zinc-700";
}

export function DataQualityBadge({ label, status }: DataQualityBadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${tone(status)}`}>
      <span className="mr-1.5 text-[10px] uppercase tracking-wide text-zinc-500">{label}</span>
      {status}
    </span>
  );
}

export function DataQualityPanel({ dataQuality }: { dataQuality: Record<string, string> }) {
  const entries = Object.entries(dataQuality);
  if (!entries.length) {
    return null;
  }

  return (
    <div className="rounded-md border border-line bg-panel p-4">
      <h3 className="text-sm font-semibold text-zinc-900">Data Coverage</h3>
      <div className="mt-3 flex flex-wrap gap-2">
        {entries.map(([label, status]) => (
          <DataQualityBadge key={label} label={label.replaceAll("_", " ")} status={status} />
        ))}
      </div>
    </div>
  );
}
