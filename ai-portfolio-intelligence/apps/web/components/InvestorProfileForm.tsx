"use client";

import { useEffect, useState } from "react";
import { User, Save } from "lucide-react";
import { getInvestorProfile, updateInvestorProfile } from "@/lib/api";

export function InvestorProfileForm() {
  const [profile, setProfile] = useState<any>({
    objective: "Growth",
    time_horizon_years: 10,
    risk_tolerance: "High",
    risk_capacity: "Medium",
    liquidity_needs: 10000.0,
    net_worth_range: "100k-500k",
    tax_residency: "Canada",
    account_type: "Tax-Free",
    restrictions: []
  });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [restrictionsText, setRestrictionsText] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const data = await getInvestorProfile();
        setProfile(data);
        if (data.restrictions) {
          setRestrictionsText(data.restrictions.join(", "));
        }
      } catch (exc) {
        setError("Could not load investor profile.");
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
      const parsedRestrictions = restrictionsText
        .split(",")
        .map((r) => r.trim().toUpperCase())
        .filter((r) => r.length > 0);
      const updated = {
        ...profile,
        restrictions: parsedRestrictions
      };
      await updateInvestorProfile(updated);
      setProfile(updated);
      setStatus("Investor profile and suitability parameters saved successfully.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save profile");
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return <div className="mt-4 text-sm text-zinc-500">Loading investor profile...</div>;
  }

  return (
    <div className="mt-4 rounded-md border border-line bg-panel p-4">
      <div className="mb-4 flex items-center gap-2 text-base font-semibold">
        <User size={18} aria-hidden />
        Investor Suitability Profile (KYC)
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Investment Objective</label>
          <select
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            value={profile.objective}
            onChange={(event) => setProfile({ ...profile, objective: event.target.value })}
          >
            <option value="Growth">Growth</option>
            <option value="Income">Income</option>
            <option value="Capital Preservation">Capital Preservation</option>
            <option value="Speculation">Speculation</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Time Horizon (Years)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="number"
            value={profile.time_horizon_years}
            onChange={(event) => setProfile({ ...profile, time_horizon_years: parseInt(event.target.value) || 0 })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Risk Tolerance</label>
          <select
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            value={profile.risk_tolerance}
            onChange={(event) => setProfile({ ...profile, risk_tolerance: event.target.value })}
          >
            <option value="Low">Low</option>
            <option value="Medium">Medium</option>
            <option value="High">High</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Risk Capacity</label>
          <select
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            value={profile.risk_capacity}
            onChange={(event) => setProfile({ ...profile, risk_capacity: event.target.value })}
          >
            <option value="Low">Low</option>
            <option value="Medium">Medium</option>
            <option value="High">High</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Liquidity Needs ($)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="number"
            value={profile.liquidity_needs}
            onChange={(event) => setProfile({ ...profile, liquidity_needs: parseFloat(event.target.value) || 0 })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Account Type</label>
          <select
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            value={profile.account_type}
            onChange={(event) => setProfile({ ...profile, account_type: event.target.value })}
          >
            <option value="Tax-Free">Tax-Free (TFSA/RRSP/Roth)</option>
            <option value="Taxable">Taxable</option>
            <option value="Margin">Margin</option>
            <option value="Corporate">Corporate</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Tax Residency</label>
          <select
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            value={profile.tax_residency}
            onChange={(event) => setProfile({ ...profile, tax_residency: event.target.value })}
          >
            <option value="Canada">Canada</option>
            <option value="US">US</option>
            <option value="Other">Other</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-zinc-600">Net Worth Range</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="text"
            value={profile.net_worth_range}
            onChange={(event) => setProfile({ ...profile, net_worth_range: event.target.value })}
          />
        </div>
        <div className="flex flex-col gap-1 md:col-span-2">
          <label className="text-xs font-semibold text-zinc-600">Symbol Restrictions (Comma Separated)</label>
          <input
            className="rounded-md border border-line px-3 py-2 text-sm bg-white"
            type="text"
            value={restrictionsText}
            onChange={(event) => setRestrictionsText(event.target.value)}
            placeholder="e.g., IONQ, LAES, CELH"
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
          {isSaving ? "Saving..." : "Save Profile"}
        </button>
      </div>
      {status ? <p className="mt-3 rounded-md border border-accent bg-teal-50 p-2 text-sm text-accent">{status}</p> : null}
      {error ? <p className="mt-3 rounded-md border border-danger bg-red-50 p-2 text-sm text-danger">{error}</p> : null}
    </div>
  );
}
