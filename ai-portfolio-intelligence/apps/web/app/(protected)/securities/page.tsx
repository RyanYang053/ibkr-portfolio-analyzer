"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Disclaimer } from "@/components/Disclaimer";
import { PageLoading } from "@/components/PageLoadState";
import { searchInstruments } from "@/lib/api";
import { useAppRouter } from "@/lib/use-app-router";
import { useClientResource } from "@/lib/use-client-resource";

type Instrument = Record<string, unknown>;

function SecuritiesIndex() {
  const router = useAppRouter();
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || undefined;
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");

  const { data, loading } = useClientResource(
    () => (submitted ? searchInstruments(submitted, accountId) : Promise.resolve(null)),
    [submitted, accountId],
  );
  const results = (data?.instruments as Instrument[] | undefined) ?? [];

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Securities</p>
        <h2 className="text-3xl font-semibold">Find any security</h2>
        <p className="text-sm text-zinc-600">
          The universal workspace works for owned holdings, watchlist names, benchmarks, ETFs, and
          securities with no position.
        </p>
      </div>
      <Disclaimer />

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setSubmitted(q.trim());
        }}
      >
        <input
          className="w-full max-w-md rounded-md border border-line px-3 py-2 text-sm"
          placeholder="Search ticker or company (e.g. MSFT, Microsoft)"
          value={q}
          onChange={(event) => setQ(event.target.value)}
          aria-label="Security search"
        />
        <button className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel" type="submit">
          Search
        </button>
        <button
          type="button"
          className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel"
          onClick={() => {
            const value = q.trim().toUpperCase();
            if (value) router.push(`/securities/${encodeURIComponent(value)}`);
          }}
        >
          Open exact
        </button>
      </form>

      {loading ? <p className="text-sm text-zinc-600">Searching…</p> : null}
      {submitted && !loading && results.length === 0 ? (
        <p className="text-sm text-zinc-600">
          No local instruments match “{submitted}”. Held securities appear after their account loads;
          use “Open exact” to open any ticker directly.
        </p>
      ) : null}

      {results.length > 0 ? (
        <div className="grid gap-2">
          {results.map((row) => (
            <button
              key={String(row.instrument_id)}
              type="button"
              className="rounded-md border border-line p-3 text-left hover:bg-panel"
              onClick={() =>
                router.push(`/securities/${encodeURIComponent(String(row.instrument_id))}`)
              }
            >
              <div className="flex justify-between text-sm">
                <span className="font-semibold">{String(row.symbol)}</span>
                <span className="text-zinc-500">{String(row.asset_class ?? "")}</span>
              </div>
              <p className="text-xs text-zinc-600">
                {String(row.name ?? "")} {row.provisional ? "· provisional" : ""}
              </p>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function SecuritiesPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <SecuritiesIndex />
    </Suspense>
  );
}
