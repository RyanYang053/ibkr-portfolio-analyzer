import type { ReactNode } from "react";

/**
 * A panel with nothing in it.
 *
 * Deliberately distinct from `DegradedStateBanner`: this means "the request
 * succeeded and there genuinely is nothing here", which is a different fact
 * from "the request failed so we cannot say".
 */
export function EmptyState({
  title,
  description,
  icon,
  action,
  className = "",
}: {
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center rounded-lg border border-dashed border-line bg-panel/50 px-6 py-10 text-center ${className}`}
    >
      {icon ? <div className="mb-3 text-zinc-400">{icon}</div> : null}
      <p className="text-sm font-medium text-zinc-700">{title}</p>
      {description ? (
        <p className="mt-1 max-w-md text-xs leading-5 text-zinc-500">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
