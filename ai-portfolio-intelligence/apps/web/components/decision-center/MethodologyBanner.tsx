export function MethodologyBanner({ status = "experimental" }: { status?: string }) {
  return (
    <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <strong className="font-semibold uppercase tracking-wide">Experimental</strong>
      <span className="ml-2">
        Decision Center uses deterministic lenses and ordered gates. Valuation remains withheld.
        Methodology status: {status}.
      </span>
    </div>
  );
}
