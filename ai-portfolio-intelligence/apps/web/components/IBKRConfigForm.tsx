"use client";

import { useEffect, useState } from "react";
import { Plug, Save } from "lucide-react";
import { configureBrokerReadonly, getAccounts, getBrokerStatus } from "@/lib/api";
import { useAppRouter } from "@/lib/use-app-router";

type IBKRConfigFormProps = {
  defaultMode?: string;
  defaultHost?: string;
  defaultPort?: string;
  defaultClientId?: string;
  defaultAccountId?: string;
};

export function IBKRConfigForm({
  defaultMode = "ibkr_readonly",
  defaultHost = "127.0.0.1",
  defaultPort = "4002",
  defaultClientId = "10",
  defaultAccountId = "",
}: IBKRConfigFormProps) {
  const [mode, setMode] = useState(defaultMode);
  const [host, setHost] = useState(defaultHost);
  const [port, setPort] = useState(defaultPort);
  const [clientId, setClientId] = useState(defaultClientId);
  const [accountId, setAccountId] = useState(defaultAccountId);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [discoveredAccounts, setDiscoveredAccounts] = useState<string[]>([]);
  const router = useAppRouter();

  useEffect(() => {
    setMode(defaultMode);
    setHost(defaultHost);
    setPort(defaultPort);
    setClientId(defaultClientId);
    setAccountId(defaultAccountId);
  }, [defaultMode, defaultHost, defaultPort, defaultClientId, defaultAccountId]);

  useEffect(() => {
    getBrokerStatus().then((info) => {
      if (info) {
        if (info.mode) setMode(info.mode);
        if (info.host) setHost(info.host);
        if (info.port) setPort(info.port);
        if (info.client_id) setClientId(info.client_id);
        if (info.account_id) setAccountId(info.account_id);
      }
    }).catch(() => {});
  }, []);

  async function save() {
    setIsSaving(true);
    setError(null);
    setStatus(null);
    setDiscoveredAccounts([]);
    try {
      const response = await configureBrokerReadonly({
        mode,
        host,
        port: Number(port),
        client_id: Number(clientId),
        account_id: accountId || undefined
      });
      if (response.mode === "mock_ibkr_readonly") {
        setStatus("Switched to Demo/Simulation Mode. Open Portfolio to view mock holdings.");
        return;
      }

      let ids: string[] = [];
      try {
        const accounts = await getAccounts();
        ids = (accounts || []).map((item: { id: string }) => String(item.id));
        setDiscoveredAccounts(ids);
      } catch {
        // Discovery can fail while TWS farms are down; settings are still saved.
      }

      if (ids.length === 1 && !accountId) {
        await configureBrokerReadonly({
          mode,
          host,
          port: Number(port),
          client_id: Number(clientId),
          account_id: ids[0],
        });
        setAccountId(ids[0]);
        setStatus(`IBKR settings saved. Using account ${ids[0]}. Open Portfolio to refresh.`);
        router.push(`/portfolio/?account_id=${encodeURIComponent(ids[0])}`);
        return;
      }

      if (ids.length > 1) {
        setStatus(
          `IBKR settings saved for ${response.host}:${response.port}. ` +
            `Detected ${ids.length} accounts (${ids.join(", ")}). ` +
            `Pick an Account ID below (or use Active Account → Consolidated View), save again, then open Portfolio.`,
        );
        return;
      }

      setStatus(`IBKR read-only settings saved for ${response.host}:${response.port}. Open Portfolio to refresh.`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not configure IBKR");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="mt-4 rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Plug size={16} aria-hidden />
        Connect portfolio data
      </div>
      
      <div className="mb-4">
        <label className="grid gap-1 text-sm font-medium">
          Connection Mode
          <select
            className="rounded-md border border-line bg-white px-3 py-2 text-sm"
            value={mode}
            onChange={(event) => setMode(event.target.value)}
          >
            <option value="mock_ibkr_readonly">Demo Mode (Simulated / Mock Holdings)</option>
            <option value="ibkr_readonly">Local IB Gateway / TWS Connection (Actual Holdings)</option>
          </select>
        </label>
      </div>

      {mode === "ibkr_readonly" && (
        <div className="grid gap-3 md:grid-cols-2 border-t border-line pt-3">
          <label className="grid gap-1 text-sm">
            Host
            <input className="rounded-md border border-line px-3 py-2" value={host} onChange={(event) => setHost(event.target.value)} />
          </label>
          <label className="grid gap-1 text-sm">
            Socket port
            <input className="rounded-md border border-line px-3 py-2" value={port} onChange={(event) => setPort(event.target.value)} />
          </label>
          <label className="grid gap-1 text-sm">
            Client ID
            <input className="rounded-md border border-line px-3 py-2" value={clientId} onChange={(event) => setClientId(event.target.value)} />
          </label>
          <label className="grid gap-1 text-sm">
            Account ID (optional)
            {discoveredAccounts.length > 0 ? (
              <select
                className="rounded-md border border-line px-3 py-2 bg-white"
                value={accountId}
                onChange={(event) => setAccountId(event.target.value)}
              >
                <option value="">Consolidated / pick later in sidebar</option>
                {discoveredAccounts.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className="rounded-md border border-line px-3 py-2"
                value={accountId}
                onChange={(event) => setAccountId(event.target.value)}
                placeholder="Leave blank to auto-detect"
              />
            )}
          </label>
        </div>
      )}

      <button
        className="mt-4 inline-flex items-center justify-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        onClick={save}
        disabled={isSaving || (mode === "ibkr_readonly" && (!host || !port || !clientId))}
      >
        <Save size={16} aria-hidden />
        {isSaving ? "Saving" : "Save settings"}
      </button>

      {mode === "ibkr_readonly" ? (
        <div className="mt-3 text-xs text-zinc-600 space-y-1">
          <p>
            <strong>Note:</strong> This connects via a local socket. You must log into IB Gateway or TWS first.
          </p>
          <p>
            <strong>Port Guidelines:</strong> IB Gateway uses <code>4001</code> (Live) / <code>4002</code> (Paper). TWS uses <code>7496</code> (Live) / <code>7497</code> (Paper).
          </p>
          <p>
            Ensure <strong>&quot;Enable ActiveX and Socket Clients&quot;</strong> is checked in TWS settings under Configuration → API → Settings.
          </p>
        </div>
      ) : (
        <p className="mt-3 text-xs text-zinc-600">
          Demo mode loads a mock portfolio containing pre-analyzed assets like Amazon, Tesla, etc.
        </p>
      )}

      {status ? <p className="mt-3 rounded-md border border-accent bg-teal-50 p-2 text-sm text-accent">{status}</p> : null}
      {error ? <p className="mt-3 rounded-md border border-danger bg-red-50 p-2 text-sm text-danger">{error}</p> : null}
    </div>
  );
}
