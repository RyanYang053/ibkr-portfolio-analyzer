"use client";

import { useId, useState } from "react";
import { Info } from "lucide-react";

/**
 * Explanation of how a metric is calculated, attached to its label.
 *
 * A `<button>` rather than a hover-only `<span>`: these carry the methodology
 * behind every risk number, which a keyboard or screen-reader user needs as
 * much as a mouse user. The panel is removed from the DOM when closed — an
 * `invisible` fixed-width panel still contributes to page width and pushed the
 * layout into horizontal scroll at narrower viewports.
 *
 * Anchored to the trigger's right edge and width-clamped to the viewport so it
 * stays on screen for the rightmost card in a row.
 */
export function InfoTip({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label={`How ${label} is calculated`}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen((current) => !current)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
        className="text-zinc-400 transition-colors hover:text-accent focus-visible:text-accent"
      >
        <Info size={12} aria-hidden />
      </button>
      {open ? (
        <span
          id={id}
          role="tooltip"
          className="absolute bottom-full right-0 z-20 mb-2 w-[min(16rem,calc(100vw-3rem))] rounded-md border border-line bg-surface p-2.5 text-[11px] font-normal normal-case leading-5 text-zinc-700 shadow-lg"
        >
          {children}
        </span>
      ) : null}
    </span>
  );
}
