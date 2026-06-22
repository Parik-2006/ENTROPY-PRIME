import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Entropy Prime — Honeypot UI vite config
// Proxies /score, /honeypot/trigger, /session/verify to the FastAPI backend
// so the dev server can serve the shadow UI without CORS issues.
export default defineConfig({
  plugins: [react()],
  root: '.',
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  server: {
    port: 3001,
    proxy: {
      '/score':             { target: 'http://localhost:8000', changeOrigin: true },
      '/honeypot':          { target: 'http://localhost:8000', changeOrigin: true },
      '/session':           { target: 'http://localhost:8000', changeOrigin: true },
      '/auth':              { target: 'http://localhost:8000', changeOrigin: true },
      '/admin':             { target: 'http://localhost:8000', changeOrigin: true },
      // Phase 3 MVP — shadow world synthetic APIs
      '/api/shadow':        { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
