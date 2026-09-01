import type { ReactNode } from "react";

import { RefreshCw } from "lucide-react";

/**
 * Consistent page masthead: eyebrow, title, one line of orientation, actions.
 *
 * `refreshing` shows an unobtrusive marker while data revalidates behind
 * already-visible numbers — the user should be able to tell that what they are
 * reading is being updated, without the page blanking.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  refreshing = false,
  stale = false,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  refreshing?: boolean;
  stale?: boolean;
}) {
  return (
    <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {eyebrow ? (
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-accent">{eyebrow}</p>
        ) : null}
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-semibold tracking-tight text-zinc-900">{title}</h2>
          {refreshing ? (
            <span
              role="status"
              aria-live="polite"
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-panel px-2 py-0.5 text-[11px] font-medium text-zinc-500"
            >
              <RefreshCw size={11} aria-hidden className="animate-spin" />
              {stale ? "Updating" : "Refreshing"}
            </span>
          ) : null}
        </div>
        {description ? (
          <p className="mt-1 max-w-3xl text-sm leading-6 text-zinc-600">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
