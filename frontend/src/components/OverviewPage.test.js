import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'

const Overview = await loadVue(new URL('./OverviewPage.vue', import.meta.url))
const now = Date.parse('2026-10-17T12:00:00+08:00')
const wuwa = { game_id: 'wuthering_waves', display_name: '鸣潮', capabilities: ['stamina', 'roles', 'events'], credentials_configured: true }
const role = (name, level, icon = true) => ({ role_id: name, name, level, icon_url: icon ? `https://web-static.kurobbs.com/r${level}.png` : '' })
const byClass = (root, name) => {
  const walk = n => [...(String(n.props.class ?? '').split(/\s+/).includes(name) ? [n] : []), ...n.children.flatMap(walk)]
  return walk(root)
}

test('game cards show the five highest-level pictured roles and the whole roster count', t => {
  const roles = [role('甲', 60), role('乙', 90), role('丙', 70), role('丁', 80, false), role('戊', 50), role('己', 40), role('庚', 85)]
  const root = mount(t, Overview, { games: [wuwa], now, snapshots: { wuthering_waves: { roles: { payload: roles } } } })
  const faces = nodes(byClass(root, 'roster-faces')[0], 'img').map(img => img.props.src)
  assert.deepEqual(faces, [90, 85, 70, 60, 50].map(level => `https://web-static.kurobbs.com/r${level}.png`))
  assert.match(content(byClass(root, 'summary-roster')[0]), /7 名角色/)
  const none = mount(t, Overview, { games: [wuwa], now, snapshots: { wuthering_waves: { roles: { payload: [role('甲', 60, false)] } } } })
  assert.equal(byClass(none, 'summary-roster').length, 0, 'no row without a picture')
})

test('roster pictures retry only the same role avatar and keep the real roster count', async t => {
  const root = mount(t, Overview, { games: [wuwa], now, snapshots: { wuthering_waves: { roles: { payload: [
    { role_id: 'a', name: '角色甲', level: 90, icon_url: 'https://example.com/missing.png', avatar_url: 'https://example.com/avatar.png' },
  ] } } } })
  const picture = () => nodes(byClass(root, 'roster-faces')[0], 'img')[0]
  picture().props.onError(); await nextTick()
  assert.equal(picture().props.src, 'https://example.com/avatar.png')
  assert.match(content(byClass(root, 'summary-roster')[0]), /1 名角色/)
  picture().props.onError(); await nextTick()
  assert.equal(byClass(root, 'summary-roster').length, 0)
})

test('the first deadline leads, and the week chart counts deadlines per Beijing day', t => {
  const events = [
    { name: '明日截止', start_at: '2026-10-10 10:00', end_at: '2026-10-18 03:59', category: '限时活动' },
    { name: '今晚截止', start_at: '2026-10-12 10:00', end_at: '2026-10-17 23:59', category: '限时活动' },
    { name: '下月截止', start_at: '2026-10-12 10:00', end_at: '2026-11-20 03:59' },
  ]
  const root = mount(t, Overview, { games: [wuwa], now, snapshots: { wuthering_waves: { events: { payload: events } } } })
  assert.match(content(byClass(root, 'ov-next')[0]), /最近截止.*今晚截止.*1.*天后结束/)
  const bars = nodes(byClass(root, 'bar-chart')[0], 'li').map(content)
  assert.equal(bars.length, 7)
  assert.match(bars[0], /今天/); assert.match(bars[0], /1 项/)
  assert.match(bars[1], /明天/); assert.match(bars[1], /1 项/)
  assert.ok(bars.slice(2).every(bar => /0 项/.test(bar)), 'events beyond the week are not counted')
  assert.match(content(byClass(root, 'ov-stats')[0]), /3.*进行中的活动.*2.*3 天内截止/)
})

test('deadline range switching preserves the next event and counts all dates without zero-value bars', async t => {
  const events = [
    { name: '最近活动', start_at: '2026-10-10 10:00', end_at: '2026-10-18 03:59' },
    { name: '下月活动', start_at: '2026-10-10 10:00', end_at: '2026-11-05 03:59' },
  ]
  const root = mount(t, Overview, { games: [wuwa], now, snapshots: { wuthering_waves: { events: { payload: events } } } })
  const chart = () => byClass(root, 'bar-chart')[0]
  const next = content(byClass(root, 'ov-next')[0])
  assert.match(content(byClass(root, 'chart-summary')[0]), /1 项 7 天内结束/)
  assert.equal(byClass(chart(), 'bar-fill').length, 1)
  nodes(root, 'button').find(button => content(button) === '30 天').props.onClick()
  await nextTick()
  assert.match(content(byClass(root, 'chart-summary')[0]), /2 项 30 天内结束/)
  assert.equal(byClass(chart(), 'bar-col').length, 30)
  assert.equal(byClass(chart(), 'bar-fill').length, 2)
  assert.equal(content(byClass(root, 'ov-next')[0]), next)
  nodes(root, 'button').find(button => content(button) === '7 天').props.onClick()
  await nextTick()
  assert.equal(byClass(chart(), 'bar-col').length, 7)
  assert.equal(byClass(chart(), 'bar-fill').length, 1)
})

test('daily rows share the rounded gauge and keep empty and done states distinct', t => {
  const root = mount(t, Overview, { games: [wuwa], now, snapshots: { wuthering_waves: { progress: { payload: [
    { name: '活跃度', cur: 50, total: 100 },
    { name: '周常', cur: 0, total: 3, refresh_at: '2026-10-19 04:00' },
    { name: '本周任务', cur: 3, total: 3, refresh_at: '2026-10-19 04:00' },
  ] } } } })
  const marks = byClass(root, 'task-mark')
  assert.equal(marks.length, 3)
  assert.equal(byClass(marks[0], 'ring-value')[0].props['stroke-linecap'], 'round')
  assert.equal(byClass(marks[1], 'ring-value').length, 0)
  assert.equal(byClass(marks[2], 'ring-gauge').length, 0, 'completed task keeps its check')
  assert.deepEqual(byClass(root, 'task-value').map(content), ['50/100 ，未完成', '0/3 ，未完成', '3/3 ，已完成'])
})


test('a date-only deadline counts on its stated day and shows no invented clock time', t => {
  const fixed = Date.parse('2026-10-20T12:00:00+08:00')
  const root = mount(t, Overview, { games: [wuwa], now: fixed, snapshots: { wuthering_waves: { events: { payload: [
    { name: '整日活动', start_date: '2026-10-19', end_date: '2026-10-21', end_precision: 'day' },
  ] } } } })
  assert.match(content(byClass(root, 'ov-deadlines')[0]), /1 项 7 天内结束/)
  assert.match(content(byClass(root, 'ov-next')[0]), /2026-10-21 截止/)
  assert.doesNotMatch(content(byClass(root, 'ov-next')[0]), /2026-10-22|00:00/)
})


test('expired daily completion keeps its old count with an explicit unconfirmed state', t => {
  const root = mount(t, Overview, { games: [wuwa], now, snapshots: { wuthering_waves: { progress: {
    stale: true, state: 'error', fetched_at: '2026-10-16T23:00:00+08:00',
    payload: [{ name: '活跃度', cur: 100, total: 100, refresh_at: '2026-10-17T04:00:00+08:00' }],
  } } } })
  const tasks = byClass(root, 'ov-tasks')[0]
  assert.match(content(tasks), /0 \/1 已确认完成/)
  assert.match(content(tasks), /待更新，当前周期未确认.*100\/100/)
  assert.equal(byClass(tasks, 'task')[0].props.class.includes('done'), false)
})

test('only administrators see 采集与回补; its progress ends by re-reading the overview', async t => {
  const { configureHttpClient } = await import('../http-client.js')
  const { COLLECT_POLL_MS } = await import('../cloud-collect.js')
  const button = root => nodes(root, 'button').find(n => /采集与回补|采集中/.test(content(n)))
  assert.equal(button(mount(t, Overview, { games: [wuwa], now })), undefined)
  assert.equal(button(mount(t, Overview, { games: [wuwa], now, isAdmin: false })), undefined)
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] })
  let finished = false
  t.mock.method(globalThis, 'fetch', async (path, options) => new Response(JSON.stringify(
    path.endsWith('/csrf') ? { csrf_token: 'fixture' }
      : options.method === 'POST' ? { games: [{ game_id: 'wuthering_waves', state: 'queued', job_id: 'a', generation: 0 }], private_refresh: { requested: 2, skipped: 0 } }
      : { games: [{ game_id: 'wuthering_waves', queue_state: finished ? 'idle' : 'running', generation: finished ? 1 : 0, outcome: finished ? { state: 'failed', bilibili: 'ok', failed: ['announcement'] } : null }] })))
  let refreshes = 0
  const root = mount(t, Overview, { games: [], now, isAdmin: true, onRefresh: () => refreshes++ })
  assert.equal(button(root).props.disabled, false, 'collection is global, not tied to the admin having game accounts')
  await button(root).props.onClick()
  for (let i = 0; i < 4; i++) { await new Promise(resolve => setImmediate(resolve)); await nextTick() }
  assert.equal(button(root).props.disabled, true)
  assert.match(content(root), /鸣潮 已排队/)
  assert.match(content(root), /2 项私人数据/)
  t.mock.timers.tick(COLLECT_POLL_MS)
  for (let i = 0; i < 4; i++) { await new Promise(resolve => setImmediate(resolve)); await nextTick() }
  assert.match(content(root), /鸣潮 采集中/)
  finished = true
  t.mock.timers.tick(COLLECT_POLL_MS)
  for (let i = 0; i < 4; i++) { await new Promise(resolve => setImmediate(resolve)); await nextTick() }
  assert.match(content(root), /鸣潮 部分来源失败/)
  assert.equal(refreshes, 1)
  assert.equal(button(root).props.disabled, false)
})
