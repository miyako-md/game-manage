import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRenderer, nextTick, h, reactive } from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'

const modules = new Map()
async function loadVue(url) {
  if (modules.has(url.href)) return modules.get(url.href)
  const { descriptor } = parse(readFileSync(url, 'utf8'))
  let code = compileScript(descriptor, { id: url.pathname, inlineTemplate: true }).content
  const imports = [...code.matchAll(/from ['"]([^'"]+)['"]/g)]
  for (const match of imports) {
    const name = match[1]
    if (name.endsWith('.vue')) {
      const child = new URL(name, url)
      await loadVue(child)
      code = code.replaceAll(`'${name}'`, `'${modules.get(child.href + ':url')}'`)
    } else {
      code = code.replaceAll(`'${name}'`, `'${name.startsWith('.') ? new URL(name, url).href : import.meta.resolve(name)}'`)
      code = code.replaceAll(`"${name}"`, `"${name.startsWith('.') ? new URL(name, url).href : import.meta.resolve(name)}"`)
    }
  }
  const encoded = `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
  modules.set(url.href + ':url', encoded)
  const component = (await import(encoded)).default
  modules.set(url.href, component)
  return component
}
const NteDataCard = await loadVue(new URL('./NteDataCard.vue', import.meta.url))

function mount(t, component, props) {
  const node = (type, text = '') => ({ type, text, props: {}, children: [], parent: null })
  const renderer = createRenderer({
    createElement: (type) => node(type), createText: (text) => node('#text', text),
    createComment: () => node('#comment'), setText: (n, text) => { n.text = text },
    setElementText: (n, text) => { n.text = text; n.children = [] },
    patchProp: (n, key, _old, value) => { n.props[key] = value },
    insert(n, parent, anchor) {
      if (n.parent) n.parent.children.splice(n.parent.children.indexOf(n), 1)
      const index = anchor ? parent.children.indexOf(anchor) : -1
      parent.children.splice(index < 0 ? parent.children.length : index, 0, n)
      n.parent = parent
    },
    remove(n) { n.parent?.children.splice(n.parent.children.indexOf(n), 1) },
    parentNode: (n) => n.parent,
    nextSibling: (n) => n.parent?.children[n.parent.children.indexOf(n) + 1],
  })
  const root = node('root')
  const app = renderer.createApp({ render: () => h(component, props) })
  app.mount(root)
  t.after(() => app.unmount())
  return root
}
const content = (n) => [n.text, ...n.children.map(content)].filter(Boolean).join(' ').replace(/\s+/g, ' ')
const nodes = (n, type) => [...(n.type === type ? [n] : []), ...n.children.flatMap((child) => nodes(child, type))]
const snap = (payload) => ({ payload: { schema_version: 1, ...payload }, fetched_at: '2026-09-14T10:00:00+08:00', stale: false })
const card = (t, capability, payload) => mount(t, NteDataCard, { capability, snap: snap(payload) })

test('account displays identity and owned assets without converting unknown counts into zero', (t) => {
  const root = card(t, 'account', { nickname: '零', role_id: '123', level: 0, server_name: '亚服', world_level: 2,
    tycoon_level: 3, active_days: 4, character_count: 5, achievement_count: 0, achievement_total: 99,
    house_count: null, house_total: 8, vehicle_count: 0, vehicle_total: null })
  const text = content(root)
  for (const expected of ['零', '123', '亚服', '角色数 5', '成就 0 / 99', '房产 未知 / 8', '载具 0 / 未知']) assert.ok(text.includes(expected), expected)
})

test('stamina separates city stamina, daily activity and explicitly remaining weekly attempts', (t) => {
  const text = content(card(t, 'stamina', { current: 0, maximum: 240, city_current: null, city_maximum: 120, daily_activity: 0, weekly_remaining: 0, expected_full_at: null }))
  for (const expected of ['本性像素', '0 / 240', '都市活力', '未知 / 120', '日常活跃', '0 / 100', '周本剩余 0']) assert.ok(text.includes(expected), expected)
  assert.doesNotMatch(text, /回满|重置|已完成/)
})

test('missing weekly attempts are identified as not supplied rather than zero', (t) => {
  for (const weekly_remaining of [null, undefined]) {
    const text = content(card(t, 'stamina', { current: 100, maximum: 240, weekly_remaining }))
    assert.match(text, /周本剩余 未提供/)
    assert.doesNotMatch(text, /周本剩余 (0|未知)/)
  }
})

test('roles use native quality and awakening, preserve experience, and offer accessible full details', (t) => {
  const root = card(t, 'roles', { entries: [{ id: '1', name: '薄荷', level: 45, quality: 'S', element: '灵', awaken_level: 0,
    mix_level: 1, affinity_exp: 650, icon_url: null, weapon: { name: '弧光', level: 30, quality: 'A', mix_level: 2 },
    properties: [{ name: '攻击力', value: '320' }], skills: [{ name: '战技一', level: 5 }], city_skills: [{ name: '城区一', level: 2 }] },
  { id: '2', name: '白藏', quality: 'A', properties: [], skills: [], city_skills: [] },
  { id: '3', name: '未知者', quality: null, properties: [], skills: [], city_skills: [] }] })
  const text = content(root)
  for (const expected of ['角色总数 3', 'S级 1', 'A级 1', '薄荷', '灵', '觉醒 0', '混频 1', '羁遇累计经验 650']) assert.ok(text.includes(expected), expected)
  assert.doesNotMatch(text, /6链|五星|满级|羁遇等级/)
  assert.equal(nodes(root, 'details').length, 3)
  const detail = nodes(root, 'details')[0]
  assert.match(content(nodes(detail, 'summary')[0]), /薄荷.*详情/)
  for (const expected of ['攻击力', '320', '战技一', '城区一', '弧光', '混频 2']) assert.ok(content(detail).includes(expected), expected)
})

test('achievement card renders medals and counts under achievement progress', (t) => {
  const text = content(card(t, 'progress', { completed: 5, total: 20, bronze: 0, silver: 2, gold: null, categories: [{ id: 'x', name: '都市', current: 1, total: 4 }] }))
  for (const expected of ['成就进度', '5 / 20', '铜 0', '银 2', '金 未知', '都市', '1 / 4']) assert.ok(text.includes(expected), expected)
  assert.doesNotMatch(text, /重置/)
})

test('exploration only derives a percentage from known counts and a positive denominator', (t) => {
  const root = card(t, 'exploration', { areas: [
    { id: 'a', name: '新赫兰', current: 1, total: 4, details: [{ id: '1', name: '宝箱', current: null, total: 10 }] },
    { id: 'b', name: '未解锁', current: null, total: 5, details: [] },
    { id: 'c', name: '真实零', current: 0, total: 5, details: [] },
    { id: 'd', name: '无分母', current: 2, total: 0, details: [] },
  ] })
  const text = content(root)
  assert.match(text, /新赫兰.*1 \/ 4.*25%/)
  assert.match(text, /宝箱.*未知 \/ 10/)
  assert.match(text, /真实零.*0 \/ 5.*0%/)
  assert.match(text, /无分母.*2 \/ 0/)
  assert.equal(nodes(root, 'progress').length, 2)
  assert.equal(nodes(root, 'progress')[0].props.value, 1)
  assert.equal(nodes(root, 'progress')[0].props.max, 4)
  assert.doesNotMatch(text, /NaN|Infinity/)
})

test('gacha shows statistical window and S results without inventing current pity', (t) => {
  const root = card(t, 'gacha', { role_id: '123', nickname: '零', total_draws: 120, total_s: 2, pools: [
    { name: '常驻池', total_draws: 120, s_count: 2, average: '60.0', percentile: '70%', guarantee: 80,
      details: [{ item_id: '101', name: '薄荷', pity: 60, obtained_at: '2026-09-01T00:00:00Z' }] },
  ] })
  const text = content(root)
  for (const expected of ['社区统计窗口', '仅列已出S明细', '不含当前垫抽', '不代表完整历史', '常驻池', '120', '平均出S抽数 60.0', '薄荷', '第 60 抽出S', '获得时间（北京时间）', '2026/09/01 08:00:00']) assert.ok(text.includes(expected), expected)
  assert.doesNotMatch(text, /当前保底|胜率/)
})

test('excess exploration retains source counts while capping completion at the target', (t) => {
  const text = content(card(t, 'exploration', { areas: [
    { name: '都市', current: 1768, total: 1500, details: [{ name: '支线', current: 4, total: 3 }] },
    { name: '恰好完成', current: 3, total: 3, details: [] },
  ] }))
  assert.match(text, /都市 1768 \/ 1500 · 100%.*已达目标/)
  assert.match(text, /支线 4 \/ 3 · 100%.*已达目标/)
  assert.equal((text.match(/已达目标/g) || []).length, 2)
  assert.doesNotMatch(text, /118%|133%/)
})

test('gacha times use Beijing dates across day boundaries and safely label missing or invalid times', (t) => {
  for (const [obtained_at, expected] of [
    ['2026-09-01T18:15:30Z', '2026/09/02 02:15:30'],
    ['2026-09-01T08:10:00+08:00', '2026/09/01 08:10:00'],
    ['2026-09-01 08:10', '2026/09/01 08:10:00'],
    [null, '未提供'], [undefined, '未提供'], ['', '未提供'], ['invalid', '未提供'],
  ]) {
    const text = content(card(t, 'gacha', { pools: [{ name: '池', details: [{ name: '角色', pity: 1, obtained_at }] }] }))
    assert.ok(text.includes(`获得时间（北京时间） ${expected}`), text)
    assert.doesNotMatch(text, /Invalid Date|undefined|null|T18:|T08:|\+08:00/)
  }
})

test('community cards only render safe http links and never interpolate unsafe code URLs', (t) => {
  const root = card(t, 'record', { cards: [
    { game_name: '异环', role_id: '123', nickname: '零', level: 0, server_name: '亚服', url: 'https://example.com/card' },
    { nickname: '恶意', url: 'javascript:alert(1)' }, { nickname: '数据', url: 'data:text/html,bad' },
    { nickname: '相对', url: '//example.com' },
  ] })
  assert.match(content(root), /社区名片.*异环.*零.*亚服/)
  const anchors = nodes(root, 'a')
  assert.equal(anchors.length, 1)
  assert.equal(anchors[0].props.href, 'https://example.com/card')
  assert.match(anchors[0].props.rel, /noopener/)
  assert.doesNotMatch(content(root), /对局战绩/)
})

test('unsafe portraits are omitted and official https portraits remain optional', (t) => {
  const root = card(t, 'roles', { entries: [
    { name: '一', icon_url: 'javascript:alert(1)' }, { name: '二', icon_url: 'data:image/png;base64,abc' },
    { name: '三', icon_url: 'https://cdn.example.com/official.png' },
  ] })
  assert.equal(nodes(root, 'img').length, 1)
  assert.equal(nodes(root, 'img')[0].props.alt, '三')
})

test('failed images fall back without retry loops and new portrait URLs can still load', async (t) => {
  const props = reactive({ capability: 'roles', snap: snap({ entries: [{ name: '薄荷', icon_url: 'https://cdn.example.com/failed.png' }] }) })
  const root = mount(t, NteDataCard, props)
  const image = nodes(root, 'img')[0]
  assert.equal(typeof image.props.onError, 'function')
  image.props.onError({ currentTarget: { src: image.props.src } })
  await nextTick()
  assert.equal(nodes(root, 'img').length, 0)
  assert.ok(nodes(root, 'span').some((node) => node.props.class?.includes('avatar-empty') && content(node) === '薄'))
  props.snap.payload.entries[0].level = 2
  await nextTick()
  assert.equal(nodes(root, 'img').length, 0)
  props.snap.payload.entries[0].icon_url = 'https://cdn.example.com/new.png'
  await nextTick()
  assert.equal(nodes(root, 'img')[0].props.src, 'https://cdn.example.com/new.png')
  props.snap.payload.entries[0].icon_url = 'https://cdn.example.com/failed.png'
  await nextTick()
  assert.equal(nodes(root, 'img').length, 0)
})

test('all capabilities distinguish missing snapshots from legacy schemas and show freshness', (t) => {
  for (const capability of ['account', 'stamina', 'roles', 'progress', 'exploration', 'gacha', 'record']) {
    const empty = mount(t, NteDataCard, { capability, snap: null })
    assert.match(content(empty), /暂无数据.*登录.*刷新/)
    const legacy = mount(t, NteDataCard, { capability, snap: { payload: { raw: true }, fetched_at: '2026-09-14T10:00:00+08:00', stale: true } })
    assert.match(content(legacy), /数据格式已更新，请刷新/)
    assert.match(content(legacy), /数据可能过期/)
    assert.match(content(legacy), /更新于/)
  }
})

test('empty normalized collections show no-data rather than an empty card', (t) => {
  for (const [cap, payload] of [['roles', { entries: [] }], ['exploration', { areas: [] }]]) {
    assert.match(content(card(t, cap, payload)), /暂无数据/)
  }
  assert.match(content(card(t, 'record', { cards: [] })), /暂无社区名片/)
  const text = content(card(t, 'roles', { entries: [{ quality: 'S' }, { quality: 'A' }, { quality: 'B' }, { quality: null }, { quality: 'SS' }] }))
  assert.match(text, /角色总数 5.*S级 1.*A级 1/)
})

test('GameCard routes only NTE private capabilities to the native cards', async (t) => {
  const GameCard = await loadVue(new URL('./GameCard.vue', import.meta.url))
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify(snap({ total_draws: 0, total_s: 0, pools: [], cards: [] }))))
  const root = mount(t, GameCard, { game: { game_id: 'nte', display_name: '异环', capabilities: ['gacha', 'record', 'events', 'announcement'], credentials_configured: true } })
  await new Promise(setImmediate)
  await nextTick()
  assert.match(content(root), /抽卡统计/)
  assert.match(content(root), /社区名片/)
  assert.match(content(root), /公告/)
  assert.doesNotMatch(content(root), /敬请期待/)
  const other = mount(t, GameCard, { game: { game_id: 'other', display_name: '其他', capabilities: ['gacha'], credentials_configured: true } })
  assert.match(content(other), /敬请期待/)
})
