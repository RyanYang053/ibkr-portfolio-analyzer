"use client";

import { useEffect } from "react";

import { desktopReplace, isDesktopLocal } from "@/lib/desktop-navigation";

import LoginForm from "./LoginForm";

export default function Page() {
  useEffect(() => {
    if (isDesktopLocal) {
      desktopReplace("/");
    }
  }, []);

  if (isDesktopLocal) {
    return (
      <main className="mx-auto max-w-md px-6 py-16 text-sm text-zinc-600">
        Opening Portfolio Analyzer. No sign-in is required on desktop.
      </main>
    );
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center">
      <div className="rounded-lg border border-line bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold">Sign in</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Development mode only. The desktop product does not use an application login.
        </p>
        <LoginForm />
      </div>
    </div>
  );
}
