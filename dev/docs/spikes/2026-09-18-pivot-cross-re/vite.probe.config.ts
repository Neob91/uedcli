// Throwaway dev-server config for the pivot-cross live check. Same as web/vite.config.ts but
// proxying to THIS session's own backend port, so it never touches the owner's live preview
// (backend 8765 / vite 5173).
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  root: '/workspace/uedcli/.claude/worktrees/agent-af7a9d5b5d2b653b1/web',
  plugins: [react()],
  server: {
    port: 5211,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8795',
      '/ws': { target: 'ws://127.0.0.1:8795', ws: true },
    },
  },
})
