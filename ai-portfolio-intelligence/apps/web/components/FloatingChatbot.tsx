"use client";

import { useState, useEffect, useRef } from "react";
import { MessageSquare, X, Send, Sparkles, Plus, Trash2, HelpCircle } from "lucide-react";
import { sendChatMessage, getPositions } from "@/lib/api";
import type { Position } from "@/lib/types";

interface Message {
  role: "user" | "model";
  content: string;
}

export function FloatingChatbot() {
  const [isOpen, setIsOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [taggedSymbols, setTaggedSymbols] = useState<string[]>([]);
  const [history, setHistory] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [positions, setPositions] = useState<Position[]>([]);
  const [showTagDropdown, setShowTagDropdown] = useState(false);
  const [customTicker, setCustomTicker] = useState("");
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load from localStorage on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedHistory = localStorage.getItem("chatbot_history");
      if (savedHistory) {
        try {
          setHistory(JSON.parse(savedHistory));
        } catch {}
      }
      const savedTags = localStorage.getItem("chatbot_tagged_symbols");
      if (savedTags) {
        try {
          setTaggedSymbols(JSON.parse(savedTags));
        } catch {}
      }
    }
  }, []);

  // Save to localStorage when history changes
  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("chatbot_history", JSON.stringify(history));
    }
  }, [history]);

  // Save to localStorage when taggedSymbols change
  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("chatbot_tagged_symbols", JSON.stringify(taggedSymbols));
    }
  }, [taggedSymbols]);

  function clearChat() {
    setHistory([]);
    if (typeof window !== "undefined") {
      localStorage.removeItem("chatbot_history");
    }
  }

  // Fetch portfolio holdings for quick-tagging options
  useEffect(() => {
    getPositions().then(setPositions).catch(() => {});
  }, []);

  // Listen for global tag event from stock research detail pages
  useEffect(() => {
    function handleTagEvent(e: Event) {
      const customEvent = e as CustomEvent<{ symbol: string }>;
      const sym = customEvent.detail.symbol.toUpperCase();
      setTaggedSymbols((prev) => {
        if (prev.includes(sym)) return prev;
        return [...prev, sym];
      });
      setIsOpen(true);
    }

    window.addEventListener("tag-stock-for-chat", handleTagEvent);
    return () => {
      window.removeEventListener("tag-stock-for-chat", handleTagEvent);
    };
  }, []);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, isLoading]);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!message.trim() && taggedSymbols.length === 0) return;

    const userMsg = message.trim() || `Analyze the tagged assets: ${taggedSymbols.join(", ")}`;
    const newHistory: Message[] = [...history, { role: "user", content: userMsg }];
    
    setHistory(newHistory);
    setMessage("");
    setIsLoading(true);

    try {
      const response = await sendChatMessage(userMsg, taggedSymbols, history);
      setHistory([...newHistory, { role: "model", content: response.response }]);
    } catch (exc) {
      setHistory([
        ...newHistory,
        {
          role: "model",
          content: `*Error connecting to analysis server: ${exc instanceof Error ? exc.message : "Request failed"}*`
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  function toggleTag(symbol: string) {
    const sym = symbol.toUpperCase().trim();
    if (taggedSymbols.includes(sym)) {
      setTaggedSymbols((prev) => prev.filter((s) => s !== sym));
    } else {
      setTaggedSymbols((prev) => [...prev, sym]);
    }
  }

  function addCustomTicker(e: React.FormEvent) {
    e.preventDefault();
    if (!customTicker.trim()) return;
    const sym = customTicker.toUpperCase().trim();
    if (!taggedSymbols.includes(sym)) {
      setTaggedSymbols((prev) => [...prev, sym]);
    }
    setCustomTicker("");
    setShowTagDropdown(false);
  }

  function clearAllTags() {
    setTaggedSymbols([]);
  }

  // Simple, bulletproof inline markdown formatter for custom bold/headers/bullets rendering
  function renderMarkdown(text: string) {
    return text.split("\n").map((line, idx) => {
      const cleanLine = line.trim();
      if (!cleanLine) return <div key={idx} className="h-2" />;
      
      // Header Level 3
      if (cleanLine.startsWith("###")) {
        return (
          <h4 key={idx} className="text-xs font-bold text-zinc-900 mt-2 mb-1">
            {cleanLine.replace("###", "").trim()}
          </h4>
        );
      }
      // Header Level 2
      if (cleanLine.startsWith("##")) {
        return (
          <h3 key={idx} className="text-sm font-bold text-zinc-950 mt-3 mb-1.5 border-b border-zinc-100 pb-0.5">
            {cleanLine.replace("##", "").trim()}
          </h3>
        );
      }
      // Bullet Items
      if (cleanLine.startsWith("*") || cleanLine.startsWith("-")) {
        const bulletText = cleanLine.substring(1).trim();
        return (
          <ul key={idx} className="list-disc pl-4 text-[11px] text-zinc-700 my-0.5 leading-relaxed">
            <li>{parseInlineStyles(bulletText)}</li>
          </ul>
        );
      }
      
      // Default paragraph line
      return (
        <p key={idx} className="text-[11px] text-zinc-700 leading-relaxed my-1">
          {parseInlineStyles(cleanLine)}
        </p>
      );
    });
  }

  function parseInlineStyles(text: string) {
    const boldParts = text.split("**");
    return boldParts.map((part, i) => {
      if (i % 2 === 1) {
        return <strong key={i} className="font-bold text-zinc-900">{part}</strong>;
      }
      const italicParts = part.split("*");
      return italicParts.map((subPart, j) => {
        if (j % 2 === 1) {
          return <em key={j} className="italic text-zinc-800">{subPart}</em>;
        }
        return subPart;
      });
    });
  }

  return (
    <>
      {/* Floating Toggle Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-6 right-6 z-50 flex h-12 w-12 items-center justify-center rounded-full bg-accent text-white shadow-xl hover:bg-accent/90 hover:scale-105 active:scale-95 transition-all focus:outline-none"
        title="AI Assistant Chatbot"
        aria-label="Toggle AI Assistant Chatbot"
      >
        {isOpen ? <X size={20} /> : <MessageSquare size={20} />}
      </button>

      {/* Floating Chat Panel */}
      {isOpen && (
        <div className="fixed bottom-20 right-6 z-50 w-96 h-[520px] bg-white/95 backdrop-blur border border-line rounded-xl shadow-2xl flex flex-col overflow-hidden transition-all duration-200">
          
          {/* Header */}
          <div className="bg-zinc-900 text-white p-3.5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-amber-400" />
              <div>
                <h4 className="text-xs font-bold leading-none">AI Research Assistant</h4>
                <span className="text-[9px] text-zinc-400 leading-none block mt-0.5">
                  Search Grounding Active
                </span>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {history.length > 0 && (
                <button
                  onClick={clearChat}
                  className="text-[10px] font-semibold text-zinc-400 hover:text-red-400 transition-colors flex items-center gap-1"
                >
                  <Trash2 size={11} /> Clear Chat
                </button>
              )}
              <button onClick={() => setIsOpen(false)} className="text-zinc-400 hover:text-white transition-colors">
                <X size={16} />
              </button>
            </div>
          </div>

          {/* Tagged Securities Bar */}
          <div className="bg-panel border-b border-line px-3 py-2 flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">
                Tagged Stocks ({taggedSymbols.length})
              </span>
              <div className="flex items-center gap-2">
                {taggedSymbols.length > 0 && (
                  <button
                    onClick={clearAllTags}
                    className="text-[9px] font-semibold text-zinc-400 hover:text-danger flex items-center gap-0.5"
                  >
                    <Trash2 size={10} /> Clear
                  </button>
                )}
                <button
                  onClick={() => setShowTagDropdown(!showTagDropdown)}
                  className="inline-flex items-center gap-0.5 text-[9px] font-semibold text-accent hover:underline"
                >
                  <Plus size={10} /> Tag Ticker
                </button>
              </div>
            </div>

            {/* Ticker pills list */}
            {taggedSymbols.length > 0 ? (
              <div className="flex flex-wrap gap-1.5 max-h-16 overflow-y-auto pr-1">
                {taggedSymbols.map((sym) => (
                  <span
                    key={sym}
                    className="inline-flex items-center gap-1 rounded bg-accent/10 px-1.5 py-0.5 text-[10px] font-bold text-accent border border-accent/20"
                  >
                    {sym}
                    <button
                      onClick={() => toggleTag(sym)}
                      className="text-accent/60 hover:text-accent focus:outline-none"
                    >
                      <X size={8} />
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-[10px] text-zinc-400 italic">No stocks tagged. Tag symbols to feed them as AI context.</p>
            )}

            {/* Tag Selection Dropdown Overlay */}
            {showTagDropdown && (
              <div className="mt-1.5 rounded-md border border-line bg-white p-3 shadow-md grid gap-2.5">
                <form onSubmit={addCustomTicker} className="flex gap-1.5">
                  <input
                    type="text"
                    placeholder="Enter ticker (e.g. AMZN)"
                    value={customTicker}
                    onChange={(e) => setCustomTicker(e.target.value)}
                    className="w-full rounded border border-line px-2 py-1 text-xs text-zinc-900 focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                  <button
                    type="submit"
                    className="rounded bg-accent px-2.5 py-1 text-xs font-semibold text-white hover:bg-accent/90"
                  >
                    Add
                  </button>
                </form>
                {positions.length > 0 && (
                  <div>
                    <span className="text-[8px] font-bold text-zinc-400 uppercase tracking-wider block mb-1">
                      Portfolio Holdings
                    </span>
                    <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto">
                      {positions.map((pos) => {
                        const isTagged = taggedSymbols.includes(pos.symbol);
                        return (
                          <button
                            key={pos.symbol}
                            onClick={() => toggleTag(pos.symbol)}
                            className={`rounded px-1.5 py-0.5 text-[9px] font-semibold border transition-all ${
                              isTagged
                                ? "bg-accent text-white border-accent"
                                : "bg-panel text-zinc-600 border-line hover:bg-zinc-100"
                            }`}
                          >
                            {pos.symbol}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Chat Messages Log */}
          <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5 bg-zinc-50">
            {history.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-4">
                <Sparkles className="text-zinc-300 mb-2.5" size={28} />
                <p className="text-xs font-bold text-zinc-700">AI Portfolio Copilot</p>
                <p className="text-[10px] text-zinc-500 mt-1 max-w-[200px] leading-relaxed">
                  Tag stocks and ask questions. I will auto-inject live prices, news, and fundamentals to answer your queries!
                </p>
              </div>
            ) : (
              history.map((msg, index) => {
                const isUser = msg.role === "user";
                return (
                  <div key={index} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[85%] rounded-lg p-2.5 text-xs shadow-sm border ${
                        isUser
                          ? "bg-zinc-900 border-zinc-900 text-zinc-100"
                          : "bg-white border-line text-zinc-800"
                      }`}
                    >
                      {isUser ? (
                        <p className="whitespace-pre-wrap text-[11px] leading-relaxed">{msg.content}</p>
                      ) : (
                        renderMarkdown(msg.content)
                      )}
                    </div>
                  </div>
                );
              })
            )}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white border border-line rounded-lg p-3 text-xs shadow-sm flex items-center gap-2 text-zinc-500">
                  <span className="flex h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400" />
                  <span className="flex h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 delay-75" />
                  <span className="flex h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 delay-150" />
                  <span className="text-[10px] font-semibold">AI is analyzing tagged data...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Chat Entry Form */}
          <form onSubmit={handleSend} className="p-3 border-t border-line bg-white flex gap-2">
            <input
              type="text"
              placeholder={
                taggedSymbols.length > 0
                  ? `Ask about tagged: ${taggedSymbols.join(", ")}...`
                  : "Ask a question about stocks..."
              }
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              className="flex-1 rounded-md border border-line bg-zinc-50 px-3 py-1.5 text-xs text-zinc-900 focus:border-accent focus:bg-white focus:outline-none focus:ring-1 focus:ring-accent"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading || (!message.trim() && taggedSymbols.length === 0)}
              className="flex items-center justify-center rounded-md bg-accent text-white p-2 hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              <Send size={14} />
            </button>
          </form>

        </div>
      )}
    </>
  );
}
