"use client";

import { useEffect, useState, type ReactNode } from "react";

import {
  desktopFetch,
  ensureDesktopRuntime,
  isDesktopRuntimeAvailable,
  markUiReadyPosted,
  shouldPostUiReady,
} from "@/lib/desktop-api";

const desktopLocal = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "desktop_local";

export function DesktopRuntimeGate({ children }: { children: ReactNode }) {
  // Must start false in the desktop build even when the runtime is already
  // injected: reading `window` during the first render disagrees with the
  // prerendered HTML, and React then discards and re-renders the whole tree
  // (hydration error #418) on every single page load. The effect below flips
  // it synchronously after mount, so a ready runtime still gates in one frame.
  const [ready, setReady] = useState(!desktopLocal);

  useEffect(() => {
    if (!desktopLocal) {
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    async function markReady() {
      ensureDesktopRuntime();
      if (!cancelled) {
        setReady(true);
      }
      // Only hit the API once per app session so nav stays fast.
      if (!shouldPostUiReady()) {
        return;
      }
      try {
        await desktopFetch("/desktop/status");
        await desktopFetch("/desktop/ui-ready", { method: "POST" });
        markUiReadyPosted();
      } catch {
        // Keep UI usable even if smoke marker POST fails.
      }
    }

    if (isDesktopRuntimeAvailable()) {
      void markReady();
      return () => {
        cancelled = true;
      };
    }

    timer = window.setInterval(() => {
      if (isDesktopRuntimeAvailable()) {
        window.clearInterval(timer);
        void markReady();
      }
    }, 50);

    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearInterval(timer);
      }
    };
  }, []);

  if (!ready) {
    return (
      <main className="mx-auto max-w-md px-6 py-16 text-sm text-zinc-600">
        Starting local API…
      </main>
    );
  }

  return <>{children}</>;
}
