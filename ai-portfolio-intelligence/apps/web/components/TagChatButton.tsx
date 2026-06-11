"use client";

import { MessageSquarePlus } from "lucide-react";

export function TagChatButton({ symbol }: { symbol: string }) {
  function handleTag() {
    window.dispatchEvent(
      new CustomEvent("tag-stock-for-chat", { detail: { symbol } })
    );
  }

  return (
    <button
      onClick={handleTag}
      className="inline-flex items-center gap-1.5 rounded-md border border-line bg-white px-3 py-1.5 text-xs font-semibold text-zinc-600 hover:bg-zinc-50 hover:text-accent hover:border-accent/40 shadow-sm transition-all focus:outline-none"
      title={`Tag ${symbol} for chat analysis`}
    >
      <MessageSquarePlus size={14} className="text-zinc-400" />
      Tag for Chat
    </button>
  );
}
