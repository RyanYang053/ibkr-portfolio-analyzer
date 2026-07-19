"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { getAccounts } from "@/lib/api";
import { CreditCard, RefreshCw } from "lucide-react";

function readActiveAccountId(): string {
  if (typeof window === "undefined") {
    return "all";
  }
  return new URLSearchParams(window.location.search).get("account_id") || "all";
}

export function AccountSwitcher() {
  const router = useRouter();
  const pathname = usePathname();

  const [activeAccountId, setActiveAccountId] = useState("all");
  const [accounts, setAccounts] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    setActiveAccountId(readActiveAccountId());
    setIsLoading(true);
    getAccounts()
      .then((data) => {
        setAccounts(data || []);
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [pathname]);

  function handleSelect(val: string) {
    const params = new URLSearchParams(typeof window !== "undefined" ? window.location.search : "");
    params.set("account_id", val === "all" ? "all" : val);
    setActiveAccountId(val === "all" ? "all" : val);
    router.push(`${pathname}?${params.toString()}`);
  }

  // Show switcher if there are multiple accounts or if mock/live could have multiple.
  // In demo mode or connected TWS, if accounts length > 1, show picker.
  if (accounts.length <= 1 && !isLoading) {
    // Return a default view but keep it hidden if there's nothing to select
    return null;
  }

  return (
    <div className="mb-4">
      <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block mb-1">
        Active Account
      </label>
      <div className="relative">
        <select
          value={activeAccountId}
          onChange={(e) => handleSelect(e.target.value)}
          className="w-full rounded-md border border-line bg-zinc-50 pl-8 pr-8 py-1.5 text-xs text-zinc-950 font-medium focus:border-accent focus:bg-white focus:outline-none focus:ring-1 focus:ring-accent transition-all cursor-pointer appearance-none"
        >
          <option value="all">Consolidated View (All Accounts)</option>
          {accounts.map((acct) => (
            <option key={acct.id} value={acct.id}>
              {acct.account_alias || acct.id} ({acct.id})
            </option>
          ))}
        </select>
        <CreditCard className="absolute left-2.5 top-2.5 text-zinc-400 pointer-events-none" size={13} />
        {isLoading ? (
          <RefreshCw className="absolute right-2.5 top-2.5 text-zinc-400 animate-spin" size={11} />
        ) : (
          <div className="absolute right-2.5 top-2 text-zinc-400 pointer-events-none text-[8px] font-bold">▼</div>
        )}
      </div>
    </div>
  );
}
