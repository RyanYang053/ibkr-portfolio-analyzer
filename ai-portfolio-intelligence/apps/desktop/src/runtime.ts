/**
 * Desktop shell runtime helpers (TypeScript side).
 * The native Tauri process injects window.__DESKTOP_RUNTIME__ before loading UI.
 */

export type DesktopRuntime = {
  apiBaseUrl: string;
  sessionToken: string;
};

export function readInjectedRuntime(): DesktopRuntime | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.__DESKTOP_RUNTIME__ ?? null;
}

/** Ask the Tauri shell to show OS notifications for new desktop inbox rows. */
export async function pollDesktopOsNotifications(): Promise<{ shown: number; path: string } | null> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<{ shown: number; path: string }>("poll_desktop_notifications");
  } catch {
    return null;
  }
}

/** Start a light poll loop while the desktop webview is open. */
export function startDesktopNotificationPolling(intervalMs = 60_000): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }
  let cancelled = false;
  const tick = async () => {
    if (cancelled) return;
    await pollDesktopOsNotifications();
  };
  void tick();
  const id = window.setInterval(() => {
    void tick();
  }, intervalMs);
  return () => {
    cancelled = true;
    window.clearInterval(id);
  };
}
