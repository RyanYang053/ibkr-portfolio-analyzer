import { AlertTriangle } from "lucide-react";

/**
 * Degraded-state indicator (plan §15.3 / P0.7): a subsystem's request failed, so
 * the absence of data is a FAILURE, not an empty-but-successful result. Never let
 * a caught error render as a reassuring "nothing here" state.
 */
export function DegradedStateBanner({ message }: { message: string }) {
  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-warning bg-amber-50 p-3 text-sm text-warning"
    >
      <AlertTriangle size={16} aria-hidden className="mt-0.5 shrink-0" />
      <span>{message}</span>
    </div>
  );
}
