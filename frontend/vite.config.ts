import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies the API to uvicorn so the browser sees a single
// origin and Server-Sent Events are not held up by a CORS preflight.
// Point VITE_API_TARGET elsewhere if you run uvicorn on another port.
const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8010'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
