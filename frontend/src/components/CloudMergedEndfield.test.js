import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, nodes, content, choose } from '../test-utils/vue.js'
import { configureHttpClient, setAccountScope } from '../http-client.js'
const App = await loadVue(new URL('../CloudApp.vue', import.meta.url))
const Card = await loadVue(new URL('./CloudGameCard.vue', import.meta.url))
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }
const settle = async () => { for (let i = 0; i < 6; i++) await tick() }
const button = (root, text) => nodes(root, 'button').find(node => content(node) === text)
const account = (provider, id, uid = '9001') => ({ account_id: id, grant_id: `grant-${id}`, version: 1, provider, game: 'endfield', channel: 'bilibili', server: '1', state: 'active', capabilities: provider === 'hypergryph' ? ['account', 'gacha'] : ['account'], roles: [{ role_id: `role-${id}`, game_uid: uid, display_name: '共同角色', is_default: true }] })
const h = account('hypergryph', 'h'), s = account('skland', 's')
const sources = { hypergryph: { account: h, role: 'role-h' }, skland: { account: s, role: 'role-s' } }
const envelope = (id, payload, extra = {}) => ({ account_id: id, role_id: `role-${id}`, state: 'ok', fetched_at: '2026-10-18T05:00:00Z', payload, ...extra })
const passport = envelope('h', { role_id: '9001', nickname: '鹰角本人' })
const gacha = envelope('h', { schema_version: 1, role_id: '9001', total: 12, pools: [], report: { schema_version: 1, role_id: '9001', total: 12, six_star: 1, five_star: 2, free: 0, pending: false } })
const profile = envelope('s', { base: { name: '同角色档案', role_id: '9001', level: 32 }, stamina: { current: 86, maximum: 240 }, progress: [{ id: 'daily', name: '每日活跃', cur: 20, total: 100 }, { id: 'weekly', name: '每周任务', cur: 30, total: 400 }], operators: [{ id: 'op', name: '合并干员', level: 40 }] })
const sourceSnapshots = { hypergryph: { account: passport, gacha }, skland: { account: profile } }

test('the same Endfield role shows profile and gacha together, while tools keep their source-specific routes', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    calls.push([path, options.method])
    const data = path === '/api/identity/me' ? { user_id: 'owner' }
      : path.endsWith('/csrf') ? { csrf_token: 'fixture' }
      : path === '/api/accounts' ? { accounts: [s, h] }
      : path === '/api/accounts/h/roles/role-h/snapshot/account' ? passport
      : path === '/api/accounts/h/roles/role-h/snapshot/gacha' ? gacha
      : path === '/api/accounts/s/roles/role-s/snapshot/account' ? profile
      : path.endsWith('/operators/op') ? { operator: { name: '合并干员', weapon: { name: '同角色武器', level: 20 } } }
      : path.includes('/gacha/records') ? { records: [], total: 0 }
      : { state: 'never', payload: null, supported: false }
    return new Response(JSON.stringify(data))
  })
  const root = mount(t, App); await settle()
  assert.match(content(root), /86/)
  assert.match(content(root), /每日活跃/); assert.match(content(root), /每周任务/)
  const digest = nodes(root, 'section').find(node => String(node.props.class).split(' ').includes('ov-gacha'))
  assert.match(content(digest), /12 抽/)
  button(root, '终末地').props.onClick(); await settle()
  assert.match(content(root), /同角色档案/); assert.match(content(root), /已记录寻访 12/)
  assert.doesNotMatch(content(root), /单独选择|上方切换|查看授权/)
  const roleMenu = nodes(root, 'ul').find(node => node.props['aria-label'] === '查看角色')
  assert.deepEqual(nodes(roleMenu, 'li').map(node => node.props['data-value']), ['h:role-h'])
  const navigation = nodes(root, 'nav').find(node => node.props['aria-label'] === '本人游戏角色')
  assert.equal(nodes(navigation, 'button').length, 1)
  button(root, '全员练度').props.onClick(); await tick()
  assert.match(content(root), /合并干员/)
  button(root, '查看配装').props.onClick(); await settle()
  assert.match(content(root), /同角色武器/)
  assert.ok(calls.some(([path]) => path === '/api/accounts/s/roles/role-s/endfield/skland/operators/op'))
  button(root, '抽卡统计').props.onClick(); await settle()
  const records = nodes(root, 'details').find(node => content(node).includes('逐条记录'))
  assert.ok(records, 'the complete gacha panel still offers the ledger')
  records.props.onToggle({ target: { open: true } }); await settle()
  assert.ok(calls.some(([path]) => path.startsWith('/api/accounts/h/roles/role-h/endfield/gacha/records')))
  assert.ok(calls.every(([path]) => !path.startsWith('/api/endfield/')))
})

test('a profile failure preserves gacha, and different-role data cannot appear in the merged profile', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  setAccountScope({ account_id: 'h', role_id: 'role-h', provider: 'hypergryph', sources: { hypergryph: { account_id: 'h', role_id: 'role-h', provider: 'hypergryph' }, skland: { account_id: 's', role_id: 'role-s', provider: 'skland' } } })
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ supported: false })))
  const props = reactive({ account: h, role: 'role-h', sources, snapshots: { account: passport, gacha }, sourceSnapshots: structuredClone(sourceSnapshots) })
  const root = mount(t, Card, props); await settle()
  assert.match(content(root), /同角色档案/); assert.match(content(root), /已记录寻访 12/)
  props.sourceSnapshots.skland.account = { ...profile, state: 'error', stale: true, error: '来源暂时不可用' }
  await settle()
  assert.match(content(root), /同角色档案/); assert.match(content(root), /已记录寻访 12/)
  assert.match(content(root), /森空岛档案：更新失败/)
  props.sourceSnapshots.skland.account = { ...profile, role_id: 'another-role', payload: { base: { name: '不应显示的角色' } } }
  await settle()
  assert.doesNotMatch(content(root), /不应显示的角色|今日档案/)
  assert.match(content(root), /已记录寻访 12/)
})

test('role selection removes both old sources before another character has loaded', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const other = account('hypergryph', 'other', '9002'), pending = []
  t.mock.method(globalThis, 'fetch', async path => {
    if (path.startsWith('/api/accounts/other/roles/') && path.includes('/snapshot/')) await new Promise(resolve => pending.push(resolve))
    const data = path === '/api/identity/me' ? { user_id: 'owner' } : path.endsWith('/csrf') ? { csrf_token: 'fixture' }
      : path === '/api/accounts' ? { accounts: [h, s, other] }
      : path === '/api/accounts/h/roles/role-h/snapshot/account' ? passport
      : path === '/api/accounts/h/roles/role-h/snapshot/gacha' ? gacha
      : path === '/api/accounts/s/roles/role-s/snapshot/account' ? profile
      : { state: 'never', payload: null, supported: false }
    return new Response(JSON.stringify(data))
  })
  const root = mount(t, App); await settle(); button(root, '终末地').props.onClick(); await settle()
  assert.match(content(root), /同角色档案/); assert.match(content(root), /已记录寻访 12/)
  choose(root, '查看角色', 'other:role-other'); await settle()
  assert.doesNotMatch(content(root), /同角色档案|鹰角本人|已记录寻访 12/)
  assert.match(content(root), /需要补授权：森空岛档案/)
  assert.ok(nodes(root, 'a').some(node => node.props.href === '#/accounts?focus=skland' && /一键连接森空岛档案/.test(content(node))), 'the merged partner of another character is not borrowed')
  for (const finish of pending) finish()
  await settle()
})

for (const hasPartner of [true, false]) test(`revoking the selected source ${hasPartner ? 'keeps its verified partner visible' : 'does not switch to another character during polling'}`, async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval'] })
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  let revoked = false
  const other = account('hypergryph', 'other', '9002'), calls = []
  t.mock.method(globalThis, 'fetch', async path => {
    calls.push(path)
    const data = path === '/api/identity/me' ? { user_id: 'owner' } : path.endsWith('/csrf') ? { csrf_token: 'fixture' }
      : path === '/api/accounts' ? { accounts: [revoked ? { ...h, state: 'revoked', version: 2 } : h, ...(hasPartner ? [s] : []), other] }
      : path === '/api/accounts/h/roles/role-h/snapshot/account' ? passport
      : path === '/api/accounts/h/roles/role-h/snapshot/gacha' ? gacha
      : path === '/api/accounts/s/roles/role-s/snapshot/account' ? profile
      : path.startsWith('/api/accounts/other/roles/') ? envelope('other', null)
      : { state: 'never', payload: null, supported: false }
    return new Response(JSON.stringify(data))
  })
  const root = mount(t, App); await settle(); button(root, '终末地').props.onClick(); await settle()
  calls.length = 0; revoked = true
  t.mock.timers.tick(60000); await settle()
  assert.ok(!calls.some(path => path.startsWith('/api/accounts/other/roles/')), 'background polling must not choose a different character')
  assert.doesNotMatch(content(root), /鹰角本人|已记录寻访 12/)
  if (hasPartner) assert.match(content(root), /同角色档案/)
  else {
    assert.match(content(root), /当前角色的授权已失效/)
    assert.ok(nodes(root, 'ul').some(node => node.props['aria-label'] === '查看角色'))
  }
})

function unpairedFetch(t, rows, calls = []) {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    calls.push([path, options.method])
    const data = path === '/api/identity/me' ? { user_id: 'owner' } : path.endsWith('/csrf') ? { csrf_token: 'fixture' }
      : path === '/api/accounts' ? { accounts: rows }
      : path === '/api/accounts/h/roles/role-h/snapshot/account' ? passport
      : path === '/api/accounts/h/roles/role-h/snapshot/gacha' ? gacha
      : path === '/api/accounts/s/roles/role-s/snapshot/account' ? profile
      : path.endsWith('/operators/op') ? { operator: { name: '合并干员', weapon: { name: '同角色武器', level: 20 } } }
      : { state: 'never', payload: null, supported: false }
    return new Response(JSON.stringify(data))
  })
  return calls
}
const note = root => nodes(root, 'p').find(node => node.props.role === 'note' && String(node.props.class).includes('ef-fallback-note'))

test('an unpaired entry borrows the other provider per page, says so, and keeps both entries and scopes apart', async t => {
  const unknown = { ...s, channel: 'unknown' }, calls = unpairedFetch(t, [h, unknown])
  const root = mount(t, App); await settle(); button(root, '终末地').props.onClick(); await settle()
  assert.match(content(root), /终末地 · 鹰角寻访/)
  const roleMenu = nodes(root, 'ul').find(node => node.props['aria-label'] === '查看角色')
  assert.deepEqual(nodes(roleMenu, 'li').map(node => node.props['data-value']), ['h:role-h', 's:role-s'])
  assert.equal(content(note(root)), '本页使用森空岛档案「共同角色 · 渠道未提供」，与当前鹰角寻访未配对为同一角色')
  assert.match(content(root), /同角色档案/); assert.match(content(root), /已记录寻访 12/)
  assert.doesNotMatch(content(root), /需要补授权/)
  button(root, '全员练度').props.onClick(); await tick()
  assert.ok(note(root)); assert.match(content(root), /合并干员/)
  button(root, '查看配装').props.onClick(); await settle()
  assert.ok(calls.some(([path]) => path === '/api/accounts/s/roles/role-s/endfield/skland/operators/op'))
  button(root, '抽卡统计').props.onClick(); await tick()
  assert.equal(note(root), undefined, 'gacha is the selected entry\'s own data')
  choose(root, '查看角色', 's:role-s'); await settle()
  assert.match(content(root), /终末地 · 森空岛档案/)
  button(root, '抽卡统计').props.onClick(); await settle()
  assert.equal(content(note(root)), '本页使用鹰角寻访「共同角色 · B 服」，与当前森空岛档案未配对为同一角色')
  assert.match(content(root), /鹰角本人 · 角色编号 9001/)
  assert.ok(calls.every(([path]) => !path.startsWith('/api/endfield/')))
})

test('with several unpaired candidates nothing is borrowed and the guide lists them for 查看角色', async t => {
  const unknown = { ...s, channel: 'unknown' }, second = { ...unknown, account_id: 's2', grant_id: 'grant-s2', roles: [{ ...unknown.roles[0], role_id: 'role-s2' }] }
  const calls = unpairedFetch(t, [h, unknown, second])
  const root = mount(t, App); await settle(); button(root, '终末地').props.onClick(); await settle()
  assert.equal(note(root), undefined)
  assert.match(content(root), /请在“查看角色”中选择对应角色/)
  const guide = nodes(root, 'section').find(node => node.props['aria-label'] === '终末地授权引导')
  assert.deepEqual(nodes(guide, 'li').map(content), ['共同角色 · 渠道未提供 · 森空岛档案', '共同角色 · 渠道未提供 · 森空岛档案'])
  assert.doesNotMatch(content(root), /同角色档案/)
  assert.ok(calls.every(([path]) => !path.includes('/endfield/skland/')))
})

test('a user with only one side sees the guide for the other side instead of a borrowed page', async t => {
  unpairedFetch(t, [s])
  const root = mount(t, App); await settle(); button(root, '终末地').props.onClick(); await settle()
  assert.match(content(root), /同角色档案/); assert.equal(note(root), undefined)
  assert.doesNotMatch(content(root), /需要补授权/)
  button(root, '抽卡统计').props.onClick(); await tick()
  assert.match(content(root), /需要补授权：鹰角寻访/); assert.match(content(root), /寻访抽卡统计/)
  assert.ok(nodes(root, 'a').some(node => node.props.href === '#/accounts' && /前往账号与授权/.test(content(node))))
})
