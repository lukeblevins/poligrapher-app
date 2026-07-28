/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#0f766e", light: "#14b8a6", dark: "#115e59" },
      },
      fontFamily: {
        sans: ['"Roboto Variable"', "Roboto", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ['"Roboto Variable"', "Roboto", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1rem" }],
        sm: ["0.875rem", { lineHeight: "1.25rem" }],
        base: ["1rem", { lineHeight: "1.5rem" }],
        lg: ["1rem", { lineHeight: "1.5rem" }],
        xl: ["1.25rem", { lineHeight: "1.75rem" }],
        "2xl": ["1.5rem", { lineHeight: "2rem" }],
        "3xl": ["2rem", { lineHeight: "2.5rem" }],
        "4xl": ["2.25rem", { lineHeight: "2.75rem" }],
      },
      fontWeight: {
        normal: "400",
        medium: "500",
        semibold: "500",
        bold: "700",
      },
    },
  },
  plugins: [],
};
