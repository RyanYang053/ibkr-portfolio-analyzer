"use client";

import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getAuditLogs } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

export default function AuditPage() {
  const { data: logs, error, loading } = useClientResource(
    () => getAuditLogs() as Promise<Array<Record<string, string>>>,
    [],
  );

  if (loading) {
    return <PageLoading />;
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Security and activity</p>
        <h2 className="text-3xl font-semibold">Audit Log</h2>
      </div>
      <Disclaimer />
      {error ? <PageErrorBanner message={error} /> : null}
      <div className="overflow-x-auto rounded-md border border-line bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-panel text-left text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-3 py-3">Action</th>
              <th className="px-3 py-3">Object Type</th>
              <th className="px-3 py-3">Object ID</th>
            </tr>
          </thead>
          <tbody>
            {(logs ?? []).map((log, index) => (
              <tr key={`${log.action}-${index}`} className="border-t border-line">
                <td className="px-3 py-3">{log.action}</td>
                <td className="px-3 py-3">{log.object_type}</td>
                <td className="px-3 py-3">{log.object_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
