import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { nextTick } from 'vue'
import { mount, nodes, content } from './test-utils/vue.js'
import { lazyPage } from './lazy-page.js'

const staticComponents = file => [...readFileSync(new URL(file, import.meta.url), 'utf8').matchAll(/^import \w+ from '\.\/([\w/]+\.vue)'/gm)].map(match => match[1])
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }

test('the cloud app loads only the login form, overview, icons, shared menu, theme toggle and idle update control before its first paint', () => {
  assert.deepEqual(staticComponents('./CloudApp.vue').sort(), ['components/AppIcon.vue', 'components/GameIcon.vue', 'components/MenuSelect.vue', 'components/OverviewPage.vue', 'components/SiteLogin.vue', 'components/SystemUpdateControl.vue', 'components/ThemeToggle.vue'])
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

test('game-specific dashboards and guide catalogs load only when their game panel is shown',()=>{
  const eager=staticComponents('./components/GameCard.vue')
  for(const name of ['NteRolesPanel','NteAssetsPanel','NteGachaPanel','NteGuides','EndfieldDashboard','WuwaDashboard'])
    assert.ok(!eager.includes(`${name}.vue`),`${name} is still in every game first-load graph`)
})
test('Wuwa guides load on request and stay out of the roster chunk that QQ images reuse',()=>{
  for(const [file,names] of [['WuwaRoles',['WuwaGuide','WuwaGuideBrowser']],['WuwaCombat',['WuwaChallengeGuides']]]) {
    const source=readFileSync(new URL(`./components/${file}.vue`,import.meta.url),'utf8')
    for(const name of names) {
      assert.ok(!staticComponents(`./components/${file}.vue`).includes(`${name}.vue`),`${file} still imports ${name} eagerly`)
      assert.ok(source.includes(`const ${name} = lazyPage(() => import('./${name}.vue'))`),`${name} is not a lazy page`)
    }
  }
})
test('a failed page module offers recovery without claiming a new deployment', async t => {
  const Page = lazyPage(() => Promise.reject(new Error('Failed to fetch dynamically imported module')))
  const root = mount(t, Page); await tick(); await tick()
  assert.match(content(root), /页面模块加载失败/)
  assert.doesNotMatch(content(root), /界面已更新/)
  assert.doesNotMatch(content(root), /游戏档案/)
  assert.equal(nodes(root, 'button').length, 1)
})

test('a pending module shows loading after 200ms and a recoverable timeout after 15 seconds', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] })
  const Page = lazyPage(() => new Promise(() => {}))
  const root = mount(t, Page)
  t.mock.timers.tick(200); await tick()
  assert.match(content(root), /正在加载页面/)
  t.mock.timers.tick(14800); await tick()
  assert.match(content(root), /页面模块加载失败/)
  assert.ok(nodes(root, 'button').length)
})
