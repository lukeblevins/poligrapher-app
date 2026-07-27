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
    },
  },
  plugins: [],
};
