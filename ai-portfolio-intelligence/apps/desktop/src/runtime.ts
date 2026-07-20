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
