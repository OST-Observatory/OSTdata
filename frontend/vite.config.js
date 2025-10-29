import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load env (supports .env, .env.production, etc.). Only VITE_* are exposed.
  const env = loadEnv(mode, process.cwd(), '')
  // Prefer VITE_BASE (e.g., "/data_archive/") else fallback to root
  const base = env.VITE_BASE || '/'
  return {
    base,
    plugins: [
      vue(),
      vuetify({ autoImport: true }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false
        },
      },
    },
  }
})