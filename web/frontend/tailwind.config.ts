import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Surfaces
        ink: "#0f1729",
        "ink-soft": "#3a4456",
        muted: "#6b7689",
        faint: "#9aa3b3",
        line: "#e3e8f0",
        "line-strong": "#cbd4e3",
        panel: "#ffffff",
        bg: "#f4f6fa",
        // Brand & semantic
        brand: {
          DEFAULT: "#2f5f9f",
          50: "#eef4fb",
          100: "#d7e4f5",
          200: "#a8c2e3",
          500: "#2f5f9f",
          600: "#275083",
          700: "#1d3d63",
        },
        safe: {
          DEFAULT: "#1c7a4f",
          50: "#e8f6ee",
          100: "#c6e6d3",
          500: "#1c7a4f",
          600: "#155a3a",
        },
        warn: {
          DEFAULT: "#a8660f",
          50: "#fdf3e3",
          100: "#f5dcb4",
          500: "#a8660f",
          600: "#7d4b08",
        },
        danger: {
          DEFAULT: "#a83232",
          50: "#fbe6e6",
          100: "#f0b8b8",
          500: "#a83232",
          600: "#7d2424",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 41, 0.04), 0 6px 16px rgba(15, 23, 41, 0.05)",
        "card-hover":
          "0 2px 4px rgba(15, 23, 41, 0.06), 0 12px 28px rgba(15, 23, 41, 0.08)",
        panel: "0 8px 30px rgba(15, 23, 41, 0.08)",
        pop: "0 1px 0 rgba(15, 23, 41, 0.04), 0 16px 40px rgba(43, 99, 159, 0.18)",
      },
      borderRadius: {
        xl: "12px",
        "2xl": "16px",
      },
      transitionTimingFunction: {
        soft: "cubic-bezier(0.4, 0, 0.2, 1)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
      },
      animation: {
        "fade-in": "fade-in 200ms cubic-bezier(0.4,0,0.2,1)",
        pulse: "pulse 1.6s cubic-bezier(0.4,0,0.2,1) infinite",
      },
    },
  },
  plugins: [],
};

export default config;
