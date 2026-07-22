"use client";

import { useEffect } from "react";

/**
 * Forwards frontend console output (and any uncaught error) into the packaged
 * app's Rust-side log file (apps/desktop/src-tauri/main.rs registers
 * tauri-plugin-log against `<data dir>/logs/webview.*.log`, next to the existing
 * sidecar.log). Runs only inside the Tauri shell; a no-op in a plain browser or
 * during the static export.
 *
 * This exists so a packaged-build issue (e.g. the webview never finishing initial
 * render) leaves a diagnosable trail instead of silently discarding whatever the
 * frontend tried to log or threw during startup.
 */
export function DesktopLogBridge() {
  useEffect(() => {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) return;
    let cancelled = false;

    (async () => {
      try {
        const { attachConsole, error: logError } = await import("@tauri-apps/plugin-log");
        if (cancelled) return;
        await attachConsole();

        const onError = (event: ErrorEvent) => {
          void logError(`window.onerror: ${event.message} @ ${event.filename}:${event.lineno}`);
        };
        const onRejection = (event: PromiseRejectionEvent) => {
          void logError(`unhandledrejection: ${String(event.reason)}`);
        };
        window.addEventListener("error", onError);
        window.addEventListener("unhandledrejection", onRejection);
        return () => {
          window.removeEventListener("error", onError);
          window.removeEventListener("unhandledrejection", onRejection);
        };
      } catch {
        // Logging bridge is best-effort; never block the app on it.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}
