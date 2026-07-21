"use client";

import { useState } from "react";
import { AppLink as Link } from "@/components/AppLink";
import { Plus, Trash2, Eye, TrendingUp, AlertTriangle, X, Check } from "lucide-react";
import { addWatchlistItem, deleteWatchlistItem, getWatchlist } from "@/lib/api";

interface WatchItem {
  id: number;
  symbol: string;
  reason: string;
  target_add_price?: number;
  target_trim_review_price?: number;
  status: string;
}

export function WatchlistContainer({ initialItems }: { initialItems: WatchItem[] }) {
  const [items, setItems] = useState<WatchItem[]>(initialItems);
  const [isAdding, setIsAdding] = useState(false);
  const [symbol, setSymbol] = useState("");
  const [reason, setReason] = useState("");
  const [targetAdd, setTargetAdd] = useState("");
  const [targetTrim, setTargetTrim] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!symbol.trim() || !reason.trim()) {
      setError("Symbol and reason are required.");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const payload = {
        symbol: symbol.toUpperCase().trim(),
        reason: reason.trim(),
        target_add_price: targetAdd ? parseFloat(targetAdd) : undefined,
        target_trim_review_price: targetTrim ? parseFloat(targetTrim) : undefined,
      };

      const newItem = await addWatchlistItem(payload);
      
      // Fetch fresh watchlist from backend to ensure accurate IDs and sync
      const freshList = await getWatchlist() as WatchItem[];
      setItems(freshList);
      
      // Reset form
      setSymbol("");
      setReason("");
      setTargetAdd("");
      setTargetTrim("");
      setIsAdding(false);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to add item");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("Are you sure you want to remove this stock from your watchlist?")) {
      return;
    }

    try {
      await deleteWatchlistItem(id);
      setItems((prev) => prev.filter((item) => item.id !== id));
    } catch (exc) {
      alert(exc instanceof Error ? exc.message : "Failed to delete item");
    }
  }

  return (
    <div className="grid gap-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-zinc-900">Monitored Securities</h3>
        <button
          onClick={() => {
            setIsAdding(!isAdding);
            setError(null);
          }}
          className="inline-flex items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-accent/90 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 transition-colors"
        >
          {isAdding ? <X size={14} /> : <Plus size={14} />}
          {isAdding ? "Cancel" : "Add Stock"}
        </button>
      </div>

      {isAdding && (
        <form onSubmit={handleAdd} className="rounded-md border border-line bg-zinc-50 p-4 grid gap-4 transition-all">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="symbol" className="block text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-1">
                Stock Symbol
              </label>
              <input
                id="symbol"
                type="text"
                placeholder="e.g. NVDA"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                required
              />
            </div>
            <div>
              <label htmlFor="reason" className="block text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-1">
                Thesis / Monitoring Reason
              </label>
              <input
                id="reason"
                type="text"
                placeholder="e.g. Watch for entry near support level"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                required
              />
            </div>
            <div>
              <label htmlFor="targetAdd" className="block text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-1">
                Target Add Price ($)
              </label>
              <input
                id="targetAdd"
                type="number"
                step="0.01"
                placeholder="e.g. 110.00"
                value={targetAdd}
                onChange={(e) => setTargetAdd(e.target.value)}
                className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div>
              <label htmlFor="targetTrim" className="block text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-1">
                Target Trim Price ($)
              </label>
              <input
                id="targetTrim"
                type="number"
                step="0.01"
                placeholder="e.g. 160.00"
                value={targetTrim}
                onChange={(e) => setTargetTrim(e.target.value)}
                className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-400 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
          </div>

          {error && <p className="text-xs text-danger font-medium">{error}</p>}

          <div className="flex justify-end gap-2 border-t border-line pt-3">
            <button
              type="button"
              onClick={() => setIsAdding(false)}
              className="rounded-md border border-line bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-accent/90 focus:outline-none disabled:opacity-60 transition-colors"
            >
              <Check size={14} />
              {isLoading ? "Adding..." : "Add to Watchlist"}
            </button>
          </div>
        </form>
      )}

      {items.length === 0 ? (
        <div className="rounded-md border border-line bg-white p-8 text-center">
          <Eye className="mx-auto text-zinc-300 mb-2" size={32} />
          <p className="text-sm font-semibold text-zinc-700">Watchlist is empty</p>
          <p className="text-xs text-zinc-500 mt-1">Add stocks above to begin monitoring technical trends and research metrics.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <div
              key={String(item.id)}
              className="rounded-md border border-line bg-white p-4 shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/holdings/detail?symbol=${encodeURIComponent(item.symbol.toUpperCase())}`}
                      className="text-lg font-bold text-zinc-900 hover:text-accent hover:underline flex items-center gap-1 group"
                    >
                      {item.symbol}
                      <TrendingUp size={14} className="text-zinc-400 group-hover:text-accent transition-colors" />
                    </Link>
                    <span className="rounded bg-panel px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-600 border border-line">
                      {item.status}
                    </span>
                  </div>
                  <button
                    onClick={() => handleDelete(item.id)}
                    className="p-1 rounded text-zinc-400 hover:text-danger hover:bg-red-50 transition-colors"
                    title="Remove from Watchlist"
                    aria-label={`Remove ${item.symbol} from watchlist`}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                <p className="mt-2.5 text-xs text-zinc-600 leading-normal font-medium italic">
                  &ldquo;{item.reason}&rdquo;
                </p>
              </div>

              <div className="mt-4 border-t border-zinc-100 pt-3 grid grid-cols-2 gap-2 text-[11px]">
                <div className="p-1.5 bg-emerald-50/50 rounded border border-emerald-100/50">
                  <span className="text-zinc-500 block font-medium">Target Add</span>
                  <span className="font-bold text-emerald-700 text-sm">
                    {item.target_add_price ? `$${item.target_add_price.toFixed(2)}` : "None"}
                  </span>
                </div>
                <div className="p-1.5 bg-amber-50/50 rounded border border-amber-100/50">
                  <span className="text-zinc-500 block font-medium">Trim Review</span>
                  <span className="font-bold text-amber-700 text-sm">
                    {item.target_trim_review_price ? `$${item.target_trim_review_price.toFixed(2)}` : "None"}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
