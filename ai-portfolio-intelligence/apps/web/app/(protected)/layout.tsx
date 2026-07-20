"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { DesktopRuntimeGate } from "@/components/DesktopRuntimeGate";

const desktopLocal =
  process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "desktop_local" ||
  process.env.NEXT_PUBLIC_DISABLE_AUTH === "true";

function HostedAuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch("/api/backend/auth/me", { cache: "no-store" });
        if (cancelled) {
          return;
        }
        if (response.status === 401 || response.status === 403) {
          router.replace("/login");
          return;
        }
        if (!response.ok) {
          router.replace("/service-unavailable");
          return;
        }
        setReady(true);
      } catch {
        if (!cancelled) {
          router.replace("/service-unavailable");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (!ready) {
    return (
      <main className="mx-auto max-w-md px-6 py-16 text-sm text-zinc-600">
        Checking session…
      </main>
    );
  }
  return <>{children}</>;
}

export default function ProtectedLayout({ children }: Readonly<{ children: ReactNode }>) {
  if (desktopLocal) {
    return <DesktopRuntimeGate>{children}</DesktopRuntimeGate>;
  }
  return <HostedAuthGuard>{children}</HostedAuthGuard>;
}
