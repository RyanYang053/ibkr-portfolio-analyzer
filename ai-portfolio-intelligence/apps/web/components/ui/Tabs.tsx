"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Accessible tab strip with the selection mirrored into the URL.
 *
 * Two reasons the tab lives in the query string rather than in component state:
 * a reload (which the desktop shell performs on every navigation) would
 * otherwise always land back on the first tab, and a specific tab cannot be
 * linked to or reopened from history.
 */
export function useUrlTab<T extends string>(tabs: readonly T[], paramName = "tab"): [T, (tab: T) => void] {
  const [tab, setTabState] = useState<T>(tabs[0]);

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get(paramName);
    const match = tabs.find((candidate) => candidate.toLowerCase() === (fromUrl ?? "").toLowerCase());
    if (match) {
      setTabState(match);
    }
    // `tabs` is a literal tuple defined at module scope in every caller.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramName]);

  const setTab = useCallback(
    (next: T) => {
      setTabState(next);
      const params = new URLSearchParams(window.location.search);
      params.set(paramName, next);
      // replaceState keeps Back returning to the previous *page*, not to each
      // tab the user glanced at.
      window.history.replaceState(null, "", `${window.location.pathname}?${params}`);
    },
    [paramName],
  );

  return [tab, setTab];
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label = "Sections",
  counts,
}: {
  tabs: readonly T[];
  value: T;
  onChange: (tab: T) => void;
  label?: string;
  counts?: Partial<Record<T, number>>;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  function onKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (delta === 0) {
      return;
    }
    event.preventDefault();
    const next = (index + delta + tabs.length) % tabs.length;
    onChange(tabs[next]);
    refs.current[next]?.focus();
  }

  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 border-b border-line">
      {tabs.map((name, index) => {
        const selected = value === name;
        const count = counts?.[name];
        return (
          <button
            key={name}
            ref={(element) => {
              refs.current[index] = element;
            }}
            role="tab"
            type="button"
            id={`tab-${name}`}
            aria-selected={selected}
            aria-controls={`panel-${name}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(name)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={`-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm transition-colors ${
              selected
                ? "border-accent font-semibold text-accent"
                : "border-transparent text-zinc-600 hover:border-line hover:text-zinc-900"
            }`}
          >
            {name}
            {typeof count === "number" ? (
              <span className="rounded-full bg-panel px-1.5 text-[11px] font-medium text-zinc-500">{count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div role="tabpanel" id={`panel-${name}`} aria-labelledby={`tab-${name}`} className="page-enter">
      {children}
    </div>
  );
}
