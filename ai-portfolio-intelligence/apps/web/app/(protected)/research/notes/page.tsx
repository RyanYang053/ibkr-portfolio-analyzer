"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AppLink as Link } from "@/components/AppLink";
import { Disclaimer } from "@/components/Disclaimer";
import { PageErrorBanner, PageLoading } from "@/components/PageLoadState";
import { createResearchNote, listResearchNotes } from "@/lib/api";
import { useClientResource } from "@/lib/use-client-resource";

type Note = Record<string, unknown>;

const NOTE_TYPES = ["security", "earnings", "management", "industry", "macro", "meeting", "thesis"] as const;

function NotesContent() {
  const searchParams = useSearchParams();
  const accountId = searchParams.get("account_id") || "MOCK-001";
  const [reloadKey, setReloadKey] = useState(0);
  const [instrument, setInstrument] = useState("");
  const [type, setType] = useState<string>("security");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tags, setTags] = useState("");
  const [note, setNote] = useState<string | null>(null);

  const { data, error, loading } = useClientResource(() => listResearchNotes(accountId), [accountId, reloadKey]);
  const notes = (data?.notes as Note[] | undefined) ?? [];

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() && !body.trim()) return;
    setNote(null);
    try {
      await createResearchNote({
        account_id: accountId,
        instrument_id: instrument.trim().toUpperCase() || null,
        symbol: instrument.trim().toUpperCase().split(":")[0] || null,
        note_type: type,
        title,
        body,
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
      });
      setTitle("");
      setBody("");
      setTags("");
      setReloadKey((k) => k + 1);
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Failed to save note");
    }
  }

  if (loading) return <PageLoading />;
  if (error) return <PageErrorBanner message={error} />;

  return (
    <div className="grid gap-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-accent">Research notes</p>
        <h2 className="text-3xl font-semibold">Structured research notes</h2>
        <Link className="text-sm text-accent hover:underline" href="/research">← Research</Link>
      </div>
      <Disclaimer />

      <form onSubmit={create} className="grid gap-3 rounded-md border border-line bg-white p-4">
        <div className="grid gap-3 md:grid-cols-3">
          <input className="rounded-md border border-line px-3 py-2 text-sm" placeholder="Instrument (e.g. MSFT)" value={instrument} onChange={(e) => setInstrument(e.target.value)} aria-label="Instrument" />
          <select className="rounded-md border border-line px-3 py-2 text-sm" value={type} onChange={(e) => setType(e.target.value)} aria-label="Note type">
            {NOTE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input className="rounded-md border border-line px-3 py-2 text-sm" placeholder="tags, comma, separated" value={tags} onChange={(e) => setTags(e.target.value)} aria-label="Tags" />
        </div>
        <input className="rounded-md border border-line px-3 py-2 text-sm" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Title" />
        <textarea className="min-h-[80px] rounded-md border border-line px-3 py-2 text-sm" placeholder="Note…" value={body} onChange={(e) => setBody(e.target.value)} aria-label="Body" />
        <button type="submit" className="justify-self-start rounded-md border border-line px-3 py-2 text-sm hover:bg-panel">Save note</button>
      </form>
      {note ? <PageErrorBanner message={note} /> : null}

      <div className="grid gap-2">
        {notes.length === 0 ? (
          <p className="text-sm text-zinc-600">No notes yet.</p>
        ) : (
          notes.map((n) => (
            <div key={String(n.note_id)} className="rounded-md border border-line bg-white p-3">
              <div className="flex justify-between text-sm">
                <span className="font-semibold">{String(n.title || n.symbol || "note")}</span>
                <span className="text-zinc-500">{String(n.note_type)} · v{String(n.version)}</span>
              </div>
              <p className="mt-1 text-sm text-zinc-700">{String(n.body)}</p>
              {((n.tags as string[]) ?? []).length ? (
                <p className="mt-1 text-xs text-zinc-500">{((n.tags as string[]) ?? []).join(" · ")}</p>
              ) : null}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default function ResearchNotesPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <NotesContent />
    </Suspense>
  );
}
