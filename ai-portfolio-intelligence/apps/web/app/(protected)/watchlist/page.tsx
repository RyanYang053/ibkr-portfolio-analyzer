"use client";

import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { WatchlistContainer } from "@/components/WatchlistContainer";
import { PageHeader } from "@/components/ui/PageHeader";
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
      <PageHeader
        eyebrow="Monitoring list"
        title="Watchlist"
      />
      <Disclaimer />
      {error ? <PageErrorBanner message={error} /> : null}
      <WatchlistContainer initialItems={items ?? []} />
    </div>
  );
}
