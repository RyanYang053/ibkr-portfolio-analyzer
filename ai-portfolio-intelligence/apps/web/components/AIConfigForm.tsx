"use client";

import { useState } from "react";
import { KeyRound, Save } from "lucide-react";
import { configureAI } from "@/lib/api";

const GEMINI_MODELS = [
  "gemini-2.5-flash",
  "gemini-2.5-flash-lite",
  "gemini-3.5-flash",
];

export function AIConfigForm({ defaultModel }: { defaultModel: string }) {
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(defaultModel);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function save() {
    setIsSaving(true);
    setError(null);
    setStatus(null);
    try {
      const response = await configureAI(apiKey, model);
      setStatus(`Gemini configured for this API process using ${response.model}.`);
      setApiKey("");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Could not configure Gemini");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="mt-4 rounded-md border border-line bg-panel p-3">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <KeyRound size={16} aria-hidden />
        Enter Gemini API key
      </div>
      <div className="grid gap-3">
        <input
          className="rounded-md border border-line px-3 py-2 text-sm"
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="Gemini API key"
          autoComplete="off"
        />
        <select
          className="rounded-md border border-line px-3 py-2 text-sm"
          value={model}
          onChange={(event) => setModel(event.target.value)}
        >
          {GEMINI_MODELS.map((modelId) => (
            <option key={modelId} value={modelId}>
              {modelId}
            </option>
          ))}
        </select>
        <button
          className="inline-flex items-center justify-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
          onClick={save}
          disabled={isSaving || apiKey.length < 10}
        >
          <Save size={16} aria-hidden />
          {isSaving ? "Saving" : "Save for this session"}
        </button>
      </div>
      <p className="mt-3 text-xs text-zinc-600">
        The key is sent to the backend and kept in memory for this running API process. It is not stored in browser local storage.
      </p>
      {status ? <p className="mt-3 rounded-md border border-accent bg-teal-50 p-2 text-sm text-accent">{status}</p> : null}
      {error ? <p className="mt-3 rounded-md border border-danger bg-red-50 p-2 text-sm text-danger">{error}</p> : null}
    </div>
  );
}
