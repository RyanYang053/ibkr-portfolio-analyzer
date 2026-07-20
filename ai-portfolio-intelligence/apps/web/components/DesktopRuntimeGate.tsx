"use client";

import { useEffect, useState, type ReactNode } from "react";

import { desktopFetch, isDesktopRuntimeAvailable } from "@/lib/desktop-api";

const desktopLocal = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "desktop_local";

export function DesktopRuntimeGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(!desktopLocal);

  useEffect(() => {
    if (!desktopLocal) {
      return;
    }

    let cancelled = false;
    let timer: number | undefined;

    async function markReady() {
      try {
        await desktopFetch("/desktop/status");
        await desktopFetch("/desktop/ui-ready", { method: "POST" });
      } catch {
        // Smoke waits for the marker; keep retrying briefly.
      }
      if (!cancelled) {
        setReady(true);
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
