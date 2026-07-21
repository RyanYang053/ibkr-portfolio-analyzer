"use client";

import { useRouter } from "next/navigation";

import {
  desktopNavigate,
  desktopReplace,
  isDesktopLocal,
} from "@/lib/desktop-navigation";

/**
 * Router wrapper that forces full HTML navigations in the Tauri desktop shell.
 * Soft App Router transitions fetch RSC `.txt` payloads, which Tauri serves as
 * the document body (raw flight text instead of the page).
 */
export function useAppRouter() {
  const router = useRouter();

  return {
    push(href: string) {
      if (isDesktopLocal) {
        desktopNavigate(href);
        return;
      }
      void router.push(href);
    },
    replace(href: string) {
      if (isDesktopLocal) {
        desktopReplace(href);
        return;
      }
      void router.replace(href);
    },
    refresh() {
      if (isDesktopLocal) {
        window.location.reload();
        return;
      }
      router.refresh();
    },
  };
}
