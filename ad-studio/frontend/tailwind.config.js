/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"], display: ["'Plus Jakarta Sans'", "Inter", "sans-serif"] },
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        elev: "rgb(var(--elev) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        fg: "rgb(var(--fg) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        brand: { DEFAULT: "#8B5CF6", 2: "#EC4899", 3: "#22D3EE" },
      },
      boxShadow: {
        glow: "0 0 0 1px rgb(139 92 246 / .25), 0 8px 32px -8px rgb(139 92 246 / .45)",
        card: "0 1px 0 0 rgb(255 255 255 / .04) inset, 0 12px 40px -12px rgb(0 0 0 / .5)",
      },
      keyframes: { shimmer: { "100%": { transform: "translateX(100%)" } } },
      animation: { shimmer: "shimmer 1.6s infinite" },
    },
  },
  plugins: [],
};
