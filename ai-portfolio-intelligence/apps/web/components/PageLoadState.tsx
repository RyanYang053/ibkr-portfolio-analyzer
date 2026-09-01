import { AlertTriangle, RotateCw } from "lucide-react";

import { SkeletonPanel, SkeletonStatCards, SkeletonTable } from "@/components/ui/Skeleton";

/**
 * First-paint placeholder for a page.
 *
 * `variant` picks a silhouette that matches the page about to render, so the
 * layout does not jump when data lands. A page that already has cached data
 * should not reach here at all — `useClientResource` seeds it and revalidates
 * behind the visible numbers instead.
 */
export function PageLoading({
  label = "Loading…",
  variant = "detail",
}: {
  label?: string;
  variant?: "detail" | "table" | "dashboard";
}) {
  return (
    <div className="grid gap-6" aria-busy="true">
      <span className="sr-only" role="status">
        {label}
      </span>

      <div>
        <div className="skeleton h-3 w-28" />
        <div className="skeleton mt-2 h-7 w-64" />
      </div>

      {variant === "dashboard" ? (
        <>
          <SkeletonStatCards />
          <div className="grid gap-4 xl:grid-cols-2">
            <SkeletonPanel />
            <SkeletonPanel />
          </div>
          <SkeletonTable rows={5} />
        </>
      ) : variant === "table" ? (
        <>
          <SkeletonStatCards count={4} />
          <SkeletonTable rows={8} columns={6} />
        </>
      ) : (
        <>
          <SkeletonStatCards count={4} />
          <div className="grid gap-4 xl:grid-cols-2">
            <SkeletonPanel />
            <SkeletonPanel />
          </div>
        </>
      )}
    </div>
  );
}

export function PageErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2.5 rounded-lg border border-warning-border bg-warning-soft p-4 text-sm text-warning"
    >
      <AlertTriangle size={16} aria-hidden className="mt-0.5 shrink-0" />
      <span className="flex-1 leading-6">{message}</span>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-warning-border px-2 py-1 text-xs font-medium hover:bg-warning-soft"
        >
          <RotateCw size={12} aria-hidden />
          Retry
        </button>
      ) : null}
    </div>
  );
}
