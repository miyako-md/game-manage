import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
const Summary = await loadVue(new URL('./EndfieldGachaSummary.vue', import.meta.url))
const snapshot = report => ({ stale: false, fetched_at: '2026-10-15T01:02:00Z', payload: { schema_version: 1, role_id: 'r', total: report.total, report: { schema_version: 1, role_id: 'r', ...report } } })
const view = report => ({ account: { nickname: '本人', role_id: 'r' }, accountId: 'r', snapshot: snapshot(report), message: '' })
const hasClass = (node, name) => String(node.props.class).split(' ').includes(name)

test('operator headhunting and weapon requisition get separate lines and are never added together', t => {
  const pools = [{ key: 'special', kind: 'character', total: 120, six_star: 3, five_star: 12, history: [{ pulls: 60, status: 'exact' }, { pulls: 40, status: 'exact' }] },
    { key: 'weapon:w1', kind: 'weapon', total: 40, six_star: 2, five_star: 5, history: [{ pulls: 9, status: 'lower_bound' }] }]
  const base = view({ total: 160, pending: false })
  const root = mount(t, Summary, { view: { ...base, snapshot: { ...base.snapshot, payload: { ...base.snapshot.payload, pools } } } })
  const lines = nodes(root, 'li').map(content)
  assert.deepEqual(lines, ['干员寻访 120 抽 6★ 3 5★ 12 平均出 6★ 50 抽', '武器申领 40 抽 6★ 2 5★ 5 平均出 6★ —'])
  assert.doesNotMatch(content(root), /160/)
  assert.match(content(root), /本轮同步完成/)
})

test('a snapshot without pools still states its recorded total plainly', t => {
  const root = mount(t, Summary, { view: view({ total: 120, six_star: 3 }) })
  assert.equal(nodes(root, 'li').length, 0)
  assert.match(content(root), /已记录寻访 120/)
})

test('an unsynced account gets a quiet placeholder and both actions keep working', t => {
  const events = []
  const root = mount(t, Summary, { view: { account: null, accountId: '', snapshot: null, message: '请登录有效的鹰角通行证后刷新寻访数据。' }, refreshing: false, onDetails: () => events.push('details'), onRefresh: () => events.push('refresh') })
  assert.match(content(root), /鹰角通行证 · 尚未读取/); assert.match(content(root), /请登录有效的鹰角通行证后刷新寻访数据/)
  assert.ok(nodes(root, 'span').some(node => hasClass(node, 'gs-ghost') && node.props['aria-hidden'] === 'true'))
  const buttons = nodes(root, 'button')
  assert.deepEqual(buttons.map(content), ['查看寻访详情 →', '刷新寻访数据'])
  buttons.forEach(button => button.props.onClick())
  assert.deepEqual(events, ['details', 'refresh'])
  assert.equal(content(mount(t, Summary, { view: view({ total: 1 }), refreshing: true }).children[0]).includes('同步中…'), true)
})

test('the overview card says how many pools failed to read', t => {
  const base = view({ total: 10, pending: true })
  const root = mount(t, Summary, { view: { ...base, snapshot: { ...base.snapshot, payload: { ...base.snapshot.payload, errors: [{ key: 'weapon:w1', label: '熔铸申领', message: 'x' }] } } } })
  assert.match(content(root), /1 个卡池读取失败，详见寻访详情/)
})
