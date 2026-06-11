"use client";

import { useState } from "react";
import { Clock, Sun, Sunset, Moon, Save, ToggleLeft, ToggleRight } from "lucide-react";
import { updateScheduleSettings } from "@/lib/api";

interface ScheduleConfig {
  enabled: boolean;
  morning_time: string;
  midday_time: string;
  night_time: string;
}

interface ScheduleConfigFormProps {
  initialSettings: ScheduleConfig;
}

export function ScheduleConfigForm({ initialSettings }: ScheduleConfigFormProps) {
  const [settings, setSettings] = useState<ScheduleConfig>(initialSettings);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");

  async function handleSave() {
    setSaving(true);
    setSavedMsg("");
    try {
      await updateScheduleSettings(settings);
      setSavedMsg("Schedule saved successfully.");
    } catch (err) {
      setSavedMsg(`Error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSaving(false);
      setTimeout(() => setSavedMsg(""), 3000);
    }
  }

  const timeSlots = [
    { key: "morning_time" as const, label: "Morning Session", icon: <Sun size={14} className="text-amber-500" />, desc: "Pre-market / market open analysis" },
    { key: "midday_time" as const, label: "Midday Review", icon: <Sunset size={14} className="text-orange-500" />, desc: "Intraday trend & consolidation check" },
    { key: "night_time" as const, label: "Night Wrap-up", icon: <Moon size={14} className="text-indigo-400" />, desc: "Post-market daily PnL review" },
  ];

  return (
    <div className="mt-4 rounded-lg border border-line bg-panel/50 p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Clock size={16} className="text-accent" />
          <span className="text-sm font-bold text-zinc-800">Scheduled Analysis Times</span>
        </div>
        <button
          onClick={() => setSettings((s) => ({ ...s, enabled: !s.enabled }))}
          className="inline-flex items-center gap-1.5 text-xs font-bold text-zinc-600 hover:text-zinc-900 transition-colors"
        >
          {settings.enabled ? (
            <ToggleRight size={20} className="text-accent" />
          ) : (
            <ToggleLeft size={20} className="text-zinc-400" />
          )}
          {settings.enabled ? "Enabled" : "Disabled"}
        </button>
      </div>

      <div className="grid gap-3">
        {timeSlots.map((slot) => (
          <div key={slot.key} className="flex items-center gap-3 rounded-md border border-line bg-white px-3 py-2.5">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              {slot.icon}
              <div>
                <span className="text-xs font-bold text-zinc-800 block">{slot.label}</span>
                <span className="text-[9px] text-zinc-400">{slot.desc}</span>
              </div>
            </div>
            <input
              type="time"
              value={settings[slot.key]}
              onChange={(e) => setSettings((s) => ({ ...s, [slot.key]: e.target.value }))}
              disabled={!settings.enabled}
              className="rounded-md border border-line bg-panel px-2.5 py-1.5 text-xs font-mono text-zinc-700 focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-40 disabled:cursor-not-allowed w-[100px]"
            />
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 mt-4">
        <button
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-xs font-bold text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          <Save size={12} />
          {saving ? "Saving…" : "Save Schedule"}
        </button>
        {savedMsg && (
          <span className={`text-xs font-semibold ${savedMsg.startsWith("Error") ? "text-rose-600" : "text-emerald-600"}`}>
            {savedMsg}
          </span>
        )}
      </div>
    </div>
  );
}
