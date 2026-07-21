import type { ReactNode } from "react";

// Desktop ships as a static export (output: "export"), which requires
// generateStaticParams on dynamic segments. Real plan ids are resolved
// client-side via the SPA 404.html fallback, so only a placeholder shell is
// prebuilt. In the hosted (standalone) build these routes stay on-demand.
const desktopBuild = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "desktop_local";

export function generateStaticParams() {
  return desktopBuild ? [{ planId: "_" }] : [];
}

export default function TradePlanLayout({ children }: { children: ReactNode }) {
  return children;
}
