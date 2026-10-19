import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The API is reached through the dev server, so the browser sees a single origin and needs no CORS.
// Inside docker compose API_URL points to the app service; outside it falls back to localhost.
const apiUrl = process.env.API_URL || 'http://localhost:8080'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: apiUrl,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
