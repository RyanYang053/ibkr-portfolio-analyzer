import type { Metadata, Viewport } from "next";

import { Nav } from "@/components/Nav";
import { CommandPalette } from "@/components/CommandPalette";
import { FloatingChatbot } from "@/components/FloatingChatbot";
import { UpdateChecker } from "@/components/UpdateChecker";
import { DesktopLogBridge } from "@/components/DesktopLogBridge";
import { RoutePrewarm } from "@/components/RoutePrewarm";
import { THEME_BOOTSTRAP_SCRIPT } from "@/components/ThemeToggle";
import "./globals.css";

export const metadata: Metadata = {
  title: "Portfolio Intelligence",
  description: "Read-only portfolio research and decision-support system",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbfcfa" },
    { media: "(prefers-color-scheme: dark)", color: "#0d1117" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Applies the stored theme before first paint, so a dark-mode user
            never sees a flash of the light palette. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
      </head>
      <body>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:shadow-lg"
        >
          Skip to content
        </a>

        <div className="grid min-h-screen lg:grid-cols-[236px_minmax(0,1fr)]">
          <Nav />
          <main id="main-content" className="min-w-0 px-4 py-5 lg:px-7 lg:py-6">
            {children}
            <FloatingChatbot />
          </main>
        </div>

        <CommandPalette />
        <RoutePrewarm />
        <DesktopLogBridge />
        <UpdateChecker />
      </body>
    </html>
  );
}
