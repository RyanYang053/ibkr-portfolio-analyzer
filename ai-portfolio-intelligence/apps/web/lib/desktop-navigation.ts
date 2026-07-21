/** Desktop static export + Tauri cannot soft-navigate via Next RSC `.txt` payloads. */

export const isDesktopLocal =
  process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "desktop_local";

/**
 * Normalize App Router hrefs for trailingSlash static export.
 * `/settings` -> `/settings/`, `/holdings/detail?symbol=AAPL` -> `/holdings/detail/?symbol=AAPL`
 * Query/hash-only hrefs (`?tab=options`) are left relative.
 */
export function desktopHref(href: string): string {
  if (!href.startsWith("/")) {
    return href;
  }
  const hashIndex = href.indexOf("#");
  const hash = hashIndex >= 0 ? href.slice(hashIndex) : "";
  const withoutHash = hashIndex >= 0 ? href.slice(0, hashIndex) : href;
  const queryIndex = withoutHash.indexOf("?");
  const path = queryIndex >= 0 ? withoutHash.slice(0, queryIndex) : withoutHash;
  const query = queryIndex >= 0 ? withoutHash.slice(queryIndex) : "";
  if (path === "/") {
    return `/${query}${hash}`;
  }
  const withSlash = path.endsWith("/") ? path : `${path}/`;
  return `${withSlash}${query}${hash}`;
}

/** Read the active account from the current URL (browser only). */
export function readCurrentAccountId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return new URLSearchParams(window.location.search).get("account_id");
}

/**
 * Carry `account_id` across in-app navigations so Consolidated View stays selected.
 * Does not override an explicit account_id already present on the target href.
 */
export function withCurrentAccountId(href: string): string {
  if (!href.startsWith("/") || href.startsWith("//")) {
    return href;
  }
  const accountId = readCurrentAccountId();
  if (!accountId) {
    return href;
  }

  const hashIndex = href.indexOf("#");
  const hash = hashIndex >= 0 ? href.slice(hashIndex) : "";
  const withoutHash = hashIndex >= 0 ? href.slice(0, hashIndex) : href;
  const queryIndex = withoutHash.indexOf("?");
  const path = queryIndex >= 0 ? withoutHash.slice(0, queryIndex) : withoutHash;
  const params = new URLSearchParams(queryIndex >= 0 ? withoutHash.slice(queryIndex + 1) : "");
  if (!params.has("account_id")) {
    params.set("account_id", accountId);
  }
  const query = params.toString();
  return `${path}${query ? `?${query}` : ""}${hash}`;
}

export function desktopNavigate(href: string): void {
  if (typeof window === "undefined") {
    return;
  }
  window.location.assign(desktopHref(withCurrentAccountId(href)));
}

export function desktopReplace(href: string): void {
  if (typeof window === "undefined") {
    return;
  }
  window.location.replace(desktopHref(withCurrentAccountId(href)));
}
