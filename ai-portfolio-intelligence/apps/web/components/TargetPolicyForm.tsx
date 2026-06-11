"use client";

import { useEffect, useState } from "react";
import { Settings, Save } from "lucide-react";
import { getPortfolioPolicy, updatePortfolioPolicy } from "@/lib/api";

export function TargetPolicyForm() {
  const [policy, setPolicy] = useState<any>({
    target_equity_percent: 85.0,
    target_cash_percent: 15.0,
    target_bond_percent: 0.0,
    max_single_stock_weight: 12.0,
    max_speculative_weight: 5.0,
    max_sector_weight: 35.0,
    max_options_exposure: 3.0,
    minimum_cash: 10000.0,
    benchmark: "SPY",
    rebalancing_drift_threshold: 5.0
  });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await getPortfolioPolicy();
        setPolicy(data);
      } catch (exc) {
        setError("Could not load portfolio policy parameters.");
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, []);

  async function save() {
    setIsSaving(true);
    setError(null);
    setStatus(null);
    try {
      // Validate percentages sum to 100
      const totalAlloc = policy.target_equity_percent + policy.target_cash_percent + policy.target_bond_percent;
      if (Math.abs(totalAlloc - 100.0) > 0.01) {
        setError(`Target allocations (Equity, Cash, Bond) must sum to 100% (currently ${totalAlloc}%).`);
        setIsSaving(false);
        return;
      }
      
      await updatePortfolioPolicy(policy);
      setStatus("Investment Policy Statement (IPS) targets saved successfully.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save policy");
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return <div className="mt-4 text-sm text-zinc-500">Loading portfolio policy targets...</div>;
  }

  return (
    <div className="mt-4 rounded-md border border-line bg-panel p-4">
      <div className="mb-4 flex items-center gap-2 text-base font-semibold">
        <Settings size={18} aria-hidden />
        Investment Policy Statement (IPS) Targets
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Target Equity Allocation (%)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="number"
            value={policy.target_equity_percent}
            onChange={(event) => setPolicy({ ...policy, target_equity_percent: parseFloat(event.target.value) || 0 })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Target Cash Allocation (%)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="number"
            value={policy.target_cash_percent}
            onChange={(event) => setPolicy({ ...policy, target_cash_percent: parseFloat(event.target.value) || 0 })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Target Bond Allocation (%)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="number"
            value={policy.target_bond_percent}
            onChange={(event) => setPolicy({ ...policy, target_bond_percent: parseFloat(event.target.value) || 0 })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Max Single Stock Weight (%)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="number"
            value={policy.max_single_stock_weight}
            onChange={(event) => setPolicy({ ...policy, max_single_stock_weight: parseFloat(event.target.value) || 0 })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Max Speculative Weight (%)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="number"
            value={policy.max_speculative_weight}
            onChange={(event) => setPolicy({ ...policy, max_speculative_weight: parseFloat(event.target.value) || 0 })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Max Sector Weight (%)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="number"
            value={policy.max_sector_weight}
            onChange={(event) => setPolicy({ ...policy, max_sector_weight: parseFloat(event.target.value) || 0 })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Max Options Exposure (%)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="number"
            value={policy.max_options_exposure}
            onChange={(event) => setPolicy({ ...policy, max_options_exposure: parseFloat(event.target.value) || 0 })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Minimum Cash Floor ($)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="number"
            value={policy.minimum_cash}
            onChange={(event) => setPolicy({ ...policy, minimum_cash: parseFloat(event.target.value) || 0 })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Benchmark Reference Index</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="text"
            value={policy.benchmark}
            onChange={(event) => setPolicy({ ...policy, benchmark: event.target.value.toUpperCase() })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Rebalancing Drift Trigger Threshold (%)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="number"
            value={policy.rebalancing_drift_threshold}
            onChange={(event) => setPolicy({ ...policy, rebalancing_drift_threshold: parseFloat(event.target.value) || 0 })}
          />
        </div>
      </div>
      <div className="mt-4">
        <button
          className="inline-flex items-center justify-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          onClick={save}
          disabled={isSaving}
        >
          <Save size={16} aria-hidden />
          {isSaving ? "Saving..." : "Save Policy"}
        </button>
      </div>
      {status ? <p className="mt-3 rounded-md border border-accent bg-teal-50 p-2 text-sm text-accent">{status}</p> : null}
      {error ? <p className="mt-3 rounded-md border border-danger bg-red-50 p-2 text-sm text-danger">{error}</p> : null}
    </div>
  );
}
