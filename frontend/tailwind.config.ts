import type { Config } from "tailwindcss";

/**
 * "Hextech Arena" — a dark, esports-grade design system for the LoL Draft
 * Predictor. Dark-only by design (every serious LoL tool is): obsidian/navy
 * surfaces, Hextech gold + teal accents, and vivid Blue-vs-Red team colors.
 */
const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Page + layered surfaces (dark obsidian → lifted navy).
        canvas: "#06090F",
        "canvas-2": "#0A0F1B",
        surface: "#0E1626",
        "surface-2": "#142036", // raised: inputs, inner cards
        "surface-3": "#1B2942", // hover / active
        // Hairlines.
        line: "#1E2C44",
        "line-strong": "#2C3E5E",
        // Text.
        ink: "#EDF1F8",
        "ink-soft": "#C3CEE0",
        "ink-muted": "#8A97AE",
        "ink-dim": "#5E6C86",
        // Hextech gold — the primary brand accent.
        gold: {
          DEFAULT: "#C8AA6E",
          bright: "#F0E6D2",
          deep: "#785A28",
          glow: "#E4C98B",
        },
        // Hextech teal — secondary "magic" accent.
        teal: {
          DEFAULT: "#2DD4BF",
          deep: "#0AC8B9",
        },
        // Team Blue (Summoner's Rift blue side).
        team_blue: {
          DEFAULT: "#3B82F6",
          glow: "#60A5FA",
          deep: "#1D4ED8",
        },
        // Team Red (Riot red).
        team_red: {
          DEFAULT: "#FF4655",
          glow: "#FF6B78",
          deep: "#C81E2E",
        },
        win: "#34D399",
        loss: "#FB6E6E",
      },
      fontFamily: {
        sans: [
          "var(--font-geist-sans)",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
        display: [
          "var(--font-display)",
          "var(--font-geist-sans)",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        // Soft elevation for cards on dark surfaces.
        card: "inset 0 1px 0 0 rgba(255,255,255,0.03), 0 12px 32px -12px rgba(0,0,0,0.7)",
        "card-hover":
          "inset 0 1px 0 0 rgba(255,255,255,0.05), 0 18px 44px -14px rgba(0,0,0,0.85)",
        // Accent glows.
        gold: "0 0 0 1px rgba(200,170,110,0.35), 0 8px 30px -8px rgba(200,170,110,0.4)",
        "glow-blue": "0 0 24px -2px rgba(96,165,250,0.55)",
        "glow-red": "0 0 24px -2px rgba(255,107,120,0.55)",
        "glow-teal": "0 0 24px -2px rgba(45,212,191,0.5)",
      },
      backgroundImage: {
        "gold-sheen":
          "linear-gradient(135deg, #F0E6D2 0%, #C8AA6E 42%, #A17E45 100%)",
        "blue-fill":
          "linear-gradient(90deg, #1D4ED8 0%, #3B82F6 55%, #60A5FA 100%)",
        "red-fill":
          "linear-gradient(90deg, #C81E2E 0%, #FF4655 55%, #FF6B78 100%)",
        "hex-grid":
          "radial-gradient(circle at 1px 1px, rgba(200,170,110,0.06) 1px, transparent 0)",
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.97)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "pulse-glow": {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.16,1,0.3,1) both",
        "fade-in": "fade-in 0.4s ease-out both",
        "scale-in": "scale-in 0.35s cubic-bezier(0.16,1,0.3,1) both",
        shimmer: "shimmer 1.6s infinite",
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
