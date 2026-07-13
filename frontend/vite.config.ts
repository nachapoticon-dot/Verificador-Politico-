import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// El frontend se construye a dist/ y el servidor FastAPI lo sirve. En desarrollo
// (vite dev) las llamadas a /api se redirigen a uvicorn en el 8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
