import { Disclaimer } from "@/components/Disclaimer";
import { getWatchlist } from "@/lib/api";
import { WatchlistContainer } from "@/components/WatchlistContainer";

export const dynamic = "force-dynamic";

export default async function WatchlistPage() {
  const items = await getWatchlist() as any[];

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Monitoring list</p>
        <h2 className="text-3xl font-semibold">Watchlist</h2>
      </div>
      <Disclaimer />
      <WatchlistContainer initialItems={items} />
    </div>
  );
}

