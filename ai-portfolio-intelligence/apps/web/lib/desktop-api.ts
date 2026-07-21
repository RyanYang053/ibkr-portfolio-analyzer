type DesktopRuntime = {
  apiBaseUrl: string;
  sessionToken: string;
};

const RUNTIME_STORAGE_KEY = "__DESKTOP_RUNTIME__";
const UI_READY_STORAGE_KEY = "__DESKTOP_UI_READY_POSTED__";

declare global {
  interface Window {
    __DESKTOP_RUNTIME__?: DesktopRuntime;
  }
}

function readStoredRuntime(): DesktopRuntime | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = sessionStorage.getItem(RUNTIME_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as DesktopRuntime;
    if (
      parsed &&
      typeof parsed.apiBaseUrl === "string" &&
      typeof parsed.sessionToken === "string" &&
      parsed.apiBaseUrl.startsWith("http://127.0.0.1:")
    ) {
      return parsed;
    }
  } catch {
    // Ignore corrupt storage.
  }
  return null;
}

function persistRuntime(runtime: DesktopRuntime): void {
  try {
    sessionStorage.setItem(RUNTIME_STORAGE_KEY, JSON.stringify(runtime));
  } catch {
    // Private mode / quota — ignore.
  }
}

/** Ensure window runtime exists (Tauri injects it; sessionStorage covers full-page nav races). */
export function ensureDesktopRuntime(): DesktopRuntime | null {
  if (typeof window === "undefined") {
    return null;
  }
  if (window.__DESKTOP_RUNTIME__) {
    persistRuntime(window.__DESKTOP_RUNTIME__);
    return window.__DESKTOP_RUNTIME__;
  }
  const stored = readStoredRuntime();
  if (stored) {
    Object.defineProperty(window, "__DESKTOP_RUNTIME__", {
      value: stored,
      writable: false,
      configurable: true,
    });
    return stored;
  }
  return null;
}

export function isDesktopRuntimeAvailable(): boolean {
  return Boolean(ensureDesktopRuntime());
}

export function getDesktopRuntime(): DesktopRuntime {
  const runtime = ensureDesktopRuntime();
  if (!runtime) {
    throw new Error("Desktop runtime is unavailable");
  }
  return runtime;
}

export function shouldPostUiReady(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  try {
    return sessionStorage.getItem(UI_READY_STORAGE_KEY) !== "1";
  } catch {
    return true;
  }
}

export function markUiReadyPosted(): void {
  try {
    sessionStorage.setItem(UI_READY_STORAGE_KEY, "1");
  } catch {
    // ignore
  }
}

export async function desktopFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const runtime = getDesktopRuntime();

  const headers = new Headers(init.headers);
  headers.set("X-Local-Session", runtime.sessionToken);

  return fetch(`${runtime.apiBaseUrl}${path}`, {
    ...init,
    headers,
  });
}

/** Ask Tauri shell to show OS notifications for new desktop inbox rows. */
export async function pollDesktopOsNotifications(): Promise<{ shown: number; path: string } | null> {
  if (!isDesktopRuntimeAvailable()) {
    return null;
  }
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<{ shown: number; path: string }>("poll_desktop_notifications");
  } catch {
    return null;
  }
}

export function startDesktopNotificationPolling(intervalMs = 60_000): () => void {
  if (typeof window === "undefined" || !isDesktopRuntimeAvailable()) {
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
