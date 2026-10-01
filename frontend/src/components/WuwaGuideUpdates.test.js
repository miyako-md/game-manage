import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
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
