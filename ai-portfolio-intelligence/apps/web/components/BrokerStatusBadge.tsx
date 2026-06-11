"use client";

import { useEffect, useState } from "react";
import { Gauge } from "lucide-react";
import { getBrokerStatus } from "@/lib/api";
import type { BrokerStatus } from "@/lib/types";

export function BrokerStatusBadge() {
  const [status, setStatus] = useState<BrokerStatus | null>(null);
  const [mounted, setMounted] = useState(false);
  const [showDiag, setShowDiag] = useState(false);

  useEffect(() => {
    setMounted(true);
    getBrokerStatus().then(setStatus).catch(() => {});
  }, []);

  if (!mounted) {
    return <div className="mt-4 flex items-center gap-2 text-xs font-semibold text-zinc-400 animate-pulse h-4 w-28" />;
  }

  const isConnected = status?.status === "connected" || status?.status === "connected_mock_readonly";
  const statusLabel = isConnected 
    ? `Connected: ${status.mode === "mock_ibkr_readonly" ? "Mock" : `Live`}` 
    : "IBKR not connected";
  const badgeColor = isConnected ? "text-emerald-600" : "text-accent";

  return (
    <div className="mt-4 border-t border-line pt-3">
      <button 
        type="button"
        onClick={() => setShowDiag(!showDiag)}
        className={`flex w-full items-center justify-between text-xs font-semibold ${badgeColor} hover:opacity-85 focus:outline-none`}
        title="Click to toggle connection diagnostics"
      >
        <div className="flex items-center gap-2">
          <Gauge size={16} aria-hidden />
          <span>{statusLabel}</span>
        </div>
        <span className="text-[10px] text-zinc-400">{showDiag ? "▲" : "▼"}</span>
      </button>

      {showDiag && status && (
        <div className="mt-2 rounded bg-zinc-50 border border-line p-2 text-[10px] text-zinc-600 space-y-1">
          <div><strong>Status:</strong> <span className="text-zinc-900">{status.status}</span></div>
          <div><strong>Mode:</strong> <span className="text-zinc-900">{status.mode}</span></div>
          <div><strong>Host Socket:</strong> <span className="text-zinc-900">{status.host ?? "127.0.0.1"}:{status.port ?? "4002"}</span></div>
          <div><strong>Client ID Offset:</strong> <span className="text-zinc-900">{status.client_id ?? "10"}</span></div>
          {status.account_id && <div><strong>Default Acct:</strong> <span className="text-zinc-900">{status.account_id}</span></div>}
          {status.error && <div className="text-red-500 mt-1 border-t border-line/50 pt-1"><strong>Error:</strong> {status.error}</div>}
        </div>
      )}
    </div>
  );
}
