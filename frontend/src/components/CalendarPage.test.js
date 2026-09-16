import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRenderer, nextTick, h, reactive } from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { calendarRange } from '../calendar.js'

const modules = new Map()
async function loadVue(url) {
  if (modules.has(url.href)) return modules.get(url.href)
  const { descriptor } = parse(readFileSync(url, 'utf8'))
  let code = compileScript(descriptor, { id: url.pathname, inlineTemplate: true, templateOptions: { compilerOptions: { hoistStatic: false } } }).content
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
function mount(t, component, props) {
  const node = (type, text = '') => ({ type, text, props: {}, style: {}, children: [], parent: null,
    addEventListener() {}, get options() { return this.children.filter(child => child.type === 'option') },
  })
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
const CalendarPage = await loadVue(new URL('./CalendarPage.vue', import.meta.url))
const games = [{ game_id: 'nte', display_name: '异环' }, { game_id: 'lol', display_name: '英雄联盟' }]
const snapshots = { nte: { events: { payload: [{ name: '待定的活动', category: '限时活动', source_title: '版本公告', source_post_id: '123', end_at: null }], fetched_at: '2026-09-14T10:00:00+08:00', stale: true } } }
test('calendar filters by initial game, keeps unknown events and exposes accessible source details', async (t) => {
  const props = reactive({ games, snapshots, initialGameId: 'nte' })
  const root = mount(t, CalendarPage, props)
  assert.match(content(root), /待定的活动/)
  assert.match(content(root), /起止时间均未知/)
  assert.match(content(root), /数据可能过期/)
  const trigger = nodes(root, 'button').find(n => n.props['aria-label'] === '查看活动详情：待定的活动')
  assert.ok(trigger)
  await trigger.props.onClick()
  await nextTick()
  assert.match(content(root), /版本公告/)
  assert.match(content(root), /2026-09-14 10:00/)
  assert.ok(nodes(root, 'section').some(n => n.props['aria-labelledby'] === 'calendar-detail-title'))
  props.initialGameId = 'lol'
  await nextTick()
  assert.doesNotMatch(content(root), /待定的活动/)
  assert.match(content(root), /暂无活动数据/)
})
test('navigation changes displayed time range and allows returning to today', async (t) => {
  const root = mount(t, CalendarPage, { games: [], snapshots: {} })
  assert.ok(nodes(root, 'button').find(n => n.text === '近 30 天').props['aria-pressed'])
  const initial = content(root)
  const next = nodes(root, 'button').find(n => n.props['aria-label'] === '下一时间范围')
  next.props.onClick()
  await nextTick()
  assert.notEqual(content(root), initial)
  nodes(root, 'button').find(n => n.text === '今天').props.onClick()
  await nextTick()
  assert.equal(content(root), initial)
  nodes(root, 'button').find(n => n.text === '14 天').props.onClick()
  await nextTick()
  assert.ok(nodes(root, 'button').find(n => n.text === '14 天').props['aria-pressed'])
})
test('calendar puts different activity types in one game group and includes type and status on each bar', (t) => {
  const now = Date.now()
  const iso = delta => new Date(now + delta * 86400000).toISOString()
  const root = mount(t, CalendarPage, { games, snapshots: { nte: { events: { payload: [
    { name: '签到活动', category: '签到', start_at: iso(-2), end_at: iso(5) },
    { name: '限时卡池', category: '卡池', start_at: iso(-2), end_at: iso(-1) },
  ] } } } })
  assert.equal(nodes(root, 'div').filter(n => n.props.class === 'timeline-group').length, 1)
  const bars = nodes(root, 'button').filter(n => n.props.class?.includes('timeline-event'))
  assert.equal(bars.length, 2)
  assert.match(content(bars[0]), /签到活动 签到 进行中/)
  assert.match(content(bars[1]), /限时卡池 卡池 已结束/)
})
test('timeline renders exact range proportions, a separate single-date marker and clipped detail', async (t) => {
  const range = calendarRange(Date.now(), 'month')
  const iso = time => new Date(time).toISOString()
  const span = range.end - range.start
  const root = mount(t, CalendarPage, { games, snapshots: { nte: { events: { payload: [
    { name: '半月活动', start_at: iso(range.start + span / 4), end_at: iso(range.start + span * 3 / 4) },
    { name: '只有截止', end_at: iso(range.start + span / 2) },
    { name: '跨月活动', start_at: iso(range.start - 86400000), end_at: iso(range.end + 86400000) },
    { name: '异常活动', start_at: iso(range.end), end_at: iso(range.start) },
  ] } } } })
  nodes(root, 'button').find(n => n.text === '整月').props.onClick()
  await nextTick()
  const bar = nodes(root, 'button').find(n => n.props['aria-label'] === '查看活动详情：半月活动')
  assert.equal(bar.props.style.left, '25%')
  assert.equal(bar.props.style.width, '50%')
  const point = nodes(root, 'button').find(n => n.props['aria-label'] === '查看活动详情：只有截止')
  assert.equal(point.props.style.left, '50%')
  assert.equal(point.props.style.width, undefined)
  assert.match(content(point), /开始时间未知/)
  assert.match(content(root), /截止早于开始/)
  await nodes(root, 'button').find(n => n.props['aria-label'] === '查看活动详情：跨月活动').props.onClick()
  await nextTick()
  assert.match(content(root), /裁剪左侧和右侧/)
})
test('missing event snapshots and failed reads distinguish uncollected data from retained snapshots', async (t) => {
  const props = reactive({ games, snapshots: {}, readErrors: {}, initialGameId: 'nte' })
  const root = mount(t, CalendarPage, props)
  assert.match(content(root), /尚未取得活动快照/)
  props.snapshots = snapshots
  props.readErrors = { nte: '网络连接失败' }
  await nextTick()
  assert.match(content(root), /游戏数据读取或刷新异常/)
  assert.match(content(root), /网络连接失败/)
  assert.match(content(root), /保留上次成功快照/)
  assert.match(content(root), /待定的活动/)
  props.initialGameId = 'lol'
  await nextTick()
  assert.doesNotMatch(content(root), /网络连接失败/)
  assert.match(content(root), /尚未取得活动快照/)
})
