/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        "dark-bg": "#131722",      // TV exact background
        "dark-card": "#1e222d",     // TV panel
        "dark-border": "#2a2e39",   // TV border
        "accent-green": "#26a69a",  // TV bullish
        "accent-red": "#ef5350",    // TV bearish
        "accent-yellow": "#fbbf24",
        "accent-blue": "#3b82f6",
        "tv-text": "#d1d4dc",       // TV primary text
        "tv-dim": "#787b86",        // TV secondary text
      }
    }
  },
  plugins: []
}