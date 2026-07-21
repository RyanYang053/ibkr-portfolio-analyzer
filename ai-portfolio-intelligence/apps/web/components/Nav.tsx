"use client";

import { useState } from "react";
import {
  Activity,
  Bell,
  BookOpen,
  ClipboardList,
  HeartPulse,
  History,
  LayoutDashboard,
  Scale,
  Settings,
  ShieldCheck,
  Star,
  Search,
  Target,
  Telescope,
  TrendingUp,
} from "lucide-react";
import { AppLink } from "@/components/AppLink";
import { BrokerStatusBadge } from "@/components/BrokerStatusBadge";
import { AccountSwitcher } from "@/components/AccountSwitcher";
import { useAppRouter } from "@/lib/use-app-router";

const items = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/markets", label: "Markets", icon: TrendingUp },
  { href: "/decisions", label: "Decisions", icon: Scale },
  { href: "/plan", label: "Plan", icon: Target },
  { href: "/research", label: "Research", icon: Telescope },
  { href: "/securities", label: "Securities", icon: Search },
  { href: "/trade-plans", label: "Trade Plans", icon: ClipboardList },
  { href: "/journal", label: "Journal", icon: BookOpen },
  { href: "/monitoring", label: "Monitoring", icon: HeartPulse },
  { href: "/portfolio", label: "Portfolio", icon: ClipboardList },
  { href: "/portfolio/construction", label: "Construction", icon: BookOpen },
  { href: "/risk", label: "Risk Center", icon: ShieldCheck },
  { href: "/history", label: "History", icon: History },
  { href: "/data-health", label: "Data Health", icon: Activity },
  { href: "/methodologies", label: "Methodologies", icon: Bell },
  { href: "/watchlist", label: "Watchlist", icon: Star },
  { href: "/reports", label: "Reports", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Nav() {
  const [query, setQuery] = useState("");
  const router = useAppRouter();

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    const symbol = query.trim().toUpperCase();
    router.push(`/holdings/${encodeURIComponent(symbol)}`);
    setQuery("");
  }

  return (
    <aside className="border-r border-line bg-white px-4 py-5 lg:min-h-screen">
      <div className="mb-6">
        <div className="text-sm font-semibold uppercase tracking-wide text-accent">Read-only IBKR</div>
        <h1 className="text-xl font-semibold leading-tight">AI Portfolio Intelligence</h1>
      </div>

      <AccountSwitcher />

      <form onSubmit={handleSearch} className="mb-4 relative">
        <input
          type="text"
          placeholder="Lookup stock ticker..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-md border border-line bg-zinc-50 pl-8 pr-3 py-1.5 text-xs text-zinc-950 placeholder-zinc-400 focus:border-accent focus:bg-white focus:outline-none focus:ring-1 focus:ring-accent transition-all"
        />
        <Search className="absolute left-2.5 top-2.5 text-zinc-400" size={13} />
      </form>

      <nav className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-1 gap-1">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <AppLink key={item.href} className="flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-panel transition-colors" href={item.href}>
              <Icon size={17} aria-hidden />
              {item.label}
            </AppLink>
          );
        })}
      </nav>
      <div className="mt-8 rounded-md border border-line bg-panel p-3 text-xs leading-5">
        Broker actions are read-only. No order placement, automated rebalancing, or broker execution controls exist in this UI.
      </div>
      <BrokerStatusBadge />
    </aside>
  );
}
