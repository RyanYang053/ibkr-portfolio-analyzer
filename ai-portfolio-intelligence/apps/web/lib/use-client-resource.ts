"use client";

import { useEffect, useRef, useState } from "react";

import { formatApiError } from "./api";

export function useClientResource<T>(
  loader: () => Promise<T>,
  deps: readonly unknown[],
): { data: T | null; error: string | null; loading: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const hasDataRef = useRef(false);
  const depsKey = JSON.stringify(deps);
  const prevDepsKey = useRef(depsKey);

  useEffect(() => {
    let cancelled = false;
    const scopeChanged = prevDepsKey.current !== depsKey;
    prevDepsKey.current = depsKey;

    if (scopeChanged) {
      hasDataRef.current = false;
      setData(null);
      setError(null);
    }

    // Keep previous content visible while revalidating the same scope.
    if (!hasDataRef.current) {
      setLoading(true);
    }

    loader()
      .then((value) => {
        if (!cancelled) {
          hasDataRef.current = true;
          setData(value);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(formatApiError(err));
          if (!hasDataRef.current) {
            setData(null);
          }
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [depsKey]);

  return { data, error, loading };
}
