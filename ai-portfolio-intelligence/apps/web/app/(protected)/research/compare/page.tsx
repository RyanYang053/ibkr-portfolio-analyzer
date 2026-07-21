"use client";

import { Suspense, useState } from "react";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { compareCandidates } from "@/lib/api";

function CompareContent() {
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function compare(e: React.FormEvent) {
    e.preventDefault();
    setNote(null);
    setResult(null);
    try {
      setResult(await compareCandidates(left.trim(), right.trim()));
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Compare failed");
    }
  }

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Compare</p>
        <h2 className="text-3xl font-semibold">Candidate comparison</h2>
        <p className="text-sm text-zinc-600">Compare two research candidates side by side. Data quality is surfaced, not hidden.</p>
        <Link className="text-sm text-accent hover:underline" href="/research">← Research</Link>
      </div>
      <Disclaimer />

      <form onSubmit={compare} className="flex flex-wrap gap-2">
        <input className="rounded-md border border-line px-3 py-2 text-sm" placeholder="Left candidate id" value={left} onChange={(e) => setLeft(e.target.value)} aria-label="Left candidate" />
        <input className="rounded-md border border-line px-3 py-2 text-sm" placeholder="Right candidate id" value={right} onChange={(e) => setRight(e.target.value)} aria-label="Right candidate" />
        <button type="submit" className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel">Compare</button>
      </form>
      {note ? <PageErrorBanner message={note} /> : null}

      {result ? (
        <pre className="overflow-x-auto rounded-md border border-line bg-panel p-3 text-xs">
          {JSON.stringify(result, null, 2)}
        </pre>
      ) : (
        <p className="text-sm text-zinc-600">
          Candidate ids come from the research queue and screener promotions.
        </p>
      )}
    </div>
  );
}

export default function ResearchComparePage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <CompareContent />
    </Suspense>
  );
}
