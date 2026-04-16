import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 3333,
    proxy: {
      '/api': 'http://localhost:4444',
      '/openapi.json': 'http://localhost:4444',
    },
  },
  build: {
    outDir: 'dist',
  },
})
