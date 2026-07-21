"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { Disclaimer } from "@/components/Disclaimer";
import { DecisionCenterClient } from "@/components/decision-center/DecisionCenterClient";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getDecisionCenter } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

function DecisionCenterContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const { data: payload, error, loading } = useClientResource(
    () => getDecisionCenter(accountId),
    [accountId],
  );

  if (loading) {
    return <PageLoading />;
  }

  const holdings = Array.isArray(payload?.holdings)
    ? (payload?.holdings as Array<Record<string, unknown>>)
    : [];
  const methodologyStatus = String(payload?.methodology_status || "experimental");

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Decision support</p>
        <h2 className="text-3xl font-semibold">Decision Center</h2>
        <p className="mt-1 max-w-3xl text-sm text-zinc-600">
          Ordered deterministic gates and investor lenses for holding review. Valuation may be
          approved_for_personal_use when golden fixtures pass; Review Add still requires packet gates.
        </p>
      </div>
      <Disclaimer />
      {error ? (
        <PageErrorBanner message={error} />
      ) : (
        <DecisionCenterClient
          accountId={accountId}
          methodologyStatus={methodologyStatus}
          holdings={holdings.map((row) => ({
            instrument_key: String(row.instrument_key || row.symbol || ""),
            symbol: String(row.symbol || ""),
            action: String(row.action || ""),
            valuation_status: String(row.valuation_status || "withheld"),
          }))}
        />
      )}
    </div>
  );
}

export default function DecisionCenterPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <DecisionCenterContent />
    </Suspense>
  );
}
