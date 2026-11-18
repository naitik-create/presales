import type { Config } from "tailwindcss";

/**
 * Motadata brand tokens (§18.4). The default Tailwind palette, font sizes and spacing are replaced, not extended,
 * so components can only use values from the brand scale.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      black: "var(--primary-black)",
      white: "var(--pure-white)",
      offwhite: "var(--off-white)",
      border: "var(--border-gray)",
      lightborder: "var(--light-border)",
      muted: "var(--medium-gray)",
      accent: "var(--accent)",
      "accent-text": "var(--accent-text)",
      mono: {
        50: "var(--mono-50)", 100: "var(--mono-100)", 200: "var(--mono-200)", 300: "var(--mono-300)",
        400: "var(--mono-400)", 500: "var(--mono-500)", 600: "var(--mono-600)", 700: "var(--mono-700)",
        800: "var(--mono-800)", 900: "var(--mono-900)",
      },
      success: "var(--status-success)",
      warning: "var(--status-warning)",
      error: "var(--status-error)",
      info: "var(--status-info)",
    },
    spacing: {
      0: "0", px: "1px", 1: "4px", 2: "8px", 3: "12px", 4: "16px", 5: "20px", 6: "24px", 8: "32px", 12: "48px", 16: "64px",
    },
    fontFamily: {
      sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Arial", "sans-serif"],
    },
    fontSize: {
      h1: ["56px", { lineHeight: "1.1", fontWeight: "600" }],
      h2: ["36px", { lineHeight: "1.2", fontWeight: "600" }],
      h3: ["24px", { lineHeight: "1.3", fontWeight: "600" }],
      h4: ["20px", { lineHeight: "1.4", fontWeight: "600" }],
      h5: ["18px", { lineHeight: "1.4", fontWeight: "600" }],
      h6: ["16px", { lineHeight: "1.4", fontWeight: "600" }],
      lg: ["20px", { lineHeight: "1.6" }],
      base: ["16px", { lineHeight: "1.6" }],
      sm: ["14px", { lineHeight: "1.5" }],
    },
    fontWeight: { normal: "400", semibold: "600" },
    borderRadius: { none: "0", sm: "4px", DEFAULT: "8px", lg: "12px", full: "9999px" },
    extend: {
      width: { sidebar: "256px", "sidebar-collapsed": "64px", 12: "48px", 24: "96px", 32: "128px", 40: "160px", 56: "224px", 96: "384px" },
      maxWidth: { sm: "384px", lg: "512px", content: "1440px", prose: "768px" },
      boxShadow: { sm: "0 1px 2px rgb(0 0 0 / 0.08)" },
    },
  },
  plugins: [],
};

export default config;
