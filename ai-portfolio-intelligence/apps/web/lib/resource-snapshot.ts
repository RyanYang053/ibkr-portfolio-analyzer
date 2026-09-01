"use client";

/**
 * Per-page snapshots of the last successfully loaded data.
 *
 * The desktop shell navigates by replacing the document, so every in-memory
 * React state and module cache is destroyed on each tab switch. Persisting the
 * resolved value for each `useClientResource` call site lets the next visit
 * paint the previous numbers immediately and revalidate behind them, instead of
 * dropping to a blank screen for as long as the requests take.
 *
 * Snapshots are scoped per pathname and per call site, live in sessionStorage
 * (so they are gone when the app closes), and are always treated as stale: they
 * are a starting picture, never a substitute for a fresh response.
 */

const PREFIX = "pai.snap.v1:";
const MAX_AGE_MS = 30 * 60_000;
/** Roughly 250KB of JSON — beyond this the write cost outweighs the repaint win. */
const MAX_BYTES = 250_000;

type Snapshot = { storedAt: number; data: unknown };

function storage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function fullKey(key: string): string {
  const path = typeof window === "undefined" ? "" : window.location.pathname;
  return `${PREFIX}${path}|${key}`;
}

export function readResourceSnapshot<T>(key: string): T | undefined {
  const store = storage();
  if (!store) {
    return undefined;
  }
  try {
    const raw = store.getItem(fullKey(key));
    if (!raw) {
      return undefined;
    }
    const parsed = JSON.parse(raw) as Snapshot;
    if (typeof parsed?.storedAt !== "number") {
      return undefined;
    }
    if (Date.now() - parsed.storedAt > MAX_AGE_MS) {
      store.removeItem(fullKey(key));
      return undefined;
    }
    return parsed.data as T;
  } catch {
    return undefined;
  }
}

export function writeResourceSnapshot(key: string, data: unknown): void {
  const store = storage();
  if (!store || data === undefined) {
    return;
  }
  try {
    const serialized = JSON.stringify({ storedAt: Date.now(), data } satisfies Snapshot);
    if (serialized.length > MAX_BYTES) {
      return;
    }
    store.setItem(fullKey(key), serialized);
  } catch {
    clearResourceSnapshots();
  }
}

/** Drop every snapshot — used when the account scope changes. */
export function clearResourceSnapshots(): void {
  const store = storage();
  if (!store) {
    return;
  }
  try {
    for (const key of Object.keys(store)) {
      if (key.startsWith(PREFIX)) {
        store.removeItem(key);
      }
    }
  } catch {
    // ignore
  }
}
