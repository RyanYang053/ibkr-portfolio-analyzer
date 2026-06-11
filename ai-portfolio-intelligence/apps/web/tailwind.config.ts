import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#18211f",
        panel: "#f6f8f5",
        line: "#dbe4df",
        accent: "#0f766e",
        warning: "#b45309",
        danger: "#b91c1c"
      }
    }
  },
  plugins: []
};

export default config;
