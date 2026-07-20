"use client";

import { useEffect, useState, type ReactNode } from "react";

import { isDesktopRuntimeAvailable } from "@/lib/desktop-api";

const desktopLocal = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "desktop_local";

export function DesktopRuntimeGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(!desktopLocal);

  useEffect(() => {
    if (!desktopLocal) {
      return;
    }
    if (isDesktopRuntimeAvailable()) {
      setReady(true);
      return;
    }
    const timer = window.setInterval(() => {
      if (isDesktopRuntimeAvailable()) {
        setReady(true);
        window.clearInterval(timer);
      }
    }, 50);
    return () => window.clearInterval(timer);
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
