import { AppLink as Link } from "@/components/AppLink";

type HoldingRow = {
  instrument_key?: string;
  symbol?: string;
  action?: string;
  outcome?: string;
  valuation_status?: string;
  priority?: string;
  confidence_status?: string;
  blockers?: string[];
  gates?: Array<{ gate_id?: string; passed?: boolean }>;
  implementation_status?: string;
};

export function DecisionMatrix({
  holdings,
  onSelect,
}: {
  holdings: HoldingRow[];
  onSelect?: (instrumentKey: string) => void;
}) {
  if (!holdings.length) {
    return <p className="text-sm text-zinc-600">No holdings available for decision review.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-md border border-line bg-white">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-line bg-panel text-xs uppercase tracking-wide text-zinc-500">
          <tr>
            <th className="px-3 py-2">Symbol</th>
            <th className="px-3 py-2">Outcome</th>
            <th className="px-3 py-2">Priority</th>
            <th className="px-3 py-2">Confidence</th>
            <th className="px-3 py-2">Blockers</th>
            <th className="px-3 py-2">Gates</th>
            <th className="px-3 py-2">Detail</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((row) => {
            const key = row.instrument_key || row.symbol || "";
            const failedGates = (row.gates || []).filter((g) => g.passed === false).map((g) => g.gate_id).filter(Boolean);
            return (
              <tr key={key} className="border-b border-line last:border-0">
                <td className="px-3 py-2 font-medium">{row.symbol}</td>
                <td className="px-3 py-2">{row.outcome ?? row.action ?? "—"}</td>
                <td className="px-3 py-2">{row.priority ?? "routine"}</td>
                <td className="px-3 py-2">{row.confidence_status ?? "provisional"}</td>
                <td className="px-3 py-2 text-amber-800">
                  {(row.blockers || []).length ? (row.blockers || []).slice(0, 2).join(", ") : "—"}
                </td>
                <td className="px-3 py-2 text-zinc-600">
                  {failedGates.length ? `${failedGates.length} failed` : "clear"}
                </td>
                <td className="px-3 py-2">
                  <button
                    type="button"
                    className="text-accent hover:underline"
                    onClick={() => onSelect?.(key)}
                  >
                    Open drawer
                  </button>
                  {" · "}
                  <Link className="text-accent hover:underline" href={`/holdings/${encodeURIComponent(key)}`}>
                    Holding page
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
