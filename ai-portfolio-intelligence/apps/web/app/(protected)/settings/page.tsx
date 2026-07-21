"use client";

import { Disclaimer } from "@/components/Disclaimer";
import { AIConfigForm } from "@/components/AIConfigForm";
import { FlexTokenForm } from "@/components/FlexTokenForm";
import { IBKRConfigForm } from "@/components/IBKRConfigForm";
import { ScheduleConfigForm } from "@/components/ScheduleConfigForm";
import { InvestorProfileForm } from "@/components/InvestorProfileForm";
import { TargetPolicyForm } from "@/components/TargetPolicyForm";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { getAIStatus, getBrokerStatus, getScheduleSettings } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";
import { useState } from "react";

const DESKTOP_MODE = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "desktop_local";

export default function SettingsPage() {
  const { data, error, loading } = useClientResource(
    () => Promise.all([getAIStatus(), getBrokerStatus(), getScheduleSettings()]),
    [],
  );

  if (loading) {
    return <PageLoading />;
  }

  const [aiStatus, brokerStatus, scheduleData] = data ?? [
    { provider: "unknown", model: "unknown", mode: "unknown" },
    { status: "unknown", mode: "unknown" },
    { settings: { enabled: false, morning_time: "09:30", midday_time: "12:30", night_time: "20:00" } },
  ];

  const scheduleSettings = scheduleData?.settings ?? {
    enabled: false,
    morning_time: "09:30",
    midday_time: "12:30",
    night_time: "20:00",
  };

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Configuration</p>
        <h2 className="text-3xl font-semibold">Settings</h2>
      </div>
      <Disclaimer />
      {error ? <PageErrorBanner message={error} /> : null}

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="flex flex-col gap-4">
          <InvestorProfileForm />
          <TargetPolicyForm />
        </div>

        <div className="flex flex-col gap-4">
          <div className="rounded-md border border-line bg-white p-4">
            <h3 className="text-lg font-semibold">Broker Connection</h3>
            <dl className="mt-3 grid gap-2 text-sm">
              <div className="flex justify-between"><dt>Status</dt><dd>{brokerStatus.status}</dd></div>
              <div className="flex justify-between"><dt>Mode</dt><dd>{brokerStatus.mode}</dd></div>
              <div className="flex justify-between"><dt>Socket</dt><dd>{brokerStatus.host ?? "127.0.0.1"}:{brokerStatus.port ?? "4002"}</dd></div>
              <div className="flex justify-between"><dt>Credential storage</dt><dd>No IBKR password storage</dd></div>
              <div className="flex justify-between"><dt>Order APIs</dt><dd>Not present</dd></div>
            </dl>
            {brokerStatus.error ? <p className="mt-3 rounded-md border border-warning bg-amber-50 p-2 text-sm text-warning">{brokerStatus.error}</p> : null}
            <IBKRConfigForm
              defaultMode={brokerStatus.mode}
              defaultHost={brokerStatus.host}
              defaultPort={brokerStatus.port}
              defaultClientId={brokerStatus.client_id}
              defaultAccountId={brokerStatus.account_id}
            />
            {DESKTOP_MODE ? <FlexTokenForm /> : null}
          </div>
          <div className="rounded-md border border-line bg-white p-4">
            <h3 className="text-lg font-semibold">AI Provider</h3>
            <dl className="mt-3 grid gap-2 text-sm">
              <div className="flex justify-between"><dt>Provider</dt><dd>{aiStatus.provider}</dd></div>
              <div className="flex justify-between"><dt>Model</dt><dd>{aiStatus.model}</dd></div>
              <div className="flex justify-between"><dt>Mode</dt><dd>{aiStatus.mode}</dd></div>
              <div className="flex justify-between">
                <dt>Scheduled Analysis</dt>
                <dd>{scheduleSettings.enabled ? "Active" : "Manual only"}</dd>
              </div>
            </dl>
            <div className="mt-4 rounded-md bg-panel p-3 text-sm">
              Set <code className="font-mono">GEMINI_API_KEY</code> on the backend process, then restart the API.
              Do not put the key in browser code.
            </div>
            <AIConfigForm defaultModel={aiStatus.model} />
            <ScheduleConfigForm initialSettings={scheduleSettings} />
          </div>
        </div>
      </section>

      <section className="rounded-md border border-line bg-white p-4">
        <h3 className="text-lg font-semibold">Desktop backup</h3>
        <p className="mt-2 text-sm text-zinc-700">
          Create a local zip backup of personal state. Optional passphrase writes an encrypted PAEB1
          envelope. Flex tokens stay in the OS keychain and are not included.
        </p>
        <DesktopBackupPanel />
      </section>

      <section className="rounded-md border border-line bg-white p-4">
        <h3 className="text-lg font-semibold">No-Trading Policy Acknowledgement</h3>
        <p className="mt-2 text-sm text-zinc-700">
          This product is a read-only portfolio analyst. It does not place, modify, cancel, route,
          schedule, or automate broker orders.
        </p>
      </section>
    </div>
  );
}

function DesktopBackupPanel() {
  const [passphrase, setPassphrase] = useState("");
  const [encryptedPath, setEncryptedPath] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function runBackup() {
    setBusy(true);
    setMessage(null);
    try {
      const { createDesktopBackup, exportDesktopArchive } = await import("@/lib/api");
      if (passphrase.trim()) {
        const result = await createDesktopBackup(passphrase.trim());
        const encrypted = String(result.encrypted_path || "");
        if (encrypted) setEncryptedPath(encrypted);
        setMessage(
          `Backup written: ${String(result.backup_path || "")}` +
            (encrypted ? ` · encrypted: ${encrypted}` : ""),
        );
      } else {
        const result = await createDesktopBackup();
        setMessage(`Backup written: ${String(result.backup_path || "")}`);
      }
      await exportDesktopArchive().catch(() => null);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Backup failed");
    } finally {
      setBusy(false);
    }
  }

  async function runVerify() {
    setBusy(true);
    setMessage(null);
    try {
      const { verifyDesktopBackupRestore } = await import("@/lib/api");
      if (!encryptedPath.trim() || !passphrase.trim()) {
        setMessage("Encrypted path and passphrase are required to verify restore.");
        return;
      }
      const result = await verifyDesktopBackupRestore(encryptedPath.trim(), passphrase.trim());
      setMessage(
        result.ok
          ? `Verify-restore succeeded (${String(result.bytes || 0)} bytes). Live data was not overwritten.`
          : "Verify-restore did not succeed.",
      );
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Verify-restore failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 grid gap-2 text-sm">
      <label className="grid gap-1">
        <span className="text-zinc-600">Optional encryption passphrase</span>
        <input
          type="password"
          className="rounded-md border border-line px-3 py-2"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          placeholder="Leave blank for zip-only backup"
          autoComplete="new-password"
        />
      </label>
      <label className="grid gap-1">
        <span className="text-zinc-600">Encrypted backup path (for verify-restore)</span>
        <input
          type="text"
          className="rounded-md border border-line px-3 py-2 font-mono text-xs"
          value={encryptedPath}
          onChange={(e) => setEncryptedPath(e.target.value)}
          placeholder="/path/to/portfolio-backup-….zip.paeb1"
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="w-fit rounded-md border border-line px-3 py-2 hover:bg-panel disabled:opacity-50"
          onClick={runBackup}
          disabled={busy}
        >
          {busy ? "Working…" : "Create backup"}
        </button>
        <button
          type="button"
          className="w-fit rounded-md border border-line px-3 py-2 hover:bg-panel disabled:opacity-50"
          onClick={runVerify}
          disabled={busy}
        >
          Verify restore (no overwrite)
        </button>
      </div>
      {message ? <p className="text-zinc-600">{message}</p> : null}
    </div>
  );
}
