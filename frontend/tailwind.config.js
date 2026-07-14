/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "media", // follow the OS light/dark preference
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#0f766e", light: "#14b8a6", dark: "#115e59" },
      },
      fontFamily: {
        sans: ['"Source Sans 3 Variable"', '"Source Sans 3"', "ui-sans-serif", "system-ui", "sans-serif"],
        display: ['"Source Serif 4 Variable"', '"Source Serif 4"', "ui-serif", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
