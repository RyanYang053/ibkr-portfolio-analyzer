type DesktopRuntime = {
  apiBaseUrl: string;
  sessionToken: string;
};

declare global {
  interface Window {
    __DESKTOP_RUNTIME__?: DesktopRuntime;
  }
}

export function isDesktopRuntimeAvailable(): boolean {
  return typeof window !== "undefined" && Boolean(window.__DESKTOP_RUNTIME__);
}

export function getDesktopRuntime(): DesktopRuntime {
  const runtime = window.__DESKTOP_RUNTIME__;

  if (!runtime) {
    throw new Error("Desktop runtime is unavailable");
  }

  return runtime;
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
