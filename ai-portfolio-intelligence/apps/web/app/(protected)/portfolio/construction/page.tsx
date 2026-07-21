"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getConstructionScenarios, getReplacementUniverse } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

function ConstructionContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const { data, error, loading } = useClientResource(
    () =>
      Promise.all([
        getConstructionScenarios(accountId),
        getReplacementUniverse(accountId).catch(() => ({
          buy_candidates: [],
          core_etf: null,
          prohibited_symbols: [],
          preferred_asset_classes: [],
        })),
      ]),
    [accountId],
  );
  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  const [scenariosPayload, universeRaw] = data ?? [{ scenarios: [] }, {}];
  const universe = (universeRaw || {}) as Record<string, unknown>;
  const scenarios = Array.isArray(scenariosPayload?.scenarios)
    ? (scenariosPayload.scenarios as Array<Record<string, unknown>>)
    : [];
  const buyCandidates = Array.isArray(universe.buy_candidates)
    ? (universe.buy_candidates as string[])
    : [];
  const prohibited = Array.isArray(universe.prohibited_symbols)
    ? (universe.prohibited_symbols as string[])
    : [];
  const preferred = Array.isArray(universe.preferred_asset_classes)
    ? (universe.preferred_asset_classes as string[])
    : [];
  const constraints =
    universe.constraints && typeof universe.constraints === "object"
      ? (universe.constraints as Record<string, unknown>)
      : {
          core_etf: universe.core_etf ?? null,
          prohibited_symbols: prohibited,
          preferred_asset_classes: preferred,
          source: universe.source,
        };

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Construction</p>
        <h2 className="text-3xl font-semibold">Scenario comparison</h2>
        <p className="text-sm text-zinc-600">
          Every run includes a no-trade baseline. No orders are generated.
        </p>
      </div>
      <Disclaimer />
      <div className="overflow-x-auto rounded-md border border-line bg-white">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-line bg-panel text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-3 py-2">Scenario</th>
              <th className="px-3 py-2">Turnover</th>
              <th className="px-3 py-2">Ready</th>
              <th className="px-3 py-2">Blockers</th>
            </tr>
          </thead>
          <tbody>
            {scenarios.map((row) => (
              <tr key={String(row.scenario_id)} className="border-b border-line last:border-0">
                <td className="px-3 py-2 font-medium">{String(row.scenario_type)}</td>
                <td className="px-3 py-2">{String(row.turnover ?? "—")}</td>
                <td className="px-3 py-2">{row.implementation_ready ? "yes" : "no"}</td>
                <td className="px-3 py-2 text-amber-800">
                  {Array.isArray(row.blockers) ? (row.blockers as string[]).slice(0, 3).join(", ") || "—" : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="grid gap-4 md:grid-cols-3">
        <div className="rounded-md border border-line bg-white p-4 text-sm">
          <h3 className="mb-2 font-semibold">Buy candidates</h3>
          {buyCandidates.length === 0 ? (
            <p className="text-zinc-600">No watchlist/plan candidates outside current holdings.</p>
          ) : (
            <ul className="grid gap-1">
              {buyCandidates.map((sym) => (
                <li key={sym} className="border-b border-line py-1 last:border-0">
                  {sym}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="rounded-md border border-line bg-white p-4 text-sm">
          <h3 className="mb-2 font-semibold">Core ETF</h3>
          <p className="font-medium">{String(universe.core_etf || constraints.core_etf || "Not configured")}</p>
          <p className="mt-2 text-xs text-zinc-500">
            Sourced from plan policy constraints or approved watchlist ETFs only.
          </p>
        </div>
        <div className="rounded-md border border-line bg-white p-4 text-sm">
          <h3 className="mb-2 font-semibold">Constraints</h3>
          <dl className="grid gap-2">
            <div>
              <span className="text-zinc-500">Prohibited</span>
              <div>{prohibited.length ? prohibited.join(", ") : "None"}</div>
            </div>
            <div>
              <span className="text-zinc-500">Preferred classes</span>
              <div>{preferred.length ? preferred.join(", ") : "None"}</div>
            </div>
            <div>
              <span className="text-zinc-500">Source</span>
              <div>{String(constraints.source || universe.source || "plan_and_watchlist")}</div>
            </div>
          </dl>
        </div>
      </section>
    </div>
  );
}

export default function ConstructionPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <ConstructionContent />
    </Suspense>
  );
}
