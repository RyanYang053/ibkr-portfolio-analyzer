"use client";

import { useState } from "react";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { approveMethodology, getMethodologies } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

export default function MethodologiesPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const { data, error, loading } = useClientResource(() => getMethodologies(), [refreshKey]);

  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  const items = (data?.methodologies as Array<Record<string, unknown>> | undefined) ?? [];

  async function onApprove(methodologyId: string, version: string) {
    setBusyId(methodologyId);
    setMessage(null);
    try {
      await approveMethodology({
        methodology_id: methodologyId,
        version,
        approver: "owner",
        notes: "Personal-use approval recorded from Methodologies UI",
      });
      setMessage(`Recorded approval for ${methodologyId} ${version}`);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Approval failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Governance</p>
        <h2 className="text-3xl font-semibold">Methodologies</h2>
        <p className="text-sm text-zinc-600">
          Approvals are personal-use records only. Valuation and tax remain experimental until fixtures pass.
        </p>
      </div>
      <Disclaimer />
      {message ? <p className="rounded-md border border-line bg-panel p-3 text-sm">{message}</p> : null}
      <div className="grid gap-2">
        {items.map((m) => {
          const methodologyId = String(m.methodology_id);
          const version = String(m.version || "0.0.0");
          const status = String(m.status || "experimental");
          const approved = status === "approved_for_personal_use";
          return (
            <div key={methodologyId} className="rounded-md border border-line bg-white p-4 text-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">{String(m.name || methodologyId)}</div>
                  <div className="text-zinc-600">
                    Status: {status} · Version: {version}
                  </div>
                </div>
                <button
                  type="button"
                  className="rounded-md border border-line px-3 py-1.5 text-xs hover:bg-panel disabled:opacity-50"
                  disabled={approved || busyId === methodologyId}
                  onClick={() => onApprove(methodologyId, version)}
                >
                  {approved ? "Approved" : busyId === methodologyId ? "Saving…" : "Approve for personal use"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
