import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Relative base so dist/ works from any path or static host. Hash routing: no server rewrites needed.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: { outDir: 'dist', sourcemap: false, chunkSizeWarningLimit: 700 },
  server: { port: 5173 },
})
