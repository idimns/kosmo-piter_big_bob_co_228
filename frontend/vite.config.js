import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev-сервер проксирует /api на бэкенд (uvicorn на 8000)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
