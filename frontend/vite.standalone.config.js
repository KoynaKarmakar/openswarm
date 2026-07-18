// Single self-contained HTML build for the OpenSwarm canvas.
// Renders the Swarm Console with the swarm running client-side (mock) — no backend.
//   npm run build:standalone   →  dist-standalone/standalone.html  (one file)
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

export default defineConfig({
  plugins: [react(), viteSingleFile()],
  define: { 'import.meta.env.VITE_SWARM_MOCK': JSON.stringify('1') },
  build: {
    outDir: 'dist-standalone',
    rollupOptions: { input: 'standalone.html' },
  },
})
