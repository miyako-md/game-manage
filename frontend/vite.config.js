import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { existsSync } from 'node:fs'

// Optional, user-owned artwork stays outside the public repository.
const localGameIcons = Object.fromEntries(
  ['nte', 'wuthering_waves', 'league_of_legends'].flatMap(id => {
    const file = ['png', 'jpg', 'webp', 'svg'].map(ext => `${id}.${ext}`)
      .find(name => existsSync(new URL(`./public/local-game-icons/${name}`, import.meta.url)))
    return file ? [[id, `/local-game-icons/${file}`]] : []
  }),
)

export default defineConfig({
  plugins: [vue()],
  define: { __LOCAL_GAME_ICONS__: JSON.stringify(localGameIcons) },
  // Vite 8 默认只绑 IPv6 [::1]，浏览器 localhost 走 IPv4 会拒连——固定 IPv4 回环
  server: { host: '127.0.0.1', port: 5173, proxy: { '/api': 'http://127.0.0.1:8010' } },
})
