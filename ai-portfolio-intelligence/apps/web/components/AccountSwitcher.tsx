"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { getAccounts, invalidateApiGetCache } from "@/lib/api";
import { CreditCard, RefreshCw } from "lucide-react";
import { useAppRouter } from "@/lib/use-app-router";

const ACCOUNTS_CACHE_KEY = "pai.accounts.v1";
const ACCOUNTS_CACHE_TTL_MS = 5 * 60_000;

type CachedAccounts = {
  fetchedAt: number;
  accounts: Array<Record<string, unknown>>;
};

function readActiveAccountId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return new URLSearchParams(window.location.search).get("account_id");
}

function readAccountsCache(): CachedAccounts | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = sessionStorage.getItem(ACCOUNTS_CACHE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as CachedAccounts;
    if (!parsed?.fetchedAt || !Array.isArray(parsed.accounts)) {
      return null;
    }
    if (Date.now() - parsed.fetchedAt > ACCOUNTS_CACHE_TTL_MS) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function writeAccountsCache(accounts: Array<Record<string, unknown>>): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    sessionStorage.setItem(
      ACCOUNTS_CACHE_KEY,
      JSON.stringify({ fetchedAt: Date.now(), accounts } satisfies CachedAccounts),
    );
  } catch {
    // ignore quota / private mode
  }
}

export function AccountSwitcher() {
  const router = useAppRouter();
  const pathname = usePathname();

  const [activeAccountId, setActiveAccountId] = useState<string>("all");
  const [accounts, setAccounts] = useState<Array<Record<string, unknown>>>(() => {
    return readAccountsCache()?.accounts ?? [];
  });
  const [isLoading, setIsLoading] = useState(() => !readAccountsCache());

  useEffect(() => {
    const current = readActiveAccountId();
    if (current) {
      setActiveAccountId(current);
    }

    const cached = readAccountsCache();
    if (cached) {
      setAccounts(cached.accounts);
      setIsLoading(false);
      ensureAccountParam(cached.accounts);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    getAccounts()
      .then((data) => {
        if (cancelled) {
          return;
        }
        const list = (data || []) as Array<Record<string, unknown>>;
        setAccounts(list);
        writeAccountsCache(list);
        ensureAccountParam(list);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };

    function ensureAccountParam(list: Array<Record<string, unknown>>) {
      const selected = readActiveAccountId();
      if (selected || list.length === 0) {
        return;
      }
      // Keep URL and API in sync: missing account_id with multiple accounts
      // previously caused "account_id is required…".
      if (list.length === 1) {
        const only = String(list[0].id);
        setActiveAccountId(only);
        const params = new URLSearchParams(window.location.search);
        params.set("account_id", only);
        router.replace(`${pathname}?${params.toString()}`);
      } else {
        setActiveAccountId("all");
        const params = new URLSearchParams(window.location.search);
        params.set("account_id", "all");
        router.replace(`${pathname}?${params.toString()}`);
      }
    }
    // Only re-sync on path change; account list is session-cached.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  function handleSelect(val: string) {
    const params = new URLSearchParams(typeof window !== "undefined" ? window.location.search : "");
    params.set("account_id", val === "all" ? "all" : val);
    setActiveAccountId(val === "all" ? "all" : val);
    invalidateApiGetCache();
    router.push(`${pathname}?${params.toString()}`);
  }

  if (accounts.length <= 1 && !isLoading) {
    return null;
  }

  return (
    <div className="mb-4">
      <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block mb-1">
        Active Account
      </label>
      <p className="mb-1 text-[10px] text-zinc-500">
        Multiple IBKR accounts detected. Pick one account or Consolidated View.
      </p>
      <div className="relative">
        <select
          value={activeAccountId}
          onChange={(e) => handleSelect(e.target.value)}
          className="w-full rounded-md border border-line bg-zinc-50 pl-8 pr-8 py-1.5 text-xs text-zinc-950 font-medium focus:border-accent focus:bg-white focus:outline-none focus:ring-1 focus:ring-accent transition-all cursor-pointer appearance-none"
        >
          <option value="all">Consolidated View (All Accounts)</option>
          {accounts.map((acct) => (
            <option key={String(acct.id)} value={String(acct.id)}>
              {String(acct.account_alias || acct.id)} ({String(acct.id)})
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
