"use client";

import { Suspense } from "react";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getDataHealth } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

function DataHealthContent() {
  const { data, error, loading } = useClientResource(() => getDataHealth(), []);
  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  const checks = Array.isArray(data?.checks) ? (data?.checks as Array<Record<string, string>>) : [];
  const database = (data?.database || {}) as Record<string, unknown>;
  const calibration = (data?.calibration || {}) as Record<string, unknown>;

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Data health</p>
        <h2 className="text-3xl font-semibold">Evidence and readiness</h2>
        <p className="text-sm text-zinc-600">
          Overall: {String(data?.overall_status || "unknown")} · Missing fields never silently become zero.
        </p>
      </div>
      <Disclaimer />
      <div className="grid gap-3 md:grid-cols-2">
        {checks.map((check) => (
          <div key={check.id} className="rounded-md border border-line bg-white p-4 text-sm">
            <div className="font-semibold capitalize">
              {check.id.replaceAll("_", " ")} · {check.status}
            </div>
            <p className="mt-1 text-zinc-700">{check.detail}</p>
          </div>
        ))}
      </div>
      <section className="rounded-md border border-line bg-white p-4 text-sm">
        <h3 className="mb-2 font-semibold">Decision calibration</h3>
        {Object.keys(calibration).length === 0 ? (
          <p className="text-zinc-600">No calibration observations yet. Respond to decisions to start the record.</p>
        ) : (
          <dl className="grid gap-2 md:grid-cols-2">
            {Object.entries(calibration).map(([key, value]) => (
              <div key={key} className="flex justify-between gap-3 border-b border-line py-1">
                <dt className="text-zinc-600">{key.replaceAll("_", " ")}</dt>
                <dd className="font-medium">{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>
      <section className="rounded-md border border-line bg-white p-4 text-sm">
        <h3 className="mb-2 font-semibold">Database</h3>
        <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-zinc-700">
          {JSON.stringify(database, null, 2)}
        </pre>
      </section>
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
