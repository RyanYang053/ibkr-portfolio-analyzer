"use client";

import NextLink from "next/link";
import type { ComponentProps, MouseEvent, ReactNode } from "react";

import { desktopHref, isDesktopLocal, withCurrentAccountId } from "@/lib/desktop-navigation";

type AppLinkProps = {
  href: string;
  children: ReactNode;
  className?: string;
  prefetch?: ComponentProps<typeof NextLink>["prefetch"];
} & Omit<ComponentProps<"a">, "href">;

function resolveHref(href: string): string {
  return desktopHref(withCurrentAccountId(href));
}

function prefetchDesktopPage(href: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const url = resolveHref(href);
  const absolute = new URL(url, window.location.href).pathname;
  // Warm the static HTML + chunk cache without navigating.
  void fetch(absolute, { credentials: "same-origin", cache: "force-cache" }).catch(() => {});
}

/**
 * Next `<Link>` soft-nav fetches RSC `index.txt` files. Tauri's asset protocol
 * serves those as the document body, so Settings etc. show raw flight data.
 * Desktop builds force a full HTML navigation instead, with hover prefetch.
 */
export function AppLink({ href, children, className, prefetch, onMouseEnter, onFocus, ...rest }: AppLinkProps) {
  if (isDesktopLocal) {
    const url = resolveHref(href);
    return (
      <a
        href={url}
        className={className}
        onMouseEnter={(event: MouseEvent<HTMLAnchorElement>) => {
          prefetchDesktopPage(href);
          onMouseEnter?.(event);
        }}
        onFocus={(event) => {
          prefetchDesktopPage(href);
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
      href={withCurrentAccountId(href)}
      className={className}
      prefetch={prefetch}
      onMouseEnter={onMouseEnter}
      onFocus={onFocus}
      {...rest}
    >
      {children}
    </NextLink>
  );
}
