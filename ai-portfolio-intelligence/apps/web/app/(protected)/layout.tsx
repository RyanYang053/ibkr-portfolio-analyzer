import { type ReactNode } from "react";

import { DesktopRuntimeGate } from "@/components/DesktopRuntimeGate";

export default function ProtectedLayout({ children }: Readonly<{ children: ReactNode }>) {
  // The product ships desktop-only: the local runtime gate (loopback API +
  // per-launch session token) is the only access boundary. There is no login.
  return <DesktopRuntimeGate>{children}</DesktopRuntimeGate>;
}
