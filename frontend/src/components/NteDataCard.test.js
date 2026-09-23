import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'

const NteDataCard = await loadVue(new URL('./NteDataCard.vue', import.meta.url))
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
  const zero = content(card(t, 'stamina', { current: 100, maximum: 240, weekly_remaining: 0 }))
  assert.match(zero, /周本剩余 0/)
  assert.doesNotMatch(zero, /周本剩余 未提供/)
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

test('all capabilities distinguish missing snapshots from legacy schemas and show freshness', (t) => {
  for (const capability of ['account', 'stamina', 'progress', 'exploration', 'record']) {
    const empty = mount(t, NteDataCard, { capability, snap: null })
    assert.match(content(empty), /暂无数据.*登录.*刷新/)
    const legacy = mount(t, NteDataCard, { capability, snap: { payload: { raw: true }, fetched_at: '2026-09-14T10:00:00+08:00', stale: true } })
    assert.match(content(legacy), /数据格式已更新，请刷新/)
    assert.match(content(legacy), /数据可能过期/)
    assert.match(content(legacy), capability === 'stamina' ? /读取于/ : /更新于/)
  }
})

test('stamina reports the actual source read time rather than the later cache-save time', (t) => {
  const root = mount(t, NteDataCard, { capability: 'stamina', snap: {
    payload: { schema_version: 1, current: 0, maximum: 320, updated_at: '2026-09-15T00:50:00+08:00' },
    fetched_at: '2026-09-15T00:50:25+08:00',
  } })
  assert.match(content(root), /0 \/ 320/)
  assert.match(content(root), /读取于 2026-09-15 00:50/)
  assert.match(content(root), /社区数据可能延迟/)
})

test('empty normalized collections show no-data rather than an empty card', (t) => {
  assert.match(content(card(t, 'exploration', { areas: [] })), /暂无数据/)
  assert.match(content(card(t, 'record', { cards: [] })), /暂无社区名片/)
})

test('GameCard routes only NTE private capabilities to the native cards', async (t) => {
  const GameCard = await loadVue(new URL('./GameCard.vue', import.meta.url))
  const supplied = snap({ total_draws: 0, total_s: 0, pools: [], cards: [] })
  const root = mount(t, GameCard, { game: { game_id: 'nte', display_name: '异环', capabilities: ['gacha', 'record', 'events', 'announcement'], credentials_configured: true },
    externalSnapshots: { gacha: supplied, record: supplied, announcement: supplied } })
  await nextTick()
  assert.match(content(root), /抽卡统计/)
  assert.match(content(root), /社区名片/)
  assert.match(content(root), /公告/)
  assert.doesNotMatch(content(root), /敬请期待/)
  const other = mount(t, GameCard, { game: { game_id: 'other', display_name: '其他', capabilities: ['gacha'], credentials_configured: true }, externalSnapshots: {} })
  assert.match(content(other), /敬请期待/)
})

test('managed game detail uses supplied snapshots and tabs without issuing duplicate reads', async (t) => {
  const GameCard = await loadVue(new URL('./GameCard.vue', import.meta.url))
  let reads = 0
  t.mock.method(globalThis, 'fetch', async () => { reads++; throw Error('must use supplied snapshots') })
  const root = mount(t, GameCard, { game: { game_id: 'nte', display_name: '异环', capabilities: ['account', 'gacha', 'events', 'announcement'], credentials_configured: true },
    externalSnapshots: { account: snap({ nickname: '管理态账号' }), gacha: snap({ total_draws: 80, total_s: 1, pools: [] }) }, initialSection: 'overview' })
  await new Promise(setImmediate)
  await nextTick()
  assert.equal(reads, 0)
  assert.match(content(root), /管理态账号/)
  assert.doesNotMatch(content(root), /统计抽数/)
  const tab = nodes(root, 'button').find(n => content(n) === '抽卡统计')
  assert.ok(tab)
  tab.props.onClick(); await nextTick()
  assert.match(content(root), /近期抽卡记录/)
  assert.match(content(root), /暂无卡池统计/)
  assert.equal(reads, 0)
  assert.match(content(root), /活动日历/)
})

test('news capability displays its own heading, freshness and only safe source links', async (t) => {
  const AnnouncementList = await loadVue(new URL('./AnnouncementList.vue', import.meta.url))
  const root = mount(t, AnnouncementList, { capability: 'news', snap: { stale: true, fetched_at: '2026-09-14T12:00:00Z', payload: [
    { title: '合法资讯', url: 'https://example.com/news', published_at: '2026-09-14T00:00:00Z' },
    { title: '不安全链接', url: 'javascript:alert(1)' },
  ] } })
  assert.match(content(root), /资讯.*数据可能过期/)
  assert.deepEqual(nodes(root, 'a').map(n => n.props.href), ['https://example.com/news'])
})
