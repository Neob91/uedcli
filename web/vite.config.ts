/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dev proxy to `uedcli serve`'s FastAPI/uvicorn backend (default port from
    // uedcli/cli/parsers/serve.py) — the browser talks to Vite's dev server, which forwards
    // /api and /ws so the client can use plain relative paths in both dev and (later) a built
    // static bundle served by the backend itself.
    proxy: {
      '/api': 'http://127.0.0.1:8765',
      '/ws': { target: 'ws://127.0.0.1:8765', ws: true },
    },
  },
  test: {
    environment: 'jsdom',
  },
})
