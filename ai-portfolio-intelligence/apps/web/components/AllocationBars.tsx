export function AllocationBars({ data }: { data: Record<string, number> }) {
  return (
    <div className="grid gap-3">
      {Object.entries(data).map(([label, value]) => (
        <div key={label}>
          <div className="mb-1 flex justify-between text-sm">
            <span>{label}</span>
            <span>{value.toFixed(2)}%</span>
          </div>
          <div className="h-2 rounded-full bg-panel">
            <div className="h-2 rounded-full bg-accent" style={{ width: `${Math.min(value, 100)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
