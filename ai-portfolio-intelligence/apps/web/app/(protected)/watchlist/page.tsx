"use client";

import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { WatchlistContainer } from "@/components/WatchlistContainer";
import { getWatchlist } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

export default function WatchlistPage() {
  const { data: items, error, loading } = useClientResource(
    () => getWatchlist() as Promise<any[]>,
    [],
  );

  if (loading) {
    return <PageLoading />;
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Monitoring list</p>
        <h2 className="text-3xl font-semibold">Watchlist</h2>
      </div>
      <Disclaimer />
      {error ? <PageErrorBanner message={error} /> : null}
      <WatchlistContainer initialItems={items ?? []} />
    </div>
  );
}
