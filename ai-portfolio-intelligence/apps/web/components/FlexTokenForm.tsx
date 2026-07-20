"use client";

import { useEffect, useState } from "react";
import { KeyRound, Trash2 } from "lucide-react";
import { deleteFlexToken, getFlexTokenStatus, saveFlexToken } from "@/lib/api";

export function FlexTokenForm() {
  const [configured, setConfigured] = useState(false);
  const [token, setToken] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refreshStatus() {
    const result = await getFlexTokenStatus();
    setConfigured(result.configured);
  }

  useEffect(() => {
    refreshStatus().catch(() => {
      setConfigured(false);
    });
  }, []);

  async function save() {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      await saveFlexToken(token);
      setToken("");
      setConfigured(true);
      setStatus("Flex token saved to the OS keychain. The value is not displayed again.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not save Flex token");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      await deleteFlexToken();
      setConfigured(false);
      setToken("");
      setStatus("Flex token removed from the OS keychain.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not delete Flex token");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <KeyRound size={16} aria-hidden />
        IBKR Flex Query token
      </div>
      <p className="text-sm text-zinc-700">
        Stored only in the operating-system keychain. This form never redisplays a saved token.
      </p>
      <dl className="mt-3 grid gap-2 text-sm">
        <div className="flex justify-between">
          <dt>Status</dt>
          <dd>{configured ? "Configured" : "Not configured"}</dd>
        </div>
      </dl>
      <label className="mt-3 block text-sm">
        <span className="mb-1 block font-medium">New Flex token</span>
        <input
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={token}
          onChange={(event) => setToken(event.target.value)}
          className="w-full rounded-md border border-line bg-white px-3 py-2 font-mono text-sm"
          placeholder="Paste token, then save"
        />
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy || token.trim().length < 20}
          onClick={() => void save()}
          className="rounded-md bg-ink px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Working" : "Save to keychain"}
        </button>
        <button
          type="button"
          disabled={busy || !configured}
          onClick={() => void remove()}
          className="inline-flex items-center gap-1 rounded-md border border-line bg-white px-3 py-2 text-sm disabled:opacity-50"
        >
          <Trash2 size={14} aria-hidden />
          Remove
        </button>
      </div>
      {status ? <p className="mt-3 text-sm text-zinc-700">{status}</p> : null}
      {error ? <p className="mt-3 text-sm text-warning">{error}</p> : null}
    </div>
  );
}
