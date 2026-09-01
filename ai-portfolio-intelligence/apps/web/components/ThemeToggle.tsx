"use client";

import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";

export type ThemeChoice = "light" | "dark" | "system";

const STORAGE_KEY = "pai.theme";

/**
 * Inlined into <head> so the correct palette is painted before first paint.
 * Without it the app flashes light before a stored dark preference applies.
 */
export const THEME_BOOTSTRAP_SCRIPT = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  STORAGE_KEY,
)});if(t==="dark"||t==="light"){document.documentElement.setAttribute("data-theme",t);}}catch(e){}})();`;

function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", choice);
  }
}

const OPTIONS: Array<{ value: ThemeChoice; label: string; Icon: typeof Sun }> = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
];

export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>("system");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "dark" || stored === "light") {
        setChoice(stored);
      }
    } catch {
      // Storage unavailable: stay on the system preference.
    }
  }, []);

  function select(next: ThemeChoice) {
    setChoice(next);
    applyTheme(next);
    try {
      if (next === "system") {
        localStorage.removeItem(STORAGE_KEY);
      } else {
        localStorage.setItem(STORAGE_KEY, next);
      }
    } catch {
      // Preference simply will not persist.
    }
  }

  // The stored choice is only known on the client; render the control inert
  // until then so the markup matches what was prerendered.
  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="flex items-center gap-0.5 rounded-md border border-hairline bg-panel p-0.5"
    >
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = mounted && choice === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={`${label} theme`}
            onClick={() => select(value)}
            className={`flex flex-1 items-center justify-center rounded px-2 py-1 transition-colors ${
              active ? "bg-surface text-zinc-900 shadow-sm" : "text-zinc-500 hover:text-zinc-900"
            }`}
          >
            <Icon size={13} aria-hidden />
          </button>
        );
      })}
    </div>
  );
}
