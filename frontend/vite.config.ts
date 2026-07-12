import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  base: "/cncflow/",
  server: { proxy: { "/cncflow/api": { target: "http://127.0.0.1:5001", rewrite: p => p.replace(/^\/cncflow/, "") } } },
})
