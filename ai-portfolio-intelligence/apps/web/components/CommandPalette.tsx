"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CornerDownLeft, Search } from "lucide-react";

import { prefetchRouteData } from "@/components/AppLink";
import { NAV_GROUPS, type NavItem } from "@/lib/navigation";
import { useAppRouter } from "@/lib/use-app-router";

type Entry = NavItem & { group: string };

const ENTRIES: Entry[] = NAV_GROUPS.flatMap((group) =>
  group.items.map((item) => ({ ...item, group: group.label })),
);

/** Case-insensitive subsequence match, so "pcon" finds "Portfolio Construction". */
function fuzzyScore(haystack: string, needle: string): number {
  const target = haystack.toLowerCase();
  const query = needle.toLowerCase();
  if (!query) return 1;
  if (target.startsWith(query)) return 1000;
  const index = target.indexOf(query);
  if (index >= 0) return 500 - index;

  let cursor = 0;
  let score = 0;
  for (const char of query) {
    const found = target.indexOf(char, cursor);
    if (found < 0) return 0;
    score += found === cursor ? 3 : 1;
    cursor = found + 1;
  }
  return score;
}

/**
 * ⌘K / Ctrl-K navigation.
 *
 * A dense analysis tool is used by keyboard; hunting a 20-item sidebar with the
 * mouse for every jump is the slowest part of the interface. Highlighting a
 * result also prefetches that page's data, so committing to it lands on content
 * that is already cached.
 */
export function CommandPalette() {
  const router = useAppRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlighted, setHighlighted] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const results = useMemo(() => {
    if (!query.trim()) {
      return ENTRIES;
    }
    return ENTRIES.map((entry) => {
      const haystacks = [entry.label, entry.group, entry.hint, ...(entry.keywords ?? [])];
      const score = Math.max(...haystacks.map((text) => fuzzyScore(text, query.trim())));
      return { entry, score };
    })
      .filter(({ score }) => score > 0)
      .sort((a, b) => b.score - a.score)
      .map(({ entry }) => entry);
  }, [query]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setHighlighted(0);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => !current);
      }
    }
    function onOpenRequest() {
      setOpen(true);
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("pai:open-command-palette", onOpenRequest);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("pai:open-command-palette", onOpenRequest);
    };
  }, []);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    setHighlighted(0);
  }, [query]);

  // Warm the highlighted destination so Enter lands on cached data.
  useEffect(() => {
    const target = results[highlighted];
    if (open && target) {
      // Highlighting a result is the same signal as hovering a nav link.
      prefetchRouteData(target.href, { intent: true });
    }
  }, [open, highlighted, results]);

  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [highlighted]);

  if (!open) {
    return null;
  }

  function commit(entry: Entry | undefined) {
    if (!entry) return;
    close();
    router.push(entry.href);
  }

  function onInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key === "ArrowDown" || (event.key === "n" && event.ctrlKey)) {
      event.preventDefault();
      setHighlighted((index) => (results.length ? (index + 1) % results.length : 0));
      return;
    }
    if (event.key === "ArrowUp" || (event.key === "p" && event.ctrlKey)) {
      event.preventDefault();
      setHighlighted((index) => (results.length ? (index - 1 + results.length) % results.length : 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      commit(results[highlighted]);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-4 pt-[12vh] backdrop-blur-[2px]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Go to page"
        className="w-full max-w-xl overflow-hidden rounded-xl border border-line bg-surface shadow-lg"
      >
        <div className="flex items-center gap-2.5 border-b border-hairline px-3.5 py-3">
          <Search size={15} aria-hidden className="text-zinc-400" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onInputKeyDown}
            placeholder="Go to page…"
            aria-controls="command-palette-results"
            aria-activedescendant={results[highlighted] ? `cmd-${results[highlighted].href}` : undefined}
            className="w-full bg-transparent text-sm text-zinc-900 placeholder-zinc-400 focus:outline-none"
          />
          <kbd className="rounded border border-hairline bg-panel px-1.5 py-0.5 text-[10px] text-zinc-500">
            Esc
          </kbd>
        </div>

        <ul id="command-palette-results" ref={listRef} role="listbox" className="max-h-[52vh] overflow-y-auto p-1.5">
          {results.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-zinc-500">No matching page.</li>
          ) : (
            results.map((entry, index) => {
              const Icon = entry.icon;
              const selected = index === highlighted;
              return (
                <li key={entry.href}>
                  <button
                    id={`cmd-${entry.href}`}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    onMouseEnter={() => setHighlighted(index)}
                    onClick={() => commit(entry)}
                    className={`flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left transition-colors ${
                      selected ? "bg-accent-soft" : "hover:bg-panel"
                    }`}
                  >
                    <Icon size={15} aria-hidden className={selected ? "text-accent" : "text-zinc-400"} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-zinc-900">{entry.label}</span>
                      <span className="block truncate text-xs text-zinc-500">{entry.hint}</span>
                    </span>
                    <span className="shrink-0 text-[10px] uppercase tracking-wider text-zinc-400">
                      {entry.group}
                    </span>
                    {selected ? <CornerDownLeft size={13} aria-hidden className="shrink-0 text-accent" /> : null}
                  </button>
                </li>
              );
            })
          )}
        </ul>
      </div>
    </div>
  );
}
