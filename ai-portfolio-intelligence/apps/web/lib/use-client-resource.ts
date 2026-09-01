"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { formatApiError } from "./api";
import { readResourceSnapshot, writeResourceSnapshot } from "./resource-snapshot";

export type ClientResource<T> = {
  data: T | null;
  error: string | null;
  /** True only when there is nothing at all to render yet. */
  loading: boolean;
  /** True while a background revalidation runs behind already-visible data. */
  refreshing: boolean;
  /** The visible data came from cache and is being revalidated. */
  stale: boolean;
  /** Re-run the loader immediately, keeping current data on screen. */
  reload: () => void;
};

/**
 * Load a page's data with stale-while-revalidate semantics.
 *
 * The last resolved value is snapshotted to sessionStorage and replayed on the
 * next visit, so a page paints real numbers on its first frame and revalidates
 * behind them instead of showing a blank "Loading…" screen every time. This
 * matters most in the desktop shell, where navigation replaces the document and
 * would otherwise discard every in-memory cache.
 *
 * Pass `seed` to override where the initial value comes from, or
 * `snapshot: false` for resources too large or too sensitive to persist.
 */
export function useClientResource<T>(
  loader: () => Promise<T>,
  deps: readonly unknown[],
  options: {
    seed?: () => T | undefined;
    refreshIntervalMs?: number;
    /** Persist the resolved value for instant repaint on the next visit. */
    snapshot?: boolean;
  } = {},
): ClientResource<T> {
  const { refreshIntervalMs, snapshot = true } = options;
  const seedRef = useRef(options.seed);
  seedRef.current = options.seed;

  // `useId` is stable for a given position in the component tree, so the same
  // hook on the same page resolves to the same snapshot slot across visits.
  const callSiteId = useId();

  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const depsKey = JSON.stringify(deps);
  const prevDepsKey = useRef<string | null>(null);
  const snapshotKey = snapshot ? `${callSiteId}|${depsKey}` : null;

  const [state, setState] = useState<{ data: T | null; error: string | null; stale: boolean }>({
    data: null,
    error: null,
    stale: false,
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  const hasDataRef = useRef(false);
  const cancelRef = useRef<(() => void) | null>(null);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  useEffect(() => {
    let cancelled = false;
    cancelRef.current = () => {
      cancelled = true;
    };

    const scopeChanged = prevDepsKey.current !== null && prevDepsKey.current !== depsKey;
    prevDepsKey.current = depsKey;

    // A different account/symbol means the visible numbers belong to something
    // else. Clear them rather than showing one scope's data under another's
    // heading — but seed from cache first if this scope was visited before.
    const seeded =
      seedRef.current?.() ??
      (snapshotKey ? readResourceSnapshot<T>(snapshotKey) : undefined);
    if (scopeChanged) {
      hasDataRef.current = seeded !== undefined;
      setState({ data: seeded ?? null, error: null, stale: seeded !== undefined });
    } else if (!hasDataRef.current && seeded !== undefined) {
      hasDataRef.current = true;
      setState({ data: seeded, error: null, stale: true });
    }

    setLoading(!hasDataRef.current);
    setRefreshing(hasDataRef.current);

    loaderRef
      .current()
      .then((value) => {
        if (cancelled) return;
        hasDataRef.current = true;
        setState({ data: value, error: null, stale: false });
        if (snapshotKey) {
          writeResourceSnapshot(snapshotKey, value);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setState((current) => ({
          // Keep the last good numbers on screen behind the error banner; a
          // failed refresh should not wipe a working page.
          data: hasDataRef.current ? current.data : null,
          error: formatApiError(err),
          stale: current.stale,
        }));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
        setRefreshing(false);
      });

    return () => {
      cancelled = true;
    };
    // `loader` is held in a ref so an inline arrow does not restart the fetch.
  }, [depsKey, reloadToken, snapshotKey]);

  // Optional polling for live panels (broker status, monitoring inbox).
  useEffect(() => {
    if (!refreshIntervalMs || refreshIntervalMs <= 0) {
      return;
    }
    const id = window.setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) {
        return; // Do not poll a window the user cannot see.
      }
      reload();
    }, refreshIntervalMs);
    return () => window.clearInterval(id);
  }, [refreshIntervalMs, reload]);

  useEffect(() => () => cancelRef.current?.(), []);

  return { ...state, loading, refreshing, reload };
}
