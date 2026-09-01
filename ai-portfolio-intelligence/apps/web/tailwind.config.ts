import type { Config } from "tailwindcss";

/**
 * Colours resolve through the CSS variables declared in `app/globals.css`.
 *
 * The app already uses `zinc-*` semantically (500/600 = muted copy, 50/100 =
 * wells, 900 = headings) across ~630 call sites, and `bg-white` for cards.
 * Re-pointing those scales at the token variables themes the entire app —
 * light and dark — without adding a `dark:` variant to every element.
 */
const config: Config = {
  darkMode: ["variant", [':root[data-theme="dark"] &', '@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) & }']],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Neutral ramp. Kept on the `zinc` name so existing markup themes itself.
        zinc: {
          50: "var(--c-2)",
          100: "var(--c-3)",
          200: "var(--c-3)",
          300: "var(--c-4)",
          400: "var(--c-5)",
          500: "var(--c-6)",
          600: "var(--c-7)",
          700: "var(--c-7)",
          800: "var(--c-8)",
          900: "var(--c-9)",
          950: "var(--c-9)",
        },
        white: "var(--c-1)",

        ink: "var(--c-9)",
        panel: "var(--c-2)",
        surface: "var(--c-1)",
        canvas: "var(--c-0)",
        line: "var(--c-4)",
        hairline: "var(--c-3)",
        muted: "var(--c-6)",
        faint: "var(--c-5)",

        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          soft: "var(--accent-soft)",
          border: "var(--accent-border)",
          on: "var(--accent-on)",
        },
        positive: {
          DEFAULT: "var(--positive)",
          soft: "var(--positive-soft)",
          border: "var(--positive-border)",
        },
        negative: {
          DEFAULT: "var(--negative)",
          soft: "var(--negative-soft)",
          border: "var(--negative-border)",
        },
        warning: {
          DEFAULT: "var(--warning)",
          soft: "var(--warning-soft)",
          border: "var(--warning-border)",
        },
        info: {
          DEFAULT: "var(--info)",
          soft: "var(--info-soft)",
          border: "var(--info-border)",
        },
        danger: "var(--negative)",

        // Tinted status backgrounds already used across the pages. Re-pointing
        // them keeps banners legible on the dark canvas.
        emerald: {
          50: "var(--positive-soft)",
          100: "var(--positive-soft)",
          200: "var(--positive-border)",
          300: "var(--positive-border)",
          600: "var(--positive)",
          700: "var(--positive)",
          800: "var(--positive)",
        },
        teal: { 50: "var(--accent-soft)", 100: "var(--accent-soft)", 200: "var(--accent-border)" },
        amber: {
          50: "var(--warning-soft)",
          100: "var(--warning-soft)",
          200: "var(--warning-border)",
          500: "var(--warning)",
          700: "var(--warning)",
          800: "var(--warning)",
          900: "var(--warning)",
        },
        red: {
          50: "var(--negative-soft)",
          100: "var(--negative-soft)",
          300: "var(--negative-border)",
          500: "var(--negative)",
          600: "var(--negative)",
          700: "var(--negative)",
        },
        rose: {
          50: "var(--negative-soft)",
          200: "var(--negative-border)",
          600: "var(--negative)",
          700: "var(--negative)",
        },
        sky: { 50: "var(--info-soft)", 200: "var(--info-border)", 700: "var(--info)" },
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        DEFAULT: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Inter",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
