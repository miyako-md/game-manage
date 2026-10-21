import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, nodes, content, choose } from '../test-utils/vue.js'

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
  choose(root, '森空岛角色', 'new:1')
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
    if (url.includes('/operators/op1')) return response({ operator: { id: 'op1', name: '干员甲', weapon: { name: '试作武器', level: 20, gem: { name: '晶石' } }, equipment: [{ name: '护甲', level: 10 }], skills: [{ name: '战术技能', level: 5 }], tactical_item: { name:'试作战术设备',rarity:0,active_effect:'造成 {0} 点伤害' } } })
    return response({ supported: false })
  })
  const root = mount(t, Dashboard, { snaps: {}, initialSection: 'operators' })
  await flush(); await flush()
  assert.ok(!calls.some(url => url.includes('/operators/')))
  nodes(root, 'button').find(n => content(n) === '查看配装').props.onClick()
  await flush()
  assert.match(content(root), /试作武器/)
  assert.match(content(root), /护甲 等级 LV\. 10/)
  assert.match(content(root), /LV\. 5 战术技能/)
  assert.match(content(root), /试作战术设备/)
  assert.match(content(root), /稀有度 0/)
  assert.match(content(root), /造成 \{0\} 点伤害/)
})

test('operator fallback keeps its own old timestamp and closing ignores a pending detail response', async t => {
  let pending, requests = 0
  t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('/status')) return response({connected:true,roles:[{role_id:'7',server_id:'1'}],selected_role_id:'7',selected_server_id:'1'})
    if (url.endsWith('/card')) return response({fetched_at:'2026-10-15T04:00:00Z',payload:{operators:[{id:'a',name:'干员甲'}]}})
    if (url.includes('/operators/a')) {
      requests++
      if (requests===1) return response({operator:{name:'干员甲',weapon:{name:'缓存武器'}},stale:true,error:'本次读取失败，保留旧配装',fetched_at:'2026-10-15T01:00:00Z'})
      return new Promise(resolve=>{pending=resolve})
    }
    return response({})
  })
  const root=mount(t,Dashboard,{snaps:{},initialSection:'operators'})
  await flush();await flush()
  nodes(root,'button').find(node=>content(node)==='查看配装').props.onClick();await flush()
  assert.match(content(root),/配装同步于.*09:00/);assert.match(content(root),/配装待更新/)
  assert.match(content(root),/缓存武器/);assert.match(content(root),/同步于.*12:00/)
  nodes(root,'button').find(node=>content(node)==='重新读取配装').props.onClick();await flush()
  nodes(root,'button').find(node=>content(node)==='← 返回全员练度').props.onClick();await flush()
  pending(response({operator:{name:'晚到的配装'},fetched_at:'2026-10-15T05:00:00Z'}));await flush()
  assert.doesNotMatch(content(root),/晚到的配装|配装同步于/)
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
  nodes(root, 'button').find(n => content(n).includes('刷新档案')).props.onClick()
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
  choose(form, '资料类别', 'weapons')
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
  choose(root, '点位类型', 'ore')
  await flush(); await flush()
  assert.ok(calls.at(-1).includes('type_id=ore') && calls.at(-1).includes('offset=0'))
})

test('passport login offers one-click Skland connection and loads the matching role', async t => {
  const calls = []
  let status = { connected: false, passport_available: true, roles: [] }
  t.mock.method(globalThis, 'fetch', async (url, options = {}) => {
    calls.push([options.method || 'GET', url])
    if (url.endsWith('/skland/passport')) {
      status = { connected: true, source: 'passport', passport_available: true, roles: [{ role_id: 'r1', server_id: '1', nickname: '管理员' }], selected_role_id: 'r1', selected_server_id: '1' }
      return response(status)
    }
    if (url.endsWith('/status')) return response(status)
    if (url.endsWith('/card')) return response({ payload: { base: { name: '管理员', level: 40 } } })
    if (url.endsWith('/attendance')) return response({ supported: true, status: 'unsigned', calendar: [] })
    return response({})
  })
  const root = mount(t, Dashboard, { snaps: {} })
  await flush()
  assert.match(content(root), /手动连接（备用）/)
  assert.equal(nodes(root, 'details')[0].props.open, false)
  nodes(root, 'button').find(n => content(n) === '用鹰角通行证连接').props.onClick()
  await flush(); await flush()
  assert.ok(calls.some(([method, url]) => method === 'POST' && url.endsWith('/skland/passport')))
  assert.ok(calls.some(([, url]) => url.endsWith('/skland/card')))
  assert.match(content(root), /已用鹰角通行证连接森空岛/)
  assert.equal(nodes(root, 'span').find(n => content(n) === '鹰角通行证')?.props.class, 'badge')
})

test('a rejected one-click connection explains why and opens the manual form', async t => {
  t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('/skland/passport')) return { ok: false, status: 502, json: async () => ({ detail: '森空岛未接受通行证授权，请改用手动连接' }) }
    if (url.endsWith('/status')) return response({ connected: false, passport_available: true, roles: [] })
    return response({})
  })
  const root = mount(t, Dashboard, { snaps: {} })
  await flush()
  nodes(root, 'button').find(n => content(n) === '用鹰角通行证连接').props.onClick()
  await flush()
  assert.match(content(root), /森空岛未接受通行证授权，请改用手动连接/)
  assert.equal(nodes(root, 'details')[0].props.open, true)
})

test('without a passport login only the expanded manual form is offered', async t => {
  t.mock.method(globalThis, 'fetch', async () => response({ connected: false, passport_available: false, roles: [] }))
  const root = mount(t, Dashboard, { snaps: {} })
  await flush()
  assert.match(content(root), /在「社区账号」登录终末地后，可一键连接森空岛/)
  assert.equal(nodes(root, 'details')[0].props.open, true)
  assert.ok(!nodes(root, 'button').some(n => content(n) === '用鹰角通行证连接'))
})

test('a passport session whose role differs from Skland asks the user to choose', async t => {
  t.mock.method(globalThis, 'fetch', async url => url.endsWith('/status')
    ? response({ connected: true, source: 'passport', passport_available: true, roles: [{ role_id: 'r2', server_id: '1', nickname: '其他角色' }], selected_role_id: null, selected_server_id: null })
    : response({}))
  const root = mount(t, Dashboard, { snaps: {} })
  await flush()
  assert.match(content(root), /森空岛绑定的角色与通行证登录的角色不同，请确认后手动选择/)
})

for (const [label, failing, act] of [
  ['role switch', '/skland/role', root => choose(root, '森空岛角色', 'new:1')],
  ['disconnect', '/skland/connection', root => nodes(root, 'button').find(n => content(n) === '断开森空岛').props.onClick()],
]) test(`a failed ${label} reloads the challenge records instead of the profile card`, async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async url => {
    calls.push(url)
    if (url.endsWith('/status')) return response({ connected: true, roles: [{ role_id: 'old', server_id: '1', nickname: '旧角色' }, { role_id: 'new', server_id: '1', nickname: '新角色' }], selected_role_id: 'old', selected_server_id: '1' })
    if (url.includes('/skland/challenges?')) return response({ kind: 'war', fetched_at: '2026-10-15T01:02:00Z', records: [{ name: '第一期战争', stars: 3, weeks: [] }] })
    if (url.endsWith(failing)) return { ok: false, status: 502, json: async () => ({ detail: '森空岛暂时无法响应' }) }
    return response({})
  })
  const root = mount(t, Dashboard, { snaps: {}, initialSection: 'challenges' })
  await flush(); await flush()
  assert.match(content(root), /第一期战争/)
  calls.length = 0
  act(root)
  await flush(); await flush()
  assert.match(content(root), /暂时无法读取，请稍后重试/)
  assert.match(content(root), /第一期战争/)
  assert.doesNotMatch(content(root), /尚未采集战争记录/)
  assert.equal(calls.filter(url => url.includes('/skland/challenges?')).length, 1)
  assert.ok(!calls.some(url => url.endsWith('/card')))
})

for (const [initialSection, attendanceCalls] of [['overview', 1], ['operators', 0]]) test(`a failed role switch on ${initialSection} still reloads the profile card`, async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async url => {
    calls.push(url)
    if (url.endsWith('/status')) return response({ connected: true, roles: [{ role_id: 'old', server_id: '1', nickname: '旧角色' }, { role_id: 'new', server_id: '1', nickname: '新角色' }], selected_role_id: 'old', selected_server_id: '1' })
    if (url.endsWith('/card')) return response({ payload: { base: { name: '旧档案' } } })
    if (url.endsWith('/attendance')) return response({ supported: false })
    if (url.endsWith('/skland/role')) return { ok: false, status: 502, json: async () => ({ detail: '森空岛暂时无法响应' }) }
    return response({})
  })
  const root = mount(t, Dashboard, { snaps: {}, initialSection })
  await flush(); await flush()
  calls.length = 0
  choose(root, '森空岛角色', 'new:1')
  await flush(); await flush()
  assert.equal(calls.filter(url => url.endsWith('/card')).length, 1)
  assert.equal(calls.filter(url => url.endsWith('/attendance')).length, attendanceCalls)
  assert.ok(!calls.some(url => url.includes('/skland/challenges?')))
})

test('choosing the role placeholder puts the dropdown back on the active role', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options = {}) => {
    calls.push([options.method || 'GET', url])
    if (url.endsWith('/status')) return response({ connected: true, roles: [{ role_id: 'old', server_id: '1', nickname: '旧角色' }], selected_role_id: 'old', selected_server_id: '1' })
    if (url.endsWith('/card')) return response({ payload: { base: { name: '旧档案' } } })
    return response({ supported: false })
  })
  const root = mount(t, Dashboard, { snaps: {} })
  await flush(); await flush()
  choose(root, '森空岛角色', '')
  await flush()
  assert.equal(nodes(nodes(root, 'ul').find(n => n.props['aria-label'] === '森空岛角色'), 'li').find(n => n.props['aria-selected']).props['data-value'], 'old:1')
  assert.match(content(root), /旧档案/)
  assert.ok(!calls.some(([method, url]) => method === 'POST' && url.endsWith('/skland/role')))
})

const blueprintFetch = async url => url.endsWith('/blueprints') ? response({ items: [{ id: 'b1', name: '工厂', code: 'ABC', notes: '' }] }) : response({ connected: false, roles: [] })
const button = (root, label) => nodes(root, 'button').find(n => content(n) === label)

test('copying a share code confirms in the blueprint list and never on the Skland card', async t => {
  t.mock.getter(globalThis, 'navigator', () => ({ clipboard: { writeText: async () => {} } }))
  t.mock.method(globalThis, 'fetch', blueprintFetch)
  const root = mount(t, Dashboard, { snaps: {}, initialSection: 'blueprints' })
  await flush(); await flush()
  button(root, '复制分享码').props.onClick()
  await flush()
  assert.match(content(root), /分享码已复制/)
  button(root, '概览').props.onClick()
  await flush()
  assert.doesNotMatch(content(root), /分享码已复制/)
  button(root, '蓝图收藏').props.onClick()
  await flush()
  assert.doesNotMatch(content(root), /分享码已复制/)
})

test('a failed copy and a successful copy replace each other in the blueprint list', async t => {
  let clipboardFails = true
  t.mock.getter(globalThis, 'navigator', () => ({ clipboard: { writeText: async () => { if (clipboardFails) throw new Error('denied') } } }))
  t.mock.method(globalThis, 'fetch', blueprintFetch)
  const root = mount(t, Dashboard, { snaps: {}, initialSection: 'blueprints' })
  await flush(); await flush()
  for (const [fails, shown, hidden] of [[true, /复制失败，请手动选取分享码/, /分享码已复制/], [false, /分享码已复制/, /复制失败/], [true, /复制失败，请手动选取分享码/, /分享码已复制/]]) {
    clipboardFails = fails
    button(root, '复制分享码').props.onClick()
    await flush()
    assert.match(content(root), shown)
    assert.doesNotMatch(content(root), hidden)
  }
})

test('a profile refresh whose answer cannot be read keeps the profile and says so', async t => {
  t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('/status')) return response({ connected: true, roles: [{ role_id: '7', server_id: '1', nickname: '管理员' }], selected_role_id: '7', selected_server_id: '1' })
    if (url.endsWith('/card')) return response({ payload: { base: { name: '档案昵称甲', level: 20 }, progress: [] } })
    if (url.endsWith('/skland/refresh')) return new Response('{"payload":', { status: 200 })
    return response({ supported: false })
  })
  const root = mount(t, Dashboard, { snaps: {} })
  await flush(); await flush()
  assert.match(content(root), /档案昵称甲/)
  nodes(root, 'button').find(n => content(n).includes('刷新档案')).props.onClick()
  await flush()
  assert.match(content(root), /档案昵称甲/)
  assert.match(content(root), /待更新/)
  assert.match(content(nodes(root, 'p').find(n => n.props.role === 'alert')), /暂时无法读取，请稍后重试。/)
  assert.doesNotMatch(content(root), /暂无档案数据/)
})

test('a blueprint save whose answer cannot be read keeps the form and the list and says so', async t => {
  const previous = { Document: globalThis.Document, ShadowRoot: globalThis.ShadowRoot }   // the v-model directive's update hook looks for both
  Object.assign(globalThis, { Document: class {}, ShadowRoot: class {} })
  t.after(() => { for (const [name, value] of Object.entries(previous)) { if (value === undefined) delete globalThis[name]; else globalThis[name] = value } })
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options = {}) => {
    calls.push(`${options.method || 'GET'} ${url}`)
    return options.method === 'POST' && url.endsWith('/blueprints') ? new Response('{"payload":', { status: 200 }) : blueprintFetch(url)
  })
  const root = mount(t, Dashboard, { snaps: {}, initialSection: 'blueprints' })
  await flush(); await flush()
  const [name, code] = nodes(root, 'input')
  name.props['onUpdate:modelValue']('新蓝图'); code.props['onUpdate:modelValue']('NEW-CODE'); await flush()
  await nodes(root, 'form')[0].props.onSubmit({ preventDefault() {} }); await flush()
  assert.deepEqual([name.value, code.value], ['新蓝图', 'NEW-CODE'])
  assert.match(content(nodes(root, 'p').find(n => n.props.role === 'alert')), /暂时无法读取，请稍后重试。/)
  assert.match(content(root), /工厂/)
  assert.equal(calls.filter(call => call === 'GET /api/endfield/blueprints').length, 1, 'the list was read again as if the save had worked')
})

test('profile tabs show an outline of what connecting unlocks until a role is chosen, and the overview never does', async t => {
  let connected = false
  const status = () => connected
    ? { connected: true, roles: [{ role_id: '7', server_id: '1', nickname: '管理员' }], selected_role_id: '7', selected_server_id: '1' }
    : { connected: false, passport_available: true, roles: [] }
  t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('/status')) return response(status())
    if (url.endsWith('/skland/passport')) { connected = true; return response(status()) }
    if (url.endsWith('/card')) return response({ payload: { operators: [{ id: 'a', name: '干员甲', level: 3 }] } })
    return response({ supported: false })
  })
  const root = mount(t, Dashboard, { snaps: {} })
  await flush()
  assert.doesNotMatch(content(root), /连接森空岛并选择角色后/)
  for (const [tab, note] of [['全员练度', /稀有度与精英阶段分布/], ['地区建设', /各地区调度券、据点与区域收集进度/], ['帝江号', /各舱室驻守干员的心情与信赖/]]) {
    nodes(root, 'button').find(n => content(n) === tab).props.onClick(); await flush()
    assert.match(content(root), new RegExp(`连接森空岛并选择角色后，这里显示${note.source}`))
    // The outline is decoration: no controls, and it is hidden from assistive tech.
    const outline = nodes(root, 'section').find(n => n.props['aria-label'] === '连接后可查看的内容')
    assert.equal(nodes(outline, 'button').length, 0)
    assert.equal(nodes(outline, 'div').find(n => String(n.props.class).includes('locked-grid')).props['aria-hidden'], 'true')
  }
  nodes(root, 'button').find(n => content(n) === '概览').props.onClick(); await flush()
  assert.doesNotMatch(content(root), /连接森空岛并选择角色后/)
  // Once a role is connected the real tab replaces the outline.
  nodes(root, 'button').find(n => content(n) === '用鹰角通行证连接').props.onClick(); await flush(); await flush()
  nodes(root, 'button').find(n => content(n) === '全员练度').props.onClick(); await flush(); await flush()
  assert.doesNotMatch(content(root), /连接森空岛并选择角色后/)
  assert.match(content(root), /干员甲/)
})

test('the section tabs are one pill track with a pressed state and the 更多 pills keep their own row', async t => {
  t.mock.method(globalThis, 'fetch', async () => response({ connected: false, roles: [] }))
  const root = mount(t, Dashboard, { snaps: {} })
  await flush()
  const [main, more] = nodes(root, 'nav')
  assert.equal(main.props.class, 'ef-main-nav segmented')
  assert.equal(more.props.class, 'ef-more-nav segmented')
  assert.deepEqual(nodes(main, 'button').map(n => [content(n), n.props['aria-pressed'] ?? n.props['aria-expanded']]), [['概览', true], ['全员练度', false], ['地区建设', false], ['帝江号', false], ['抽卡统计', false], ['更多', false]])
  assert.equal(nodes(more, 'button').length, 5)
  nodes(more, 'button').find(n => content(n) === '蓝图收藏').props.onClick(); await flush()
  const toggle = nodes(main, 'button').at(-1)
  assert.equal(content(toggle), '蓝图收藏'); assert.ok(String(toggle.props.class).includes('active'))
})

test('cloud challenges read the combat snapshot, switch kinds without requests and refresh through the scheduler', async t => {
  const calls = [], events = []
  t.mock.method(globalThis, 'fetch', async url => { calls.push(url); return response({}) })
  const account = { account_id: 's', provider: 'skland', game: 'endfield', server: '1', version: 1, roles: [{ role_id: 'role-s', display_name: '本人', is_default: true }] }
  const report = (kind, extra = {}) => ({ schema_version: 1, kind, supported: true, available: true, stale: false, fetched_at: '2026-10-21T01:00:00Z', records: [], honors: [], summary: { listed_count: 0, highest: null, challenge_count: null }, ...extra })
  const combat = { account_id: 's', role_id: 'role-s', state: 'ok', stale: false, fetched_at: '2026-10-21T01:05:00Z', payload: { schema_version: 1, reports: [
    report('war', { records: [{ id: 's1', name: '快照赛季', stars: 0, weeks: [] }], summary: { listed_count: 1, highest: null, challenge_count: null } }),
    report('monument', { available: false, stale: true, fetched_at: null, summary: { listed_count: null, highest: null, challenge_count: null } }),
    report('crisis', { stale: true, records: [{ id: 'r1', name: '快照合约', passed: false, result: 0 }], summary: { listed_count: 1, highest: 0, challenge_count: null } }),
  ] } }
  const props = reactive({ cloudAccount: account, cloudRole: 'role-s', cloudSources: { skland: { account, role: 'role-s' } }, sourceSnapshots: { skland: { account: { account_id: 's', role_id: 'role-s', payload: null }, combat } }, snaps: {}, initialSection: 'challenges', onRefresh: () => events.push('refresh') })
  const root = mount(t, Dashboard, props)
  await flush(); await flush()
  assert.match(content(root), /快照赛季/)
  const kind = name => nodes(root, 'button').find(n => content(n) === name).props.onClick()
  kind('丰碑'); await flush()
  assert.match(content(root), /最近一次采集失败，尚无成功资料/)
  assert.doesNotMatch(content(root), /快照赛季/)
  kind('危机'); await flush()
  assert.match(content(root), /快照合约/); assert.match(content(root), /已有资料待更新/)
  nodes(root, 'button').find(n => content(n) === '重新读取危机').props.onClick(); await flush()
  assert.deepEqual(events, ['refresh'])
  props.sourceSnapshots.skland.combat = { ...combat, role_id: 'another-role' }; await flush()
  assert.doesNotMatch(content(root), /快照合约/)
  assert.ok(!calls.some(url => String(url).includes('/skland/challenges')), 'cloud mode must not call the live challenge route')
})
