import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { computed, h, nextTick, provide, reactive } from 'vue'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
import { gameStyle } from '../dashboard.js'
import { theme } from '../theme.js'
import { officialGameIcons, officialGameIconFallbacks, officialGameBanners } from '../game-artwork.js'

const GameIcon = await loadVue(new URL('./GameIcon.vue', import.meta.url))

test('an exhausted icon gets only one delayed recovery attempt', async t => {
  t.mock.timers.enable({apis:['setTimeout']})
  const root=mount(t,GameIcon,{gameId:'nte'})
  for(let i=0;i<2;i++){nodes(root,'img')[0].props.onError();await nextTick()}
  assert.equal(nodes(root,'img').length,0)
  t.mock.timers.tick(1500);await nextTick()
  assert.equal(nodes(root,'img')[0]?.props.src,officialGameIcons.nte)
  for(let i=0;i<2;i++){nodes(root,'img')[0].props.onError();await nextTick()}
  t.mock.timers.tick(10000);await nextTick()
  assert.equal(nodes(root,'img').length,0)
})

test('theme changes retry the correct bundled icon without losing local artwork', async t => {
  t.after(()=>{theme.value='dark';delete globalThis.__LOCAL_GAME_ICONS__})
  const root=mount(t,GameIcon,{gameId:'endfield'})
  nodes(root,'img')[0].props.onError();await nextTick()
  nodes(root,'img')[0].props.onError();await nextTick()
  nodes(root,'img')[0].props.onError();await nextTick()
  assert.equal(nodes(root,'img').length,0)
  theme.value='light';await nextTick()
  assert.equal(nodes(root,'img')[0].props.src,officialGameIcons.endfield)
  nodes(root,'img')[0].props.onError();await nextTick()
  assert.equal(nodes(root,'img')[0].props.src,officialGameIconFallbacks.endfield[0])
  nodes(root,'img')[0].props.onError();await nextTick()
  assert.equal(nodes(root,'img')[0].props.src,gameStyle('endfield').iconLight)
  globalThis.__LOCAL_GAME_ICONS__={nte:'/local-game-icons/nte.jpg'}
  const local=mount(t,GameIcon,{gameId:'nte'})
  assert.equal(nodes(local,'img')[0].props.src,'/local-game-icons/nte.jpg')
  theme.value='dark';await nextTick()
  assert.equal(nodes(local,'img')[0].props.src,'/local-game-icons/nte.jpg')
})

test('local artwork overrides official artwork and failures reach the bundled icon', async t => {
  globalThis.__LOCAL_GAME_ICONS__ = { nte: '/local-game-icons/nte.jpg' }
  t.after(() => { delete globalThis.__LOCAL_GAME_ICONS__ })
  const root = mount(t, GameIcon, { gameId: 'nte' })
  assert.equal(nodes(root, 'img')[0].props.src, '/local-game-icons/nte.jpg')
  nodes(root, 'img')[0].props.onError()
  await nextTick()
  assert.equal(nodes(root, 'img')[0].props.src, officialGameIcons.nte)
  nodes(root, 'img')[0].props.onError()
  await nextTick()
  assert.equal(nodes(root, 'img')[0].props.src, gameStyle('nte').icon)
  nodes(root, 'img')[0].props.onError()
  await nextTick()
  assert.equal(nodes(root, 'img').length, 0)
})
test('each supported game records separate rights for official artwork and bundled fallback', () => {
  const sources = JSON.parse(readFileSync(new URL('../../public/game-icons/sources.json', import.meta.url)))
  assert.deepEqual(sources.map(item => item.game_id).sort(), ['endfield', 'nte', 'wuthering_waves'])
  for (const id of ['wuthering_waves', 'nte', 'endfield']) {
    const official = sources.find(item => item.game_id === id).official_icon
    assert.equal(official.url, officialGameIcons[id])
    assert.deepEqual(official.fallback_urls, officialGameIconFallbacks[id] || [])
    const banner = sources.find(item => item.game_id === id).official_banners
    assert.deepEqual(banner.urls, officialGameBanners[id])
    assert.match(banner.kind, /not a current-version/)
    assert.match(official.url, /^https:\/\//)
    assert.match(official.license, /not covered by the project GPL/)
    assert.equal(official.verified_at, id === 'nte' ? '2026-10-18' : '2026-10-17')
    assert.ok(official.owner && official.website && official.evidence)
    const src = gameStyle(id).icon
    assert.match(src, /^\/game-icons\//)
    assert.ok(readFileSync(new URL(`../../public${src}`, import.meta.url)).length > 500)
    assert.equal(sources.find(item => item.game_id === id).file, src.split('/').at(-1))
    assert.equal(sources.find(item => item.game_id === id).license, 'GPL-3.0-only')
    const light = gameStyle(id).iconLight
    assert.ok(readFileSync(new URL(`../../public${light}`, import.meta.url)).length > 500)
    assert.equal(sources.find(item => item.game_id === id).file_light, light.split('/').at(-1))
  }
  for (const file of ['nte.jpg', 'wuthering_waves.jpg', 'league_of_legends.svg', 'league_of_legends-mark.svg', 'league_of_legends-mark-light.svg']) {
    assert.equal(existsSync(new URL(`../../public/game-icons/${file}`, import.meta.url)), false)
  }
})
test('icon failure falls back to game mark and a changed game retries its own icon', async (t) => {
  const props = reactive({ gameId: 'nte', name: '异环' })
  const root = mount(t, GameIcon, props)
  assert.equal(nodes(root, 'img')[0].props.alt, '异环图标')
  assert.equal(nodes(root, 'img')[0].props.src, officialGameIcons.nte)
  assert.equal(nodes(root, 'img')[0].props.referrerpolicy, 'no-referrer')
  nodes(root, 'img')[0].props.onError()
  await nextTick()
  nodes(root, 'img')[0].props.onError()
  await nextTick()
  assert.equal(nodes(root, 'img').length, 0)
  assert.match(content(root), /异/)
  props.gameId = 'wuthering_waves'
  await nextTick()
  assert.equal(nodes(root, 'img')[0].props.src, officialGameIcons.wuthering_waves)
})
test('in image mode the icon is the game mark, never an image request the QQ renderer would abort', async t => {
  for (const mode of [true, computed(() => true)]) {
    const root = mount(t, { setup() { provide('wuwaImageMode', mode); return () => h(GameIcon, { gameId: 'nte', name: '异环' }) } })
    assert.equal(nodes(root, 'img').length, 0)
    assert.match(content(root), new RegExp(gameStyle('nte').mark))
  }
  assert.equal(nodes(mount(t, GameIcon, { gameId: 'nte' }), 'img').length, 1, 'the website still loads official artwork')
})


test('a healthy bundled fallback does not prevent one official-image recovery',async t=>{
 t.mock.timers.enable({apis:['setTimeout']})
 const root=mount(t,GameIcon,{gameId:'nte'})
 nodes(root,'img')[0].props.onError();await nextTick()
 assert.equal(nodes(root,'img')[0].props.src,gameStyle('nte').icon)
 t.mock.timers.tick(1500);await nextTick()
 assert.equal(nodes(root,'img')[0].props.src,officialGameIcons.nte)
 nodes(root,'img')[0].props.onError();await nextTick()
 t.mock.timers.tick(10000);await nextTick()
 assert.equal(nodes(root,'img')[0].props.src,gameStyle('nte').icon)
})
