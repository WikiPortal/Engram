import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Geist'", "-apple-system", "sans-serif"],
        mono: ["'Geist Mono'", "monospace"],
      },
      colors: {
        bg:      { DEFAULT: "#0a0a0a", 2: "#111111", 3: "#1a1a1a", 4: "#222222" },
        border:  { DEFAULT: "rgba(255,255,255,0.08)", 2: "rgba(255,255,255,0.12)" },
        txt:     { DEFAULT: "#f0f0f0", 2: "#a0a0a0", 3: "#606060" },
        accent:  { DEFAULT: "#7c6bff", 2: "#9b8dff", 3: "#bdb2ff" },
        success: "#22c55e",
        danger:  "#ef4444",
        warn:    "#f59e0b",
      },
      borderRadius: {
        "4xl": "2rem",
      },
      animation: {
        "fade-in":    "fadeIn 0.25s ease forwards",
        "slide-in":   "slideIn 0.2s ease forwards",
        "spin-slow":  "spin 1.5s linear infinite",
        "pulse-dot":  "pulse 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
