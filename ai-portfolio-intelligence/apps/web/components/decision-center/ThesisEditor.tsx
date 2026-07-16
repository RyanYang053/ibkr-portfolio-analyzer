"use client";

import { useState } from "react";
import { putHoldingThesis } from "@/lib/api";

export function ThesisEditor({
  instrumentKey,
  initialText = "",
  accountId,
}: {
  instrumentKey: string;
  initialText?: string;
  accountId?: string;
}) {
  const [text, setText] = useState(initialText);
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSave() {
    setSaving(true);
    setStatus(null);
    try {
      await putHoldingThesis(instrumentKey, text, accountId);
      setStatus("Thesis saved (experimental).");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-2">
      <label className="text-sm font-semibold" htmlFor={`thesis-${instrumentKey}`}>
        Holding thesis
      </label>
      <textarea
        id={`thesis-${instrumentKey}`}
        className="min-h-28 rounded-md border border-line bg-white p-3 text-sm"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <button
        type="button"
        className="w-fit rounded-md bg-zinc-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        disabled={saving || !text.trim()}
        onClick={onSave}
      >
        {saving ? "Saving…" : "Save thesis"}
      </button>
      {status ? <p className="text-xs text-zinc-600">{status}</p> : null}
    </div>
  );
}
