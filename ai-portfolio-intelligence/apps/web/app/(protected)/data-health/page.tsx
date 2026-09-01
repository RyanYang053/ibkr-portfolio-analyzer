"use client";

import { Suspense } from "react";
import { Database, Gauge } from "lucide-react";

import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge, toneForStatus } from "@/components/ui/Badge";
import { getDataHealth } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";
import { displayValue, humanizeCode } from "@/lib/format";

/** Broken checks first: a page of green with one red buried in it is a trap. */
const TONE_ORDER = { negative: 0, warning: 1, neutral: 2, info: 2, accent: 2, positive: 3 } as const;

function formatValue(value: unknown): string {
  if (typeof value === "object" && value !== null) {
    const entries = Object.entries(value as Record<string, unknown>);
    // An empty counts object means "nothing recorded", not a literal "{}".
    if (entries.length === 0) return "None recorded";
    return entries.map(([key, count]) => `${humanizeCode(key)}: ${String(count)}`).join(", ");
  }
  return displayValue(value);
}

function DataHealthContent() {
  const { data, error, loading, refreshing, stale, reload } = useClientResource(() => getDataHealth(), []);
  if (loading) return <PageLoading label="Loading data health" />;
  if (error && !data) return <PageErrorBanner message={error} onRetry={reload} />;

  const checks = Array.isArray(data?.checks) ? (data?.checks as Array<Record<string, string>>) : [];
  const database = (data?.database || {}) as Record<string, unknown>;
  const calibration = (data?.calibration || {}) as Record<string, unknown>;

  const ordered = [...checks].sort(
    (a, b) => TONE_ORDER[toneForStatus(a.status)] - TONE_ORDER[toneForStatus(b.status)],
  );
  const failing = ordered.filter((check) => toneForStatus(check.status) === "negative").length;

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Data health"
        title="Evidence and readiness"
        description={`Overall: ${humanizeCode(data?.overall_status, "unknown")}. A field that could not be measured is reported as missing — it never silently becomes zero.`}
        refreshing={refreshing}
        stale={stale}
      />
      <Disclaimer />
      {error ? <PageErrorBanner message={error} onRetry={reload} /> : null}

      <section aria-label="Readiness checks" className="grid gap-3 md:grid-cols-2">
        {ordered.length === 0 ? (
          <EmptyState
            className="md:col-span-2"
            title="No readiness checks reported"
            description="The backend returned no checks. That is itself a gap — it does not mean the data is healthy."
          />
        ) : (
          ordered.map((check) => (
            <Card key={check.id} tone={toneForStatus(check.status) === "negative" ? "negative" : "default"}>
              <div className="flex items-start justify-between gap-3">
                <h3 className="text-sm font-semibold text-zinc-900">{humanizeCode(check.id)}</h3>
                <StatusBadge value={check.status} />
              </div>
              <p className="mt-1.5 text-sm leading-6 text-zinc-600">{check.detail}</p>
            </Card>
          ))
        )}
      </section>

      <Card>
        <CardHeader
          icon={<Gauge size={16} aria-hidden className="text-zinc-400" />}
          title="Decision calibration"
          description="How the recorded outcomes compare with what the packets predicted."
          actions={
            failing > 0 ? (
              <span className="text-xs font-medium text-negative">{failing} failing checks</span>
            ) : null
          }
        />
        {Object.keys(calibration).length === 0 ? (
          <EmptyState
            title="No calibration observations yet"
            description="Respond to decisions in the queue to start building the record."
          />
        ) : (
          <dl className="grid gap-x-6 gap-y-0 text-sm md:grid-cols-2">
            {Object.entries(calibration).map(([key, value]) => (
              <div key={key} className="flex items-baseline justify-between gap-3 border-b border-hairline py-1.5">
                <dt className="text-zinc-600">{humanizeCode(key)}</dt>
                <dd className="num text-right font-medium text-zinc-900">{formatValue(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </Card>

      <Card>
        <CardHeader
          icon={<Database size={16} aria-hidden className="text-zinc-400" />}
          title="Storage"
          description="Where local state lives and whether it is reachable."
        />
        <dl className="grid gap-x-6 gap-y-0 text-sm md:grid-cols-2">
          {Object.entries(database)
            .filter(([, value]) => typeof value !== "object")
            .map(([key, value]) => (
              <div key={key} className="flex items-baseline justify-between gap-3 border-b border-hairline py-1.5">
                <dt className="text-zinc-600">{humanizeCode(key)}</dt>
                <dd className="text-right font-medium text-zinc-900">{formatValue(value)}</dd>
              </div>
            ))}
        </dl>
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-medium text-zinc-500 hover:text-zinc-900">
            Raw diagnostics
          </summary>
          <pre className="mt-2 overflow-x-auto rounded-md bg-panel p-3 text-xs leading-5 text-zinc-600">
            {JSON.stringify(database, null, 2)}
          </pre>
        </details>
      </Card>
    </div>
  );
}

export default function DataHealthPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <DataHealthContent />
    </Suspense>
  );
}
