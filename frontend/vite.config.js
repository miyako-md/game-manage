import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { buildVersion } from './build-version.js'

const version = buildVersion(fileURLToPath(new URL('..', import.meta.url)))

// Optional, user-owned artwork stays outside the public repository.
const localGameIcons = Object.fromEntries(
  ['nte', 'wuthering_waves', 'league_of_legends', 'endfield'].flatMap(id => {
    const file = ['png', 'jpg', 'webp', 'svg'].map(ext => `${id}.${ext}`)
      .find(name => existsSync(new URL(`./public/local-game-icons/${name}`, import.meta.url)))
    return file ? [[id, `/local-game-icons/${file}`]] : []
  }),
)

export default defineConfig({
  plugins: [vue(), { name: 'build-provenance', generateBundle() {
    this.emitFile({ type: 'asset', fileName: 'build-info.json', source: JSON.stringify(version) + '\n' })
  } }],
  build: { rolldownOptions: {
    input: { main: fileURLToPath(new URL('./index.html', import.meta.url)), render: fileURLToPath(new URL('./render.html', import.meta.url)), renderA:fileURLToPath(new URL('./render-a.html',import.meta.url)) },
    // Vue changes only with a dependency bump, so it gets its own long-lived chunk instead of riding in
    // whichever app chunk Rolldown shares first. Game pages keep the automatic split.
    output: { codeSplitting: { groups: [{ name: 'vendor-vue', test: /node_modules[\/](@vue|vue)[\/]/ }] } },
  } },
  define: { __LOCAL_GAME_ICONS__: JSON.stringify(localGameIcons) },
  // Vite 8 默认只绑 IPv6 [::1]，浏览器 localhost 走 IPv4 会拒连——固定 IPv4 回环。
  // 端口也固定：后端只放行 5173/8010 来源，换成 5174 时所有写请求都会 403。
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8010' } },
})
