"use client";

import { useEffect } from "react";

import { prefetchRouteData } from "@/components/AppLink";
import { NAV_ITEMS } from "@/lib/navigation";

/** Destinations worth warming unprompted — the ones reached from anywhere. */
const HOT_ROUTES = ["/", "/portfolio", "/risk", "/decisions"];

/**
 * Warms the busiest pages once the current one is idle.
 *
 * The desktop shell reloads the document on every navigation, so a page that
 * has not been visited this session starts with an empty cache and shows
 * skeletons while its requests run. Warming during idle time — never during
 * the current page's own load — means the first jump is already paid for.
 */
export function RoutePrewarm() {
  useEffect(() => {
    const current = window.location.pathname.replace(/\/+$/, "") || "/";
    const targets = HOT_ROUTES.filter((route) => route !== current);
    if (targets.length === 0) {
      return;
    }

    let cancelled = false;
    const timers: number[] = [];

    const start = () => {
      targets.forEach((route, index) => {
        // Stagger so several loopback requests do not contend with each other
        // or with anything the user triggers next.
        timers.push(
          window.setTimeout(() => {
            if (!cancelled) prefetchRouteData(route);
          }, index * 400),
        );
      });
    };

    // requestIdleCallback is unavailable on older Safari/WebKit webviews.
    const supportsIdle = typeof window.requestIdleCallback === "function";
    const handle = supportsIdle
      ? window.requestIdleCallback(start, { timeout: 4000 })
      : window.setTimeout(start, 1500);

    return () => {
      cancelled = true;
      timers.forEach((timer) => window.clearTimeout(timer));
      if (supportsIdle) {
        window.cancelIdleCallback(handle);
      } else {
        window.clearTimeout(handle);
      }
    };
  }, []);

  return null;
}
