import { Disclaimer } from "@/components/Disclaimer";
import { getAuditLogs } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AuditPage() {
  const logs = await getAuditLogs() as Array<Record<string, string>>;

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Security and activity</p>
        <h2 className="text-3xl font-semibold">Audit Log</h2>
      </div>
      <Disclaimer />
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
            {logs.map((log, index) => (
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
