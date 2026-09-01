"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Command, Search } from "lucide-react";

import { AppLink } from "@/components/AppLink";
import { BrokerStatusBadge } from "@/components/BrokerStatusBadge";
import { AccountSwitcher } from "@/components/AccountSwitcher";
import { ThemeToggle } from "@/components/ThemeToggle";
import { NAV_GROUPS, activeNavHref } from "@/lib/navigation";
import { useAppRouter } from "@/lib/use-app-router";

export function Nav() {
  const [query, setQuery] = useState("");
  const router = useAppRouter();
  const pathname = usePathname();
  const activeHref = activeNavHref(pathname ?? "/");

  function handleSearch(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    const symbol = query.trim().toUpperCase();
    router.push(`/holdings/${encodeURIComponent(symbol)}`);
    setQuery("");
  }

  function openCommandPalette() {
    window.dispatchEvent(new CustomEvent("pai:open-command-palette"));
  }

  return (
    <aside className="flex flex-col border-r border-hairline bg-surface lg:sticky lg:top-0 lg:h-screen">
      <div className="shrink-0 px-3 pb-2 pt-4">
      <div className="mb-4 px-1">
        <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-accent">Read-only IBKR</div>
        <h1 className="mt-0.5 text-[15px] font-semibold leading-snug tracking-tight text-zinc-900">
          Portfolio Intelligence
        </h1>
      </div>

      <AccountSwitcher />

      <form onSubmit={handleSearch} className="relative mb-2">
        <label htmlFor="nav-ticker-search" className="sr-only">
          Look up a stock ticker
        </label>
        <input
          id="nav-ticker-search"
          type="text"
          placeholder="Look up a ticker…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="w-full rounded-md border border-hairline bg-panel py-1.5 pl-8 pr-3 text-xs text-zinc-900 placeholder-zinc-400 transition-colors focus:border-accent focus:bg-surface focus:outline-none focus:ring-1 focus:ring-accent"
        />
        <Search className="pointer-events-none absolute left-2.5 top-2 text-zinc-400" size={13} aria-hidden />
      </form>

      <button
        type="button"
        onClick={openCommandPalette}
        className="mb-4 flex w-full items-center justify-between rounded-md border border-hairline bg-panel px-2.5 py-1.5 text-xs text-zinc-500 transition-colors hover:border-line hover:text-zinc-900"
      >
        <span className="flex items-center gap-2">
          <Command size={12} aria-hidden />
          Go to…
        </span>
        <kbd className="rounded border border-hairline bg-surface px-1 font-sans text-[10px] text-zinc-500">
          ⌘K
        </kbd>
      </button>

      </div>

      <nav aria-label="Primary" className="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-3 pb-2">
        {NAV_GROUPS.map((group) => (
          <div key={group.id}>
            <h2 className="mb-0.5 px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-zinc-400">
              {group.label}
            </h2>
            <ul className="grid grid-cols-2 gap-0.5 sm:grid-cols-3 lg:grid-cols-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                const current = activeHref === item.href;
                return (
                  <li key={item.href}>
                    <AppLink
                      href={item.href}
                      aria-current={current ? "page" : undefined}
                      title={item.hint}
                      className={`flex items-center gap-2.5 rounded-md px-2.5 py-[5px] text-[13px] transition-colors ${
                        current
                          ? "bg-accent-soft font-semibold text-accent"
                          : "text-zinc-700 hover:bg-panel hover:text-zinc-900"
                      }`}
                    >
                      <Icon size={15} aria-hidden className={current ? "" : "text-zinc-400"} />
                      <span className="truncate">{item.label}</span>
                    </AppLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="shrink-0 space-y-2.5 border-t border-hairline px-3 py-3">
        <ThemeToggle />
        <p className="rounded-md border border-hairline bg-panel p-2 text-[11px] leading-[1.45] text-zinc-600">
          Read-only. No order placement, automated rebalancing, or broker execution controls exist in
          this UI.
        </p>
        <BrokerStatusBadge />
      </div>
    </aside>
  );
}
