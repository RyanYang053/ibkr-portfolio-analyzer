import fs from "fs";
import type { NextConfig } from "next";
import path from "path";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "X-Frame-Options", value: "DENY" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "base-uri 'self'",
      "frame-ancestors 'none'",
      "object-src 'none'",
      "form-action 'self'",
      "img-src 'self' data: https:",
      "style-src 'self' 'unsafe-inline'",
      // Next.js App Router emits inline RSC flight <script> tags. Blocking them
      // with script-src 'self' alone leaves a blank document (Playwright E2E).
      "script-src 'self' 'unsafe-inline'",
      "connect-src 'self'",
    ].join("; "),
  },
];

/**
 * Docker builds this app in isolation (/app) → trace from __dirname so
 * standalone emits /app/server.js.
 *
 * npm workspaces hoist next to the monorepo root. Tracing only from apps/web
 * silently drops those files, so standalone lacks node_modules and runtime
 * resolves an incomplete apps/web/node_modules/next (missing ./cpu-profile).
 */
function resolveOutputFileTracingRoot(): string {
  const appRoot = __dirname;
  const workspaceRoot = path.join(appRoot, "../..");
  const workspacePackagePath = path.join(workspaceRoot, "package.json");
  try {
    if (!fs.existsSync(workspacePackagePath)) {
      return appRoot;
    }
    const pkg = JSON.parse(fs.readFileSync(workspacePackagePath, "utf8")) as {
      workspaces?: string[] | { packages?: string[] };
    };
    const workspaces = Array.isArray(pkg.workspaces)
      ? pkg.workspaces
      : (pkg.workspaces?.packages ?? []);
    if (workspaces.some((entry) => entry === "apps/web" || entry.endsWith("/web"))) {
      return workspaceRoot;
    }
  } catch {
    // Isolated install (Docker) or unreadable parent package.json.
  }
  return appRoot;
}

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: resolveOutputFileTracingRoot(),
  // Belt-and-suspenders: start-server.js requires ./cpu-profile which NFT
  // sometimes omits from standalone traces.
  outputFileTracingIncludes: {
    "/*": [
      "./node_modules/next/dist/server/lib/cpu-profile.js",
      "../../node_modules/next/dist/server/lib/cpu-profile.js",
    ],
  },
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
