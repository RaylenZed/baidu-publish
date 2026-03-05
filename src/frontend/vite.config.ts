import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

function resolvePreviewAllowedHosts(): true | string[] {
  const raw = process.env.VITE_PREVIEW_ALLOWED_HOSTS?.trim()

  // 缺省放开，适配 DDNS + 端口访问场景
  if (!raw || raw === '*') {
    return true
  }

  const hosts = raw
    .split(',')
    .map((h) => h.trim())
    .filter(Boolean)

  return hosts.length > 0 ? hosts : true
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: resolvePreviewAllowedHosts(),
  },
})
