"use client";

import { useState } from "react";
import { Brain, RefreshCw } from "lucide-react";
import { refreshAIStockReport } from "@/lib/api";
import type { AIStockReport } from "@/lib/types";

export function AIRefreshPanel({ symbol, initialProvider, initialReport }: { symbol: string; initialProvider: string; initialReport?: AIStockReport | null }) {
  const [report, setReport] = useState<AIStockReport | null>(initialReport ?? null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setIsLoading(true);
    setError(null);
    try {
      setReport(await refreshAIStockReport(symbol));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "AI refresh failed");
    } finally {
      setIsLoading(false);
    }
  }

  const active = report;

  return (
    <section className="rounded-md border border-line bg-white p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Brain size={18} aria-hidden /> AI Research Refresh
          </h3>
          <p className="text-sm text-zinc-600">
            Provider: {active?.provider ?? initialProvider}. Manual refresh calls the backend AI workflow.
          </p>
        </div>
        <button
          className="inline-flex items-center justify-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          onClick={refresh}
          disabled={isLoading}
        >
          <RefreshCw size={16} aria-hidden className={isLoading ? "animate-spin" : ""} />
          {isLoading ? "Analyzing" : "Refresh analysis"}
        </button>
      </div>

      {error ? <p className="mt-3 rounded-md border border-danger bg-red-50 p-3 text-sm text-danger">{error}</p> : null}

      {active ? (
        <div className="mt-4 grid gap-4">
          <div className="rounded-md bg-panel p-3">
            <div className="text-xs uppercase tracking-wide text-zinc-500">AI action category</div>
            <div className="text-2xl font-semibold">{active.action}</div>
            <p className="mt-1 text-sm text-zinc-700">Confidence: {active.confidence} · cap {active.confidence_limits?.confidence_cap}</p>
            <p className="mt-1 text-sm text-zinc-700">Thesis: {active.thesis?.status?.replaceAll("_", " ")}</p>
          </div>
          <div className="grid gap-3 text-sm lg:grid-cols-2">
            <p><strong>Summary:</strong> {active.summary}</p>
            <p><strong>Why action:</strong> {active.why_action?.text}</p>
            <p><strong>Business:</strong> {active.business_summary}</p>
            <p><strong>Valuation:</strong> {active.valuation_view}</p>
            <p><strong>Technical:</strong> {active.technical_view}</p>
            <p><strong>Risk:</strong> {active.risk_view}</p>
            <p><strong>Add zone:</strong> {active.add_zone ?? "Unavailable because required data is missing."}</p>
            <p><strong>Exit trigger:</strong> {active.exit_review_trigger}</p>
          </div>
          <div className="rounded-md border border-line p-3">
            <h4 className="text-sm font-semibold">Evidence-linked claims</h4>
            <div className="mt-2 grid gap-2 text-sm">
              {active.claims?.map((claim) => (
                <div key={claim.id}>
                  <p>{claim.text}</p>
                  <p className="text-xs text-zinc-500">Evidence: {claim.evidence_ids.join(", ")}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-md border border-line p-3 text-sm">
            <h4 className="font-semibold">Missing and stale data</h4>
            <p>Missing: {active.data_quality?.missing_categories?.join(", ") || "none"}</p>
            <p>Stale: {active.data_quality?.stale_categories?.join(", ") || "none"}</p>
          </div>
          {active.provider_error ? (
            <p className="rounded-md border border-warning bg-amber-50 p-3 text-sm text-warning">
              Gemini call failed, so a deterministic no-trading fallback was used: {active.provider_error}
            </p>
          ) : null}
          <p className="text-xs text-zinc-600">{active.disclaimer}</p>
        </div>
      ) : null}
    </section>
  );
}
