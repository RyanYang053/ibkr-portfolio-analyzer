/**
 * Loading placeholders shaped like the content they replace.
 *
 * A skeleton that matches the final layout keeps the page from jumping when
 * data lands, and reads as "loading" rather than "broken" — which a bare
 * "Loading…" line does not.
 */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`skeleton ${className}`} />;
}

export function SkeletonText({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div className={`grid gap-2 ${className}`}>
      {Array.from({ length: lines }).map((_, index) => (
        // Short final line, so the block reads as prose rather than a bar chart.
        <Skeleton key={index} className={index === lines - 1 ? "h-3 w-2/3" : "h-3"} />
      ))}
    </div>
  );
}

export function SkeletonStatCards({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="rounded-lg border border-hairline bg-surface p-4 shadow-sm">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-3 h-7 w-32" />
          <Skeleton className="mt-2 h-3 w-20" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 6, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div className="overflow-hidden rounded-lg border border-hairline bg-surface shadow-sm">
      <div className="flex gap-4 border-b border-hairline bg-panel px-3 py-2.5">
        {Array.from({ length: columns }).map((_, index) => (
          <Skeleton key={index} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-4 border-b border-hairline px-3 py-3 last:border-b-0">
          {Array.from({ length: columns }).map((_, colIndex) => (
            <Skeleton key={colIndex} className="h-3 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonPanel({ className = "" }: { className?: string }) {
  return (
    <div className={`rounded-lg border border-hairline bg-surface p-4 shadow-sm ${className}`}>
      <Skeleton className="h-4 w-40" />
      <div className="mt-4 grid gap-2">
        <Skeleton className="h-3" />
        <Skeleton className="h-3" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    </div>
  );
}
