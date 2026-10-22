import test from 'node:test'
import assert from 'node:assert/strict'
import { computed, defineComponent, h, nextTick, provide, reactive } from 'vue'
import { configureHttpClient } from '../http-client.js'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'

const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }
const entry = { id: '1555005846752059392', title: 'V3.7心培养攻略一图流', author: '轩儿Xuaner', version: '3.7', kind: 'article', url: 'https://www.kurobbs.com/forum/post/1555005846752059392', published_at: '2026-09-30T15:00:00Z' }
const result = (candidates = []) => ({ character_id: '1311', name: '心', attribute: '导电', candidates, checked_at: '2026-10-01T04:00:00Z' })

test('checking a new character installs five source-bound recommendations and restores them from cache', async t => {
  const guide = { id:'1311',name:'心',attribute:'导电',sourceId:entry.id,reviewedAt:'2026-10-01',
    sources:[{...entry,publishedAt:entry.published_at}],sections:[
      {key:'weapons',text:'玉阙玄华',status:'reviewed',sourceId:entry.id,locator:'第 5 张图'},
      {key:'teams',text:'心／导电漂泊者／穗穗',status:'reviewed',sourceId:entry.id,locator:'第 6 张图'},
      {key:'echo_sets',text:'衔梦照世之心五件套',status:'reviewed',sourceId:entry.id,locator:'第 2 张图'},
      {key:'echo_stats',text:'同奏一攻一属，电磁双攻',status:'reviewed',sourceId:entry.id,locator:'第 2 张图'},
      {key:'skill_priority',text:'共鸣回路＞共鸣解放＞变奏技能＞常态攻击＞共鸣技能',status:'reviewed',sourceId:entry.id,locator:'第 3 张图'},
    ] }
  t.mock.method(globalThis,'fetch',async()=>({ok:true,json:async()=>({...result([entry]),active_guide:guide})}))
  const Guide = await loadVue(new URL('./WuwaGuide.vue',import.meta.url))
  const root = mount(t,Guide,{characterId:'1311',characterName:'心',attribute:'导电'})
  await tick()
  assert.match(content(root),/5\/5 项已核对原帖/)
  assert.match(content(root),/玉阙玄华/)
  assert.match(content(root),/同奏一攻一属，电磁双攻/)
  assert.doesNotMatch(content(root),/此角色形态暂未收录攻略/)
})

test('new characters can check anonymous sources without overwriting reviewed advice', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options })
    return { ok: true, json: async () => options.method === 'POST' ? result([entry]) : { ...result(), checked_at: null } }
  })
  const Guide = await loadVue(new URL('./WuwaGuide.vue', import.meta.url))
  const root = mount(t, Guide, { characterId: '1311', characterName: '心', attribute: '导电' })
  await tick()
  assert.match(content(root), /此角色形态暂未收录攻略/)
  nodes(root, 'button').find(n => content(n) === '检查更新').props.onClick()
  await tick()
  assert.match(content(root), /轩儿Xuaner/)
  assert.match(content(root), /未收录/)
  assert.match(content(root), /待核查/)
  assert.doesNotMatch(content(root), /5\/5 项已核对/)
  assert.equal(calls[1].options.headers['X-Game-Assistant'], '1')
  assert.equal(JSON.parse(calls[1].options.body).name, '心')
})

test('failed checks keep cached candidates and are not presented as no updates', async t => {
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    if (options.method === 'POST') throw new Error('network')
    return { ok: true, json: async () => result([entry]) }
  })
  const Component = await loadVue(new URL('./WuwaGuideUpdates.vue', import.meta.url))
  const root = mount(t, Component, { characterId: '1311', name: '心', attribute: '导电' })
  await tick()
  nodes(root, 'button').find(n => content(n) === '检查更新').props.onClick()
  await tick()
  assert.match(content(root), /轩儿Xuaner/)
  assert.match(content(root), /检查失败/)
  assert.doesNotMatch(content(root), /没有发现/)
})

test('switching roles ignores late responses and known sources are distinguished', async t => {
  let finish
  t.mock.method(globalThis, 'fetch', (_, options) => options.method === 'POST'
    ? new Promise(resolve => { finish = resolve })
    : Promise.resolve({ ok: true, json: async () => result([entry]) }))
  const Component = await loadVue(new URL('./WuwaGuideUpdates.vue', import.meta.url))
  const props = reactive({ characterId: '1311', name: '心', attribute: '导电', sources: [{ id: entry.id }] })
  const root = mount(t, Component, props)
  await tick()
  assert.match(content(root), /已收录来源/)
  nodes(root, 'button').find(n => content(n) === '检查更新').props.onClick()
  await tick()
  props.characterId = '1102'; props.name = '散华'; props.attribute = '冷凝'
  await tick()
  finish({ ok: true, json: async () => result([{ ...entry, title: 'LATE_XIN' }]) })
  await tick()
  assert.doesNotMatch(content(root), /LATE_XIN|轩儿Xuaner/)
})

test('the cloud shows the check to administrators only and reads through the public route', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const calls = []
  t.mock.method(globalThis, 'fetch', async url => { calls.push(String(url)); return { ok: true, json: async () => result([entry]) } })
  const Guide = await loadVue(new URL('./WuwaGuide.vue', import.meta.url))
  const host = isAdmin => defineComponent({ setup() {
    provide('cloudPermissions', computed(() => ({ isAdmin })))
    return () => h(Guide, { characterId: '1311', characterName: '心', attribute: '导电' })
  } })
  const admin = mount(t, host(true), {})
  await tick()
  assert.ok(nodes(admin, 'button').some(n => content(n) === '检查更新'))
  assert.ok(calls.some(url => url.startsWith('/api/public/wuwa/guides/updates?')))
  const member = mount(t, host(false), {})
  await tick()
  assert.match(content(member), /社区攻略更新/)
  assert.ok(!nodes(member, 'button').some(n => content(n) === '检查更新'))
})

test('the background job state is shown and a busy check keeps the cached result without an error', async t => {
  const calls = []
  let background = { running: true, last_run_at: null }
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    calls.push(options.method || 'GET')
    return { ok: true, json: async () => options.method === 'POST' ? { ...result([entry]), background, busy: true } : { ...result([entry]), background } }
  })
  const Component = await loadVue(new URL('./WuwaGuideUpdates.vue', import.meta.url))
  const root = mount(t, Component, { characterId: '1311', name: '心', attribute: '导电' })
  await tick()
  assert.match(content(root), /后台检查进行中，结果会自动写入/)
  nodes(root, 'button').find(n => content(n) === '检查更新').props.onClick()
  await tick()
  assert.deepEqual(calls, ['GET', 'POST'])
  assert.match(content(root), /本次未重新检查，显示已有结果/)
  assert.match(content(root), /轩儿Xuaner/)
  assert.doesNotMatch(content(root), /检查失败/)
  background = { running: false, last_run_at: '2026-10-21T21:40:00+00:00' }
  const idle = mount(t, Component, { characterId: '1311', name: '心', attribute: '导电' })
  await tick()
  assert.match(content(idle), /后台检查于 2026\/10\/22 05:40:00（北京时间）/)
  assert.doesNotMatch(content(idle), /后台检查进行中/)
})

test('a cached check stored under another spelling of the same role ID is still shown', async t => {
  const guide = { id: '1311', name: '心', attribute: '', sourceId: entry.id, sources: [{ ...entry }], sections: [{ key: 'weapons', text: '示例武器', status: 'extracted', sourceId: entry.id }] }
  t.mock.method(globalThis, 'fetch', async () => ({ ok: true, json: async () => ({ ...result([entry]), attribute: '', active_guide: guide }) }))
  const Component = await loadVue(new URL('./WuwaGuideUpdates.vue', import.meta.url))
  const seen = []
  const root = mount(t, Component, { characterId: '1311', name: '心', attribute: '导电', onGuide: value => seen.push(value) })
  await tick()
  assert.match(content(root), /轩儿Xuaner/)
  assert.equal(seen.length, 1)
  assert.doesNotMatch(content(root), /检查失败/)
})
