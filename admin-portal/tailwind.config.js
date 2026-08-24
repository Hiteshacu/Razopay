/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Aptos Display", "Segoe UI", "sans-serif"],
        body: ["Aptos", "Segoe UI", "sans-serif"]
      },
      colors: {
        ink: "#111827",
        steel: "#334155",
        signal: "#0f766e",
        ember: "#dc2626",
        paper: "#f7f5ef"
      }
    }
  },
  plugins: []
};

