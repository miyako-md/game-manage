import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'

const Dashboard = await loadVue(new URL('./EndfieldDashboard.vue', import.meta.url))
const flush = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }
const response = data => ({ ok: true, json: async () => data })

test('unconnected account offers local connection and all tool tabs', async t => {
  t.mock.method(globalThis, 'fetch', async () => response({ connected: false, roles: [] }))
  const root = mount(t, Dashboard, { snaps: {} })
  await flush()
  assert.match(content(root), /凭据只在本机加密保存/)
  assert.match(content(root), /蓝图收藏/)
  assert.match(content(root), /地图与图鉴/)
  assert.doesNotMatch(content(root), /敬请期待/)
})

test('role switch immediately clears old card and ignores its late response', async t => {
  const cardResolvers = []
  let status = { connected: true, roles: [{ role_id: 'old', server_id: '1', nickname: '旧角色' }, { role_id: 'new', server_id: '1', nickname: '新角色' }], selected_role_id: 'old', selected_server_id: '1' }
  t.mock.method(globalThis, 'fetch', async (url, options = {}) => {
    if (url.endsWith('/status')) return response(status)
    if (url.endsWith('/card')) return new Promise(resolve => { cardResolvers.push(resolve) })
    if (url.endsWith('/attendance')) return response({ supported: false })
    if (url.endsWith('/role')) { status = { ...status, selected_role_id: 'new' }; return response(status) }
    return response({})
  })
  const root = mount(t, Dashboard, { snaps: { account: { payload: { nickname: '通行证', role_id: 'passport' } } } })
  await flush()
  assert.match(content(root), /旧角色/)
  assert.match(content(root), /通行证/)
  const select = nodes(root, 'select')[0]
  select.props.onChange({ target: { value: 'new:1' } })
  await flush()
  cardResolvers[0](response({ payload: { base: { name: '旧数据' } } }))
  await flush()
  assert.match(content(root), /新角色/)
  assert.doesNotMatch(content(root), /旧数据/)
})

test('map catalog selects a map and opens a point description', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async url => {
    calls.push(url)
    if (url.endsWith('/status')) return response({ connected: false, roles: [] })
    if (url.endsWith('/public')) return response({ news: { items: [] }, tools: [] })
    if (url.includes('/map/marks/')) return response({ info: { id: 'point1', typeSub: { name: '矿点' }, pos: { x: 1, y: 2, z: 3 }, desc: '山坡北侧' } })
    if (url.includes('map_id=map1')) return response({ maps: [{ id: 'map1', name: '起始区域' }], categories: [], marks: [{ id: 'point1', name: '矿点一', x: 1, y: 2, z: 3 }], total: 1, limit: 100 })
    return response({ maps: [{ id: 'map1', name: '起始区域' }], categories: [], marks: [], total: 0, limit: 100 })
  })
  const root = mount(t, Dashboard, { snaps: {}, initialSection: 'map' })
  await flush(); await flush()
  assert.ok(calls.some(url => url.includes('map_id=map1')))
  assert.match(content(root), /矿点一/)
  nodes(root, 'button').find(n => content(n) === '查看详情').props.onClick()
  await flush()
  assert.match(content(root), /山坡北侧/)
  assert.match(content(root), /坐标：1，2，3/)
})

test('attendance shows signed days and today reward without exposing raw data', async t => {
  t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('/status')) return response({ connected: true, roles: [{ role_id: '7', server_id: '1', nickname: '管理员' }], selected_role_id: '7', selected_server_id: '1' })
    if (url.endsWith('/card')) return response({ payload: { base: { name: '管理员', level: 20 }, progress: [] } })
    if (url.endsWith('/attendance')) return response({ supported: true, status: 'signed', calendar: [{ done: true }, { done: true }, { done: false }], today_award: { name: '资源箱', count: 2 } })
    return response({})
  })
  const root = mount(t, Dashboard, { snaps: {} })
  await flush(); await flush()
  assert.match(content(root), /今日已签/)
  assert.match(content(root), /本期已签 2 天/)
  assert.match(content(root), /今日奖励：资源箱 × 2/)
  assert.equal(nodes(root, 'button').find(n => content(n) === '手动签到').props.disabled, true)
})

test('official catalog uses top-level entities and pages without mixing nested skills', async t => {
  t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('/status')) return response({ connected: true, roles: [{ role_id: '7', server_id: '1', nickname: '管理员' }], selected_role_id: '7', selected_server_id: '1' })
    if (url.endsWith('/public')) return response({ news: { items: [] }, tools: [] })
    if (url.includes('/map?')) return response({ maps: [], categories: [], marks: [] })
    if (url.includes('/skland/tools?')) return response({ supported: true, payload: { chars: Array.from({ length: 25 }, (_, i) => ({ id: `char${i + 1}`, name: `干员${i + 1}`, skills: [{ id: `skill${i + 1}`, name: `技能${i + 1}` }] })) } })
    return response({})
  })
  const root = mount(t, Dashboard, { snaps: {}, initialSection: 'map' })
  await flush(); await flush()
  nodes(root, 'form').find(n => nodes(n, 'button').some(b => content(b) === '查询资料')).props.onSubmit?.({ preventDefault() {} })
  await flush()
  assert.match(content(root), /干员1/)
  assert.match(content(root), /char1/)
  assert.doesNotMatch(content(root), /干员25/)
  assert.doesNotMatch(content(root), /技能25/)
  nodes(root, 'button').find(n => content(n) === '下一页').props.onClick()
  await nextTick()
  assert.match(content(root), /干员25/)
})

test('operator equipment is requested on demand and shown with skills', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async url => {
    calls.push(url)
    if (url.endsWith('/status')) return response({ connected: true, roles: [{ role_id: '7', server_id: '1', nickname: '管理员' }], selected_role_id: '7', selected_server_id: '1' })
    if (url.endsWith('/card')) return response({ payload: { operators: [{ id: 'op1', name: '干员甲', level: 30 }] } })
    if (url.includes('/operators/op1')) return response({ operator: { id: 'op1', name: '干员甲', weapon: { name: '试作武器', level: 20, gem: { name: '晶石' } }, equipment: [{ name: '护甲', level: 10 }], skills: [{ name: '战术技能', level: 5 }] } })
    return response({ supported: false })
  })
  const root = mount(t, Dashboard, { snaps: {}, initialSection: 'operators' })
  await flush(); await flush()
  assert.ok(!calls.some(url => url.includes('/operators/')))
  nodes(root, 'button').find(n => content(n) === '查看配装').props.onClick()
  await flush()
  assert.match(content(root), /试作武器/)
  assert.match(content(root), /护甲（等级 10）/)
  assert.match(content(root), /战术技能（等级 5）/)
})

test('refreshing the profile does not discard an in-flight attendance response', async t => {
  let finishAttendance
  t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('/status')) return response({ connected: true, roles: [{ role_id: '7', server_id: '1', nickname: '管理员' }], selected_role_id: '7', selected_server_id: '1' })
    if (url.endsWith('/attendance')) return new Promise(resolve => { finishAttendance = resolve })
    return response({ payload: { base: { name: '管理员' }, progress: [] } })
  })
  const root = mount(t, Dashboard, { snaps: {} })
  await flush(); await flush()
  nodes(root, 'button').find(n => content(n).includes('手动刷新档案')).props.onClick()
  await flush()
  finishAttendance(response({ supported: true, status: 'signed', calendar: [{ done: true }] }))
  await flush()
  assert.match(content(root), /今日已签/)
  assert.doesNotMatch(content(root), /正在读取签到状态/)
})

test('changing catalog while a request is pending enables a new query', async t => {
  let finishOld
  t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('/status')) return response({ connected: true, roles: [{ role_id: '7', server_id: '1' }], selected_role_id: '7', selected_server_id: '1' })
    if (url.includes('/skland/tools?')) return new Promise(resolve => { finishOld = resolve })
    return response({ maps: [], news: { items: [] }, tools: [] })
  })
  const root = mount(t, Dashboard, { snaps: {}, initialSection: 'map' })
  await flush(); await flush()
  const form = nodes(root, 'form').find(n => nodes(n, 'button').some(b => content(b) === '查询资料'))
  form.props.onSubmit({ preventDefault() {} })
  await flush()
  nodes(form, 'select')[0].props['onUpdate:modelValue']('weapons')
  await flush()
  finishOld(response({ payload: { chars: [{ id: 'old', name: '旧干员' }] } }))
  await flush()
  assert.equal(nodes(root, 'button').find(b => content(b) === '查询资料').props.disabled, false)
  assert.doesNotMatch(content(root), /旧干员|正在读取官方资料/)
})

test('changing a map category returns to the first page', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('/status')) return response({ connected: false, roles: [] })
    if (url.includes('/map?')) {
      calls.push(url)
      return response({ maps: [{ id: 'map1', name: '区域' }], categories: [{ id: 'ore', name: '矿点' }],
        marks: [{ id: 'm1', name: '点位' }], total: url.includes('type_id=ore') ? 5 : 150, limit: 100 })
    }
    return response({ news: { items: [] }, tools: [] })
  })
  const root = mount(t, Dashboard, { snaps: {}, initialSection: 'map' })
  await flush(); await flush()
  nodes(root, 'button').find(b => content(b) === '下一页').props.onClick()
  await flush()
  assert.ok(calls.at(-1).includes('offset=100'))
  const filters = nodes(root, 'form').find(f => nodes(f, 'select').length === 3)
  nodes(filters, 'select')[2].props['onUpdate:modelValue']('ore')
  await flush(); await flush()
  assert.ok(calls.at(-1).includes('type_id=ore') && calls.at(-1).includes('offset=0'))
})
