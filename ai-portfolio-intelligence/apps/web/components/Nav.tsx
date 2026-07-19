"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Activity, Bell, ClipboardList, LayoutDashboard, Scale, Settings, ShieldCheck, Star, Search } from "lucide-react";
import { BrokerStatusBadge } from "@/components/BrokerStatusBadge";
import { AccountSwitcher } from "@/components/AccountSwitcher";

const items = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/portfolio", label: "Portfolio", icon: ClipboardList },
  { href: "/risk", label: "Risk Center", icon: ShieldCheck },
  { href: "/decision-center", label: "Decision Center", icon: Scale },
  { href: "/watchlist", label: "Watchlist", icon: Star },
  { href: "/reports", label: "Reports", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/audit", label: "Audit", icon: Bell }
];

export function Nav() {
  const [query, setQuery] = useState("");
  const router = useRouter();

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    router.push(`/holdings/${query.trim().toUpperCase()}`);
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
            <Link key={item.href} className="flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-panel transition-colors" href={item.href}>
              <Icon size={17} aria-hidden />
              {item.label}
            </Link>
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
