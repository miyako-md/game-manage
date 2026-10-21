import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
import { challengeReport } from '../endfield-challenges.js'

const Reuse = await loadVue(new URL('../qq-image/ReuseBody.vue', import.meta.url))
const input = (game, provider, payload) => ({ command: '合成挑战回归', snapshot: {
  kind: 'game_snapshot', game, as_of: '2026-10-15T04:00:00Z',
  display_data: { panels: [{ game, provider, capability: 'combat', snapshot: {
    payload, fetched_at: '2026-10-15T04:00:00Z', state: 'ok', stale: false,
  } }], notices: [] },
} })

test('A reuses Endfield challenges with each category observation instead of WuWa modes', t => {
  const reports = [
    ['war', '2026-10-14T01:30:00Z'], ['monument', '2026-10-14T02:30:00Z'], ['crisis', '2026-10-14T03:30:00Z'],
  ].map(([kind, fetched_at]) => challengeReport({ kind, fetched_at, records: [],
    stale: kind === 'monument', summary: { highest: 0, challenge_count: 0 },
  }, kind))
  const root = mount(t, Reuse, { input: input('endfield', 'skland', { reports }) })
  for (const expected of ['战争观测时间 2026-10-14 09:30', '丰碑观测时间 2026-10-14 10:30', '危机观测时间 2026-10-14 11:30', '已有资料待更新']) {
    assert.ok(content(root).includes(expected), expected)
  }
  assert.doesNotMatch(content(root), /逆境深塔|战术全息|冥歌海墟/)
  assert.equal(nodes(root, 'button').length, 0)
})

test('A retains all three WuWa combat modes and supplied boss data', t => {
  const payload = {
    tower: { state: 'ok', data: { difficulty_list: [] } },
    hologram: { state: 'ok', data: { challenge_info: { fixture: [
      { boss_name: '回归首领', difficulty: 1, boss_level: 10, pass_time: 20, roles: [] },
    ] } } },
    slash: { state: 'ok', data: { difficulty_list: [] } },
  }
  const root = mount(t, Reuse, { input: input('wuthering_waves', 'kuro', payload) })
  for (const expected of ['逆境深塔', '战术全息', '冥歌海墟', '回归首领', '20']) assert.ok(content(root).includes(expected), expected)
  assert.doesNotMatch(content(root), /战争观测时间|丰碑观测时间|危机观测时间/)
  assert.equal(nodes(root, 'button').length, 0)
})

const Overview = await loadVue(new URL('../qq-image/AccountOverviewSheet.vue', import.meta.url))
const overviewStats = (t, panels) => {
  const root = mount(t, Overview, { input: { command: '我的', snapshot: { kind: 'game_snapshot', game: 'all', as_of: '2026-10-15T04:00:00Z',
    display_data: { notices: [], panels: panels.map(([game, provider, capability, payload]) => ({ game, provider, capability,
      snapshot: { payload, fetched_at: '2026-10-15T04:00:00Z', state: 'ok', stale: false } })) } } } })
  return nodes(root, 'div').filter(n => n.props.class === 'ao-stat-cell')
    .map(n => [content(nodes(n, 'span')[0]), content(nodes(n, 'strong')[0])])
}

test('overview counts use full role totals instead of the six roles shown', t => {
  const wuwaRoles = Array.from({ length: 6 }, (_, i) => ({ role_id: 1000 + i, name: `角色${i}`, star_level: 5 }))
  const nteRoles = { entries: Array.from({ length: 6 }, (_, i) => ({ id: String(i), name: `异能者${i}`, quality: 'S' })) }
  const stats = Object.fromEntries(overviewStats(t, [
    ['wuthering_waves', 'kuro', 'account', { nickname: '鸣潮', role_total: 47, gold_role_total: 35 }],
    ['wuthering_waves', 'kuro', 'roles', wuwaRoles],
  ]))
  assert.equal(stats['解锁角色'], '47'); assert.equal(stats['五星角色'], '35')
  const nte = Object.fromEntries(overviewStats(t, [
    ['nte', 'tajiduo', 'account', { nickname: '异环', character_count: 20, role_total: 20, gold_role_total: 16 }],
    ['nte', 'tajiduo', 'roles', nteRoles],
  ]))
  assert.equal(nte['解锁角色'], '20'); assert.equal(nte['S级角色'], '16')
  // A truncated roster without a known gold total stays unknown rather than counting six.
  const unknown = Object.fromEntries(overviewStats(t, [
    ['nte', 'tajiduo', 'account', { nickname: '异环', role_total: 20 }], ['nte', 'tajiduo', 'roles', nteRoles],
  ]))
  assert.equal(unknown['S级角色'], '未提供')
})

const overviewNames = (t, panels) => {
  const root = mount(t, Overview, { input: { command: '我的', snapshot: { kind: 'game_snapshot', game: 'all', as_of: '2026-10-15T04:00:00Z',
    display_data: { notices: [], panels: panels.map(([game, provider, capability, payload]) => ({ game, provider, capability,
      snapshot: { payload, fetched_at: '2026-10-15T04:00:00Z', state: 'ok', stale: false } })) } } } })
  return nodes(root, 'span').filter(n => n.props.class === 'ao-role-name-tag').map(n => content(n))
}

test('overview sheet shows at most six roles in the website order (Wuwa catalogue, NTE id)', t => {
  const wuwa = ['今汐', '秋水', '心', '长离', '未收录角色', '椿', '莉莉', '守岸人'].map((name, i) => ({ role_id: 1100 + i, name, star_level: 5, level: 90 - i }))
  assert.deepEqual(overviewNames(t, [['wuthering_waves', 'kuro', 'account', { nickname: '鸣潮' }], ['wuthering_waves', 'kuro', 'roles', wuwa]]),
    ['莉莉', '心', '椿', '守岸人', '长离', '今汐'])
  const stats = Object.fromEntries(overviewStats(t, [['wuthering_waves', 'kuro', 'account', { nickname: '鸣潮' }], ['wuthering_waves', 'kuro', 'roles', wuwa]]))
  // Eight sent, six shown: the roster count is the full one and the gold count is not taken from six.
  assert.equal(stats['解锁角色'], '8'); assert.equal(stats['五星角色'], '未提供')
  const nte = { entries: [1003, 1076, 1012, 1050, 1001, 1060, 1020].map(id => ({ id: String(id), name: `异能者${id}`, quality: 'S' })) }
  assert.deepEqual(overviewNames(t, [['nte', 'tajiduo', 'account', { nickname: '异环' }], ['nte', 'tajiduo', 'roles', nte]]),
    ['异能者1076', '异能者1060', '异能者1050', '异能者1020', '异能者1012', '异能者1003'])
})

test('Endfield overview keeps the service level order and counts the whole roster', t => {
  const operators = Array.from({ length: 9 }, (_, i) => ({ id: `op_${i}`, name: `合成干员${i}`, level: 90 - i, rarity: i < 4 ? 6 : 5 }))
  const panels = [['endfield', 'skland', 'account', { base: { name: '终末地' }, operators }], ['endfield', 'skland', 'roles', { operators: operators.slice(0, 6) }]]
  assert.deepEqual(overviewNames(t, panels), operators.slice(0, 6).map(op => op.name))
  const stats = Object.fromEntries(overviewStats(t, panels))
  assert.equal(stats['六星干员'], '4'); assert.equal(stats['五星干员'], '5'); assert.equal(stats['已记录干员'], '9')
})
