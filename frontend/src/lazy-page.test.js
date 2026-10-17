import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { nextTick } from 'vue'
import { mount, nodes, content } from './test-utils/vue.js'
import { lazyPage } from './lazy-page.js'

const staticComponents = file => [...readFileSync(new URL(file, import.meta.url), 'utf8').matchAll(/^import \w+ from '\.\/([\w/]+\.vue)'/gm)].map(match => match[1])
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }

test('the cloud app loads only the login form, overview, icons, shared menu and idle update control before its first paint', () => {
  assert.deepEqual(staticComponents('./CloudApp.vue').sort(), ['components/AppIcon.vue', 'components/GameIcon.vue', 'components/MenuSelect.vue', 'components/OverviewPage.vue', 'components/SiteLogin.vue', 'components/SystemUpdateControl.vue'])
})
test('the update dialog stays in its own lazy chunk behind the lightweight control', () => {
  assert.ok(!staticComponents('./components/SystemUpdateControl.vue').some(file => file.endsWith('SystemUpdateDialog.vue')))
  const control = readFileSync(new URL('./components/SystemUpdateControl.vue', import.meta.url), 'utf8')
  assert.match(control, /lazyPage\(\(\) => import\('\.\/SystemUpdateDialog\.vue'\)\)/)
  assert.ok(!staticComponents('./CloudApp.vue').some(file => file.endsWith('SystemUpdateDialog.vue')))
  assert.ok(!staticComponents('./LocalApp.vue').some(file => file.endsWith('SystemUpdateDialog.vue')))
})
test('the League of Legends dashboard, which the cloud never shows, is not part of the game card chunk', () => {
  assert.ok(!staticComponents('./components/GameCard.vue').includes('components/LolDashboard.vue'))
  assert.match(readFileSync(new URL('./components/GameCard.vue', import.meta.url), 'utf8'), /lazyPage\(\(\) => import\('\.\/LolDashboard\.vue'\)\)/)
})
test('a page whose chunk is gone after an update says so for any page, not only for game profiles', async t => {
  const Page = lazyPage(() => Promise.reject(new Error('Failed to fetch dynamically imported module')))
  const root = mount(t, Page); await tick(); await tick()
  assert.match(content(root), /界面已更新，请刷新页面后重试/)
  assert.doesNotMatch(content(root), /游戏档案/)
  assert.equal(nodes(root, 'button').length, 1)
})
