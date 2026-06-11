"use client";

import { useEffect, useState } from "react";
import { Plug, Save } from "lucide-react";
import { configureBrokerReadonly, getBrokerStatus } from "@/lib/api";

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
    try {
      const response = await configureBrokerReadonly({
        mode,
        host,
        port: Number(port),
        client_id: Number(clientId),
        account_id: accountId || undefined
      });
      if (response.mode === "mock_ibkr_readonly") {
        setStatus("Switched to Demo/Simulation Mode. Now refresh Portfolio.");
      } else {
        setStatus(`IBKR read-only settings saved for ${response.host}:${response.port}. Now refresh Portfolio.`);
      }
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
            <input className="rounded-md border border-line px-3 py-2" value={accountId} onChange={(event) => setAccountId(event.target.value)} placeholder="Leave blank to auto-detect" />
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
            Ensure <strong>"Enable ActiveX and Socket Clients"</strong> is checked in TWS settings under Configuration → API → Settings.
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
