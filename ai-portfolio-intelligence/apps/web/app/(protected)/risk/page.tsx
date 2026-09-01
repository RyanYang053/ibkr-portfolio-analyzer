"use client";

import { Suspense, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { ShieldAlert, PieChart } from "lucide-react";

import { Disclaimer } from "@/components/Disclaimer";
import { DonutChart } from "@/components/DonutChart";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { RiskGauge } from "@/components/RiskGauge";
import { StatCard } from "@/components/StatCard";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/Badge";
import { getRisk } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";
import { formatNumber, formatPercent, humanizeCode } from "@/lib/format";
import type { Alert } from "@/lib/types";

/** Most severe first, so the alert that matters is the one at the top. */
const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  moderate: 2,
  elevated: 2,
  low: 3,
  info: 4,
};

function severityRank(alert: Alert): number {
  return SEVERITY_ORDER[String(alert.severity ?? "").toLowerCase()] ?? 5;
}

function RiskContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const { data: risk, error, loading, refreshing, stale, reload } = useClientResource(
    () => getRisk(accountId),
    [accountId],
  );

  const alerts = useMemo(
    () => [...(risk?.alerts ?? [])].sort((a, b) => severityRank(a) - severityRank(b)),
    [risk],
  );

  if (loading) {
    return <PageLoading label="Loading risk analytics" />;
  }

  if (!risk) {
    return (
      <div className="grid gap-6">
        <Disclaimer />
        <PageErrorBanner message={error ?? "Risk analytics are unavailable."} onRetry={reload} />
      </div>
    );
  }

  const breaches = alerts.filter((alert) => severityRank(alert) <= 1).length;

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Risk monitoring"
        title="Risk Center"
        description="Concentration, leverage and policy breaches for the selected account, measured against your IPS limits."
        refreshing={refreshing}
        stale={stale}
      />
      <Disclaimer />
      {error ? <PageErrorBanner message={error} onRetry={reload} /> : null}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <RiskGauge score={risk.risk_score} label="Portfolio risk score" />
        <StatCard
          label="Top 5 concentration"
          value={formatPercent(risk.top_5_concentration)}
          detail="Share held in the five largest positions"
        />
        <StatCard
          label="Herfindahl index"
          value={formatNumber(risk.herfindahl_concentration_score, 4)}
          detail={humanizeCode(risk.herfindahl_concentration_label)}
        />
        <StatCard
          label="Speculative basket"
          value={formatPercent(risk.speculative_percent)}
          tone="warn"
          detail="Gross exposure to speculative names"
        />
        <StatCard
          label="Margin usage"
          value={formatPercent(risk.margin_usage_percent)}
          detail="Requirement against net liquidation"
        />
      </section>

      <section className="grid items-start gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            icon={<PieChart size={16} aria-hidden className="text-zinc-400" />}
            title="Sector risk"
            description="Share of invested market value by GICS sector."
          />
          <DonutChart data={risk.sector_exposure} title="Sectors" />
        </Card>

        <Card>
          <CardHeader
            icon={<ShieldAlert size={16} aria-hidden className="text-zinc-400" />}
            title="Active alerts"
            description="Policy limits currently breached, most severe first."
            actions={
              breaches > 0 ? (
                <span className="text-xs font-medium text-negative">
                  {breaches} high or critical
                </span>
              ) : null
            }
          />
          <div className="grid gap-2">
            {alerts.length === 0 ? (
              <EmptyState
                title="No policy breaches"
                description="Every IPS limit is currently within tolerance for this account."
              />
            ) : (
              alerts.map((alert) => (
                <div
                  key={`${alert.alert_type}:${alert.symbol ?? ""}`}
                  className="rounded-md border border-hairline bg-panel p-3 text-sm"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="font-semibold text-zinc-900">
                      {humanizeCode(alert.alert_type)}
                      {alert.symbol ? (
                        <span className="ml-1.5 font-normal text-zinc-500">· {alert.symbol}</span>
                      ) : null}
                    </span>
                    <StatusBadge value={alert.severity} />
                  </div>
                  <p className="mt-1 leading-6 text-zinc-600">{alert.message}</p>
                </div>
              ))
            )}
          </div>
        </Card>
      </section>
    </div>
  );
}

export default function RiskPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <RiskContent />
    </Suspense>
  );
}
