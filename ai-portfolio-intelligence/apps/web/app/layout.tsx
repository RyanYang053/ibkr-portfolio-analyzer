import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { FloatingChatbot } from "@/components/FloatingChatbot";
import { UpdateChecker } from "@/components/UpdateChecker";
import { DesktopLogBridge } from "@/components/DesktopLogBridge";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Portfolio Intelligence",
  description: "Read-only portfolio research and decision-support system"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="grid min-h-screen lg:grid-cols-[260px_1fr]">
          <Nav />
          <main className="px-4 py-5 lg:px-8">
            {children}
            <FloatingChatbot />
          </main>
        </div>
        <DesktopLogBridge />
        <UpdateChecker />
      </body>
    </html>
  );
}
