import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxyTarget = process.env.NEUROLEAGUE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': proxyTarget,
      '/s/': proxyTarget,
      '/.well-known': proxyTarget,
    },
  },
})
