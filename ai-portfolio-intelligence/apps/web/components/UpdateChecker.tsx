"use client";

import { useEffect, useState } from "react";

/**
 * Silent auto-update check for the packaged desktop app.
 *
 * Runs only inside the Tauri shell (guarded by __TAURI_INTERNALS__), so it is a
 * no-op in a plain browser and during the static export. If the updater is not yet
 * configured (no signed release / placeholder pubkey) or the machine is offline, it
 * fails silently rather than surfacing an error. When an update is found it downloads
 * and installs it, then asks the user to restart.
 */
export function UpdateChecker() {
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return;
    let cancelled = false;

    (async () => {
      try {
        const { check } = await import("@tauri-apps/plugin-updater");
        const update = await check();
        if (!update || cancelled) return;
        setStatus(`Downloading update ${update.version}…`);
        await update.downloadAndInstall();
        if (!cancelled) setStatus(`Update ${update.version} installed — restart to apply.`);
      } catch {
        // Updater not configured, no release yet, or offline: stay quiet.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  if (!status) return null;

  return (
    <div className="fixed bottom-3 right-3 z-50 rounded-md border border-line bg-panel px-3 py-2 text-xs shadow-sm">
      {status}
    </div>
  );
}
