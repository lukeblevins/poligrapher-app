/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "media", // follow the OS light/dark preference
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#4f46e5", light: "#6366f1", dark: "#3730a3" },
      },
    },
  },
  plugins: [],
};
