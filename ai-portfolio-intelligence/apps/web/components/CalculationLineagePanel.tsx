type CalculationLineagePanelProps = {
  calculationRunId?: string | null;
  methodology?: Record<string, string>;
  exclusions?: string[];
  factorModelStatus?: string;
  inputSnapshotIds?: string[];
  transactionBatchIds?: string[];
};

export function CalculationLineagePanel({
  calculationRunId,
  methodology,
  exclusions = [],
  factorModelStatus,
  inputSnapshotIds = [],
  transactionBatchIds = [],
}: CalculationLineagePanelProps) {
  const methodologyEntries = Object.entries(methodology ?? {});
  const structuredKeys = new Set([
    "methodology_id",
    "version",
    "approval_status",
    "effective_date",
    "code_sha",
    "validation_artifact_hash",
  ]);

  return (
    <div className="rounded-md border border-line bg-panel p-4">
      <h3 className="text-sm font-semibold text-zinc-900">Calculation Lineage</h3>
      <dl className="mt-3 space-y-2 text-sm text-zinc-700">
        <div>
          <dt className="font-medium text-zinc-900">Calculation run ID</dt>
          <dd className="font-mono text-xs">{calculationRunId ?? "Not recorded"}</dd>
        </div>
        {methodology?.methodology_id ? (
          <div>
            <dt className="font-medium text-zinc-900">Methodology ID</dt>
            <dd className="font-mono text-xs">{methodology.methodology_id}</dd>
          </div>
        ) : null}
        {methodology?.version ? (
          <div>
            <dt className="font-medium text-zinc-900">Version</dt>
            <dd>{methodology.version}</dd>
          </div>
        ) : null}
        {methodology?.approval_status ? (
          <div>
            <dt className="font-medium text-zinc-900">Approval status</dt>
            <dd>{methodology.approval_status}</dd>
          </div>
        ) : null}
        {methodology?.effective_date ? (
          <div>
            <dt className="font-medium text-zinc-900">Effective date</dt>
            <dd>{methodology.effective_date}</dd>
          </div>
        ) : null}
        {methodology?.code_sha ? (
          <div>
            <dt className="font-medium text-zinc-900">Code SHA</dt>
            <dd className="font-mono text-xs break-all">{methodology.code_sha}</dd>
          </div>
        ) : null}
        {methodology?.validation_artifact_hash ? (
          <div>
            <dt className="font-medium text-zinc-900">Validation artifact hash</dt>
            <dd className="font-mono text-xs break-all">{methodology.validation_artifact_hash}</dd>
          </div>
        ) : null}
        {inputSnapshotIds.length ? (
          <div>
            <dt className="font-medium text-zinc-900">Input snapshot IDs</dt>
            <dd className="font-mono text-xs break-all">{inputSnapshotIds.join(", ")}</dd>
          </div>
        ) : null}
        {transactionBatchIds.length ? (
          <div>
            <dt className="font-medium text-zinc-900">Transaction batch IDs</dt>
            <dd className="font-mono text-xs break-all">{transactionBatchIds.join(", ")}</dd>
          </div>
        ) : null}
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
          {methodologyEntries
            .filter(([key]) => !structuredKeys.has(key))
            .map(([key, value]) => (
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
