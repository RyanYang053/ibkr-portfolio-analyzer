import Link from "next/link";

type HoldingRow = {
  instrument_key?: string;
  symbol?: string;
  action?: string;
  valuation_status?: string;
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
            <th className="px-3 py-2">Action</th>
            <th className="px-3 py-2">Valuation</th>
            <th className="px-3 py-2">Detail</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((row) => {
            const key = row.instrument_key || row.symbol || "";
            return (
              <tr key={key} className="border-b border-line last:border-0">
                <td className="px-3 py-2 font-medium">{row.symbol}</td>
                <td className="px-3 py-2">{row.action ?? "—"}</td>
                <td className="px-3 py-2 text-amber-800">{row.valuation_status ?? "withheld"}</td>
                <td className="px-3 py-2">
                  <button
                    type="button"
                    className="text-accent hover:underline"
                    onClick={() => onSelect?.(key)}
                  >
                    Open drawer
                  </button>
                  {" · "}
                  <Link className="text-accent hover:underline" href={`/holdings/detail?symbol=${encodeURIComponent(String(row.symbol || ""))}`}>
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
