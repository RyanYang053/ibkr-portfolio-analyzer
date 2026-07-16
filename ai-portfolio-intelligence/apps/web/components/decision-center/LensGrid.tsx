"use client";

type Lens = {
  lens_id?: string;
  score?: number | null;
  status?: string;
};

export function LensGrid({ lenses }: { lenses: Lens[] }) {
  if (!lenses.length) {
    return <p className="text-sm text-zinc-600">No lens results.</p>;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {lenses.map((lens) => (
        <div key={lens.lens_id} className="rounded-md border border-line bg-white p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{lens.lens_id}</div>
          <div className="mt-1 text-2xl font-semibold">
            {lens.score == null ? "—" : lens.score.toFixed(1)}
          </div>
          <div className="mt-1 text-xs text-amber-800">{lens.status ?? "experimental"}</div>
        </div>
      ))}
    </div>
  );
}
