/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        "dark-bg": "#0a0e1a",
        "dark-card": "#131824",
        "dark-border": "#1e2636",
        "accent-green": "#00d395",
        "accent-red": "#ff4757",
        "accent-yellow": "#fbbf24"
      }
    }
  },
  plugins: []
}