import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // Vite 8 默认只绑 IPv6 [::1]，浏览器 localhost 走 IPv4 会拒连——固定 IPv4 回环
  server: { host: '127.0.0.1', port: 5173, proxy: { '/api': 'http://127.0.0.1:8010' } },
})
