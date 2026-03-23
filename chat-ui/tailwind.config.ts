import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ["'DM Serif Display'", "serif"],
        mono: ["'JetBrains Mono'", "monospace"],
        body: ["'DM Sans'", "sans-serif"],
      },
      colors: {
        ink: {
          950: "#08080f",
          900: "#0e0e1a",
          800: "#161624",
          700: "#1e1e30",
          600: "#2a2a42",
          500: "#3a3a5c",
          400: "#5a5a8a",
          300: "#8080b0",
          200: "#a0a0c8",
          100: "#c8c8e8",
          50:  "#f0f0f8",
        },
        volt: {
          500: "#7c5cfc",
          400: "#9b7eff",
          300: "#bba8ff",
        },
        ember: {
          500: "#f56c42",
          400: "#ff8560",
        },
        jade: {
          500: "#2ecc8f",
          400: "#50e0a8",
        },
      },
      animation: {
        "fade-up": "fadeUp 0.4s ease forwards",
        "pulse-dot": "pulseDot 1.5s ease-in-out infinite",
        "thinking": "thinking 1.2s ease-in-out infinite",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseDot: {
          "0%, 100%": { opacity: "0.3", transform: "scale(0.8)" },
          "50%": { opacity: "1", transform: "scale(1)" },
        },
        thinking: {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
