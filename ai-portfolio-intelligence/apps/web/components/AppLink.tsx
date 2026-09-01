"use client";

import NextLink from "next/link";
import { useEffect, useState, type ComponentProps, type MouseEvent, type ReactNode } from "react";

import { prefetchJson } from "@/lib/api";
import { desktopHref, isDesktopLocal, readCurrentAccountId, withCurrentAccountId } from "@/lib/desktop-navigation";
import { NAV_ITEMS } from "@/lib/navigation";

type AppLinkProps = {
  href: string;
  children: ReactNode;
  className?: string;
  prefetch?: ComponentProps<typeof NextLink>["prefetch"];
} & Omit<ComponentProps<"a">, "href">;

/** HTML documents already warmed this session, so hover does not refetch them. */
const warmedDocuments = new Set<string>();

function prefetchDesktopDocument(url: string): void {
  if (typeof window === "undefined" || warmedDocuments.has(url)) {
    return;
  }
  warmedDocuments.add(url);
  const absolute = new URL(url, window.location.href).pathname;
  // Warm the static HTML + chunk cache without navigating.
  void fetch(absolute, { credentials: "same-origin", cache: "force-cache" }).catch(() => {});
}

/**
 * Warm the API responses the destination renders first.
 *
 * Navigation in the desktop shell replaces the document, so the target page
 * starts with no in-memory state. Fetching its primary endpoints while the
 * pointer is still on the link means the new page finds them already cached.
 */
export function prefetchRouteData(href: string, options: { intent?: boolean } = {}): void {
  if (typeof window === "undefined") {
    return;
  }
  const path = href.split("?")[0].replace(/\/+$/, "") || "/";
  const item = NAV_ITEMS.find((entry) => entry.href === path);
  if (!item) {
    return;
  }
  const templates = [
    ...(item.prefetch ?? []),
    // Only pull the expensive endpoints once the pointer says the user is
    // actually heading there.
    ...(options.intent ? (item.prefetchOnIntent ?? []) : []),
  ];
  const accountId = readCurrentAccountId();
  for (const template of templates) {
    const resolved = template.replace(
      "{account}",
      accountId ? `${template.includes("?") ? "&" : "?"}account_id=${encodeURIComponent(accountId)}` : "",
    );
    prefetchJson(resolved);
  }
}

/**
 * Next `<Link>` soft-nav fetches RSC `index.txt` files. Tauri's asset protocol
 * serves those as the document body, so Settings etc. show raw flight data.
 * Desktop builds force a full HTML navigation instead, with hover prefetch of
 * both the document and the data the destination needs.
 */
export function AppLink({ href, children, className, prefetch, onMouseEnter, onFocus, ...rest }: AppLinkProps) {
  // The account query string comes from `window.location`, which does not exist
  // when the page is prerendered. Appending it during the first client render
  // would disagree with the server HTML, so it is added after mount instead.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const scopedHref = mounted ? withCurrentAccountId(href) : href;

  function warm() {
    if (isDesktopLocal) {
      prefetchDesktopDocument(desktopHref(withCurrentAccountId(href)));
    }
    prefetchRouteData(href, { intent: true });
  }

  if (isDesktopLocal) {
    return (
      <a
        href={desktopHref(scopedHref)}
        className={className}
        onMouseEnter={(event: MouseEvent<HTMLAnchorElement>) => {
          warm();
          onMouseEnter?.(event);
        }}
        onFocus={(event) => {
          warm();
          onFocus?.(event);
        }}
        {...rest}
      >
        {children}
      </a>
    );
  }

  return (
    <NextLink
      href={scopedHref}
      className={className}
      prefetch={prefetch}
      onMouseEnter={(event) => {
        warm();
        onMouseEnter?.(event);
      }}
      onFocus={(event) => {
        warm();
        onFocus?.(event);
      }}
      {...rest}
    >
      {children}
    </NextLink>
  );
}
