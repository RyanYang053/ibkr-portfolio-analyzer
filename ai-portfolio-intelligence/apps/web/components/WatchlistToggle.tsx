"use client";

import { useState } from "react";
import { Star, X, Check, Loader2 } from "lucide-react";
import { addWatchlistItem, deleteWatchlistItem, getWatchlist } from "@/lib/api";

interface WatchlistToggleProps {
  symbol: string;
  initialWatchlistItem: { id: number; reason: string } | null;
}

export function WatchlistToggle({ symbol, initialWatchlistItem }: WatchlistToggleProps) {
  const [watchItem, setWatchItem] = useState<{ id: number; reason: string } | null>(initialWatchlistItem);
  const [isOpen, setIsOpen] = useState(false);
  const [reason, setReason] = useState("Monitored from research page");
  const [targetAdd, setTargetAdd] = useState("");
  const [targetTrim, setTargetTrim] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isWatched = !!watchItem;

  async function handleToggle() {
    if (isWatched) {
      if (!confirm(`Remove ${symbol} from watchlist?`)) return;
      setIsLoading(true);
      try {
        await deleteWatchlistItem(watchItem.id);
        setWatchItem(null);
      } catch (exc) {
        alert(exc instanceof Error ? exc.message : "Failed to remove from watchlist");
      } finally {
        setIsLoading(false);
      }
    } else {
      setIsOpen(true);
    }
  }

  async function handleAddSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    try {
      const payload = {
        symbol: symbol.toUpperCase(),
        reason: reason.trim(),
        target_add_price: targetAdd ? parseFloat(targetAdd) : undefined,
        target_trim_review_price: targetTrim ? parseFloat(targetTrim) : undefined,
      };
      
      const response = await addWatchlistItem(payload);
      
      // Query watchlist to get the correct item ID
      const watchlist = await getWatchlist() as Array<{ id: number; symbol: string; reason: string }>;
      const addedItem = watchlist.find((item) => item.symbol.toUpperCase() === symbol.toUpperCase());
      
      setWatchItem(addedItem ? { id: addedItem.id, reason: addedItem.reason } : { id: Date.now(), reason: payload.reason });
      setIsOpen(false);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Failed to add to watchlist");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="relative inline-block">
      <button
        onClick={handleToggle}
        disabled={isLoading}
        className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-semibold shadow-sm transition-all focus:outline-none ${
          isWatched
            ? "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100"
            : "border-line bg-white text-zinc-600 hover:bg-zinc-50"
        }`}
      >
        {isLoading ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Star size={14} className={isWatched ? "fill-amber-500 text-amber-500" : "text-zinc-400"} />
        )}
        {isWatched ? "Watching" : "Add to Watchlist"}
      </button>

      {isOpen && (
        <div className="absolute left-0 mt-2 z-50 w-72 rounded-md border border-line bg-white p-4 shadow-lg ring-1 ring-black ring-opacity-5">
          <div className="flex items-center justify-between border-b border-line pb-2 mb-3">
            <span className="text-xs font-bold text-zinc-700 uppercase tracking-wide">Watch {symbol}</span>
            <button onClick={() => setIsOpen(false)} className="text-zinc-400 hover:text-zinc-600">
              <X size={14} />
            </button>
          </div>
          <form onSubmit={handleAddSubmit} className="grid gap-3">
            <div>
              <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500 mb-1">
                Monitoring Reason
              </label>
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full rounded-md border border-line px-2 py-1 text-xs text-zinc-900 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500 mb-1">
                  Target Add ($)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={targetAdd}
                  onChange={(e) => setTargetAdd(e.target.value)}
                  placeholder="Optional"
                  className="w-full rounded-md border border-line px-2 py-1 text-xs text-zinc-900 focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500 mb-1">
                  Trim Price ($)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={targetTrim}
                  onChange={(e) => setTargetTrim(e.target.value)}
                  placeholder="Optional"
                  className="w-full rounded-md border border-line px-2 py-1 text-xs text-zinc-900 focus:border-accent focus:outline-none"
                />
              </div>
            </div>

            {error && <p className="text-[10px] text-danger font-medium">{error}</p>}

            <div className="flex justify-end gap-1.5 border-t border-line pt-2 mt-1">
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="rounded border border-line bg-white px-2 py-1 text-[10px] font-medium text-zinc-600 hover:bg-zinc-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading}
                className="inline-flex items-center gap-1 rounded bg-accent px-2 py-1 text-[10px] font-medium text-white hover:bg-accent/90"
              >
                <Check size={10} />
                Save
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
