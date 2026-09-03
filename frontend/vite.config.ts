import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE || "/cncflow/",
  server: {
    proxy: {
      "/cncflow/api/v1/chat": { target: "http://127.0.0.1:3002", rewrite: p => p.replace(/^\/cncflow/, "") },
      "/cncflow/api/chat": { target: "http://127.0.0.1:3002", rewrite: p => p.replace(/^\/cncflow/, "") },
      "/cncflow/api": { target: "http://127.0.0.1:5001", rewrite: p => p.replace(/^\/cncflow/, "") },
    },
  },
})
