type CalculationLineagePanelProps = {
  calculationRunId?: string | null;
  methodology?: Record<string, string>;
  exclusions?: string[];
  factorModelStatus?: string;
};

export function CalculationLineagePanel({
  calculationRunId,
  methodology,
  exclusions = [],
  factorModelStatus,
}: CalculationLineagePanelProps) {
  const methodologyEntries = Object.entries(methodology ?? {});

  return (
    <div className="rounded-md border border-line bg-panel p-4">
      <h3 className="text-sm font-semibold text-zinc-900">Calculation Lineage</h3>
      <dl className="mt-3 space-y-2 text-sm text-zinc-700">
        <div>
          <dt className="font-medium text-zinc-900">Calculation run</dt>
          <dd className="font-mono text-xs">{calculationRunId ?? "Not recorded"}</dd>
        </div>
        {factorModelStatus ? (
          <div>
            <dt className="font-medium text-zinc-900">Factor model status</dt>
            <dd>{factorModelStatus}</dd>
          </div>
        ) : null}
        {exclusions.length ? (
          <div>
            <dt className="font-medium text-zinc-900">Exclusions</dt>
            <dd>{exclusions.join(", ")}</dd>
          </div>
        ) : null}
      </dl>
      {methodologyEntries.length ? (
        <div className="mt-4 space-y-3">
          {methodologyEntries.map(([key, value]) => (
            <div key={key}>
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{key.replaceAll("_", " ")}</p>
              <p className="mt-1 text-sm text-zinc-700">{value}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
