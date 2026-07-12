/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {
    colors: { border: "hsl(var(--border))", background: "hsl(var(--background))", foreground: "hsl(var(--foreground))", muted: "hsl(var(--muted))", primary: "hsl(var(--primary))" },
    fontFamily: { sans: ["IBM Plex Sans", "Noto Sans SC", "sans-serif"], mono: ["IBM Plex Mono", "monospace"] },
  } }, plugins: [],
}
