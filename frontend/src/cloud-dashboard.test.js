import test from 'node:test'
import assert from 'node:assert/strict'
import { configureHttpClient, requestJson, getAccountScope } from './http-client.js'
import { createCloudDashboard } from './cloud-dashboard.js'

const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }
const account = { account_id: 'a', provider: 'kuro', roles: [{ role_id: 'r', is_default: true }] }
function setup(t, api) {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] })
  const dashboard = createCloudDashboard(api)
  t.after(dashboard.dispose)
  dashboard.state.user = { user_id: 'A' }; dashboard.selectAccount(account)
  dashboard.state.snapshots.account = { payload: { nickname: 'old' }, state: 'ok', fetched_at: '2026-10-12T22:40:00+08:00' }
  return dashboard
}
const snapshot = (refresh_state, state = 'ok', nickname = 'new') => ({ payload: { nickname }, state, poll_status: { refresh_state, state } })

test('same-owner session checks do not orphan an in-flight snapshot', async t => {
  let finish
  const d = createCloudDashboard({ getMe: async () => ({ user_id:'A' }), obtainCsrf: async () => 'csrf',
    getAccounts: async () => ({ accounts:[account] }), getAccountSnapshot: () => new Promise(resolve => { finish=resolve }) })
  t.after(d.dispose)
  await d.initialize(); const pending=d.loadSnapshot('account')
  await d.initialize(); finish(snapshot('idle')); await pending
  assert.equal(d.state.readStates.account.status,'success')
  assert.equal(d.state.snapshots.account.payload.nickname,'new')
})

test('a session check cannot restore a cleared website identity', async t => {
  let finish
  const d=createCloudDashboard({getMe:()=>new Promise(resolve=>{finish=resolve}),obtainCsrf:async()=> 'csrf',getAccounts:async()=>({accounts:[account]})})
  t.after(d.dispose)
  const pending=d.initialize();d.clear();finish({user_id:'A'});await pending
  assert.equal(d.state.user,null)
})

test('overview and selected page coalesce only the same scoped snapshot GET', async t=>{
 let finish,calls=0
 const dashboard=setup(t,{getAccountSnapshot:()=>{calls++;return new Promise(resolve=>{finish=resolve})}})
 dashboard.state.snapshots={}
 dashboard.state.accounts=[{...account,capabilities:['account']}]
 const page=dashboard.loadSnapshot('account'),overview=dashboard.loadOverview()
 await flush();assert.equal(calls,1)
 finish(snapshot('idle'));await Promise.all([page,overview])
 assert.equal(dashboard.state.overview.a.snapshots.account.payload.nickname,'new')
})

test('overview displays each capability as it arrives while another read is pending', async t => {
  let finish
  const dashboard = createCloudDashboard({ getAccountSnapshot: async (_id, _role, cap) => {
    if(cap === 'account') return new Promise(resolve => { finish = resolve })
    return { state:'ok', payload:{ current:123, maximum:240 } }
  } })
  t.after(dashboard.dispose)
  dashboard.state.user={user_id:'fixture-user'}
  dashboard.state.accounts=[{...account,capabilities:['account','stamina'],version:1,grant_id:'fixture-grant'}]
  const pending=dashboard.loadOverview(); await flush()
  assert.equal(dashboard.state.overview.a?.snapshots.stamina?.payload.current,123)
  assert.equal(dashboard.state.overviewLoading,true)
  finish({state:'ok',payload:{nickname:'fixture'}}); await pending
})

test('snapshot read state is loading until success and is cleared on a scope switch', async t => {
  let finish
  const dashboard=setup(t,{getAccountSnapshot:()=>new Promise(resolve=>{finish=resolve})})
  const pending=dashboard.loadSnapshot('roles')
  assert.equal(dashboard.state.readStates?.roles?.status,'loading')
  finish({state:'ok',payload:[]}); await pending
  assert.equal(dashboard.state.readStates.roles.status,'success')
  dashboard.selectAccount({...account,account_id:'other'})
  assert.deepEqual(dashboard.state.readStates,{})
})

test('accepted refresh reads queued, running and idle snapshots promptly without another upstream refresh', async t => {
  let requests = 0, reads = 0
  const results = [snapshot('queued', 'ok', 'old'), snapshot('running', 'ok', 'old'), snapshot('idle')]
  const dashboard = setup(t, { refreshAccount: async () => { requests++; return { state: 'queued' } }, getAccountSnapshot: async () => { reads++; return results.shift() } })
  await dashboard.refresh('account')
  assert.equal(dashboard.state.snapshots.account.payload.nickname, 'old')
  t.mock.timers.tick(0); await flush()
  assert.equal(reads, 1); assert.match(dashboard.state.refreshing.account, /排队/)
  await dashboard.refresh('account'); assert.equal(requests, 1)
  t.mock.timers.tick(2000); await flush()
  assert.match(dashboard.state.refreshing.account, /刷新中/)
  t.mock.timers.tick(2000); await flush()
  assert.equal(dashboard.state.refreshing.account, '')
  assert.equal(dashboard.state.snapshots.account.payload.nickname, 'new')
  t.mock.timers.tick(60000); await flush(); assert.equal(reads, 3)
})

for (const readFailure of [false, true]) test(`${readFailure ? 'snapshot read' : 'idle collection'} failure preserves data and stops tracking with explicit failure`, async t => {
    let reads = 0
    const dashboard = setup(t, { refreshAccount: async () => ({ state: 'coalesced' }), getAccountSnapshot: async () => {
      reads++; if (readFailure) throw new Error('网络连接失败')
      return snapshot('idle', 'error', 'old')
    } })
    await dashboard.refresh('account'); t.mock.timers.tick(0); await flush()
    assert.equal(dashboard.state.snapshots.account.payload.nickname, 'old')
    assert.match(dashboard.state.refreshing.account, /失败.*上次/)
    t.mock.timers.tick(60000); await flush(); assert.equal(reads, 1)
    dashboard.dispose()
})

test('bounded tracking stops even if a read hangs; late read cannot replace a newer observation', async t => {
  let finish, reads = 0
  const dashboard = setup(t, { refreshAccount: async () => ({ state: 'queued' }), getAccountSnapshot: () => { reads++; return new Promise(resolve => { finish = resolve }) } })
  await dashboard.refresh('account'); t.mock.timers.tick(0); await flush()
  t.mock.timers.tick(30000); await flush()
  assert.match(dashboard.state.refreshing.account, /仍未完成.*重试/)
  assert.notEqual(dashboard.state.readStates.account?.status,'loading')
  assert.equal(dashboard.state.snapshots.account.payload.nickname, 'old')
  finish(snapshot('idle', 'ok', 'late')); await flush()
  assert.equal(dashboard.state.snapshots.account.payload.nickname, 'old')
  assert.equal(reads, 1)
})

test('switching user cancels tracking and ignores old snapshot and receipt responses', async t => {
  let finish, reads = 0
  const dashboard = setup(t, { refreshAccount: async () => ({ state: 'queued' }), getAccountSnapshot: () => { reads++; return new Promise(resolve => { finish = resolve }) } })
  await dashboard.refresh('account'); t.mock.timers.tick(0); await flush()
  dashboard.clear(); dashboard.state.user = { user_id: 'B' }; dashboard.selectAccount({ ...account, account_id: 'b' })
  finish(snapshot('idle', 'ok', 'private-A')); await flush(); t.mock.timers.tick(60000); await flush()
  assert.deepEqual(dashboard.state.snapshots, {}); assert.deepEqual(dashboard.state.refreshing, {}); assert.equal(reads, 1)
})

test('reads started before or during refresh acceptance cannot overwrite a newer snapshot', async t => {
  let finishOld, finishReceipt, finishDuring, count = 0
  const dashboard = setup(t, { refreshAccount: () => new Promise(resolve => { finishReceipt = resolve }), getAccountSnapshot: () => {
    count++
    if (count === 1) return new Promise(resolve => { finishOld = resolve })
    if (count === 2) return new Promise(resolve => { finishDuring = resolve })
    return Promise.resolve(snapshot('idle'))
  } })
  const older = dashboard.loadSnapshot('account'), refresh = dashboard.refresh('account'), during = dashboard.loadSnapshot('account')
  finishReceipt({ state: 'queued' }); await refresh
  t.mock.timers.tick(0); await flush()
  finishOld(snapshot('idle', 'ok', 'old-read')); finishDuring(snapshot('idle', 'ok', 'during-post')); await Promise.all([older, during])
  assert.equal(dashboard.state.snapshots.account.payload.nickname, 'new')
  assert.equal(dashboard.state.refreshing.account, '')
})

test('queued tracking has a read limit and a later manual read can settle the receipt', async t => {
  let reads = 0, done = false
  const dashboard = setup(t, { refreshAccount: async () => ({ state: 'queued' }), getAccountSnapshot: async () => { reads++; return snapshot(done ? 'idle' : 'queued', 'ok', done ? 'new' : 'old') } })
  await dashboard.refresh('account'); t.mock.timers.tick(0); await flush()
  for (let i = 0; i < 9; i++) { t.mock.timers.tick(2000); await flush() }
  assert.equal(reads, 10); assert.match(dashboard.state.refreshing.account, /仍未完成/)
  assert.equal(dashboard.state.refreshPending.account, false)
  t.mock.timers.tick(60000); await flush(); assert.equal(reads, 10)
  done = true; await dashboard.loadSnapshot('account')
  assert.equal(dashboard.state.refreshing.account, ''); assert.equal(dashboard.state.snapshots.account.payload.nickname, 'new')
})

test('rejected refresh preserves snapshots; logout or disposal drops a pending receipt without starting reads', async t => {
  let finish, reads = 0, reject = true
  const dashboard = setup(t, { refreshAccount: () => reject ? Promise.reject(new Error('刷新请求失败')) : new Promise(resolve => { finish = resolve }), getAccountSnapshot: async () => { reads++; return snapshot('idle') }, logoutSite: async () => ({}) })
  await dashboard.refresh('account')
  assert.match(dashboard.state.error, /刷新请求失败/); assert.equal(dashboard.state.refreshPending.account, false)
  assert.equal(dashboard.state.snapshots.account.payload.nickname, 'old')
  reject = false
  const pending = dashboard.refresh('account'); await dashboard.logout()
  finish({ state: 'queued' }); await pending; t.mock.timers.tick(60000); await flush()
  assert.equal(reads, 0); assert.deepEqual(dashboard.state.refreshing, {})
  dashboard.state.user = { user_id: 'B' }; dashboard.selectAccount(account)
  const pendingDispose = dashboard.refresh('account'); dashboard.dispose()
  finish({ state: 'queued' }); await pendingDispose; t.mock.timers.tick(60000); await flush()
  assert.equal(reads, 0); assert.deepEqual(dashboard.state.refreshing, {})
})

test('the error of a failed session check does not outlive the next successful one', async t => {
  let online = true
  const dashboard = createCloudDashboard({ getMe: async () => { if (!online) throw new TypeError('无法连接服务，请稍后重试'); return { user_id: 'A' } },
    obtainCsrf: async () => 'csrf', getAccounts: async () => ({ accounts: [account] }) })
  t.after(dashboard.dispose)
  await dashboard.initialize()
  online = false; await dashboard.initialize()
  assert.equal(dashboard.state.error, '无法连接服务，请稍后重试')
  assert.equal(dashboard.state.user.user_id, 'A', 'the signed-in page stays while the service is unreachable')
  online = true; await dashboard.initialize()
  assert.equal(dashboard.state.error, '', 'the banner of a past failure is still shown')
})

const unreachable = () => new TypeError('无法连接服务，请稍后重试')
const answered = status => Object.assign(new Error(`HTTP ${status}`), { status })
for (const [name, failure, expected] of [['the service cannot be reached', unreachable(), true], ['the service answers with an error', answered(503), true], ['the site session is already gone (401)', answered(401), false]])
  test(`logout when ${name}: the private state is cleared at once and ${expected ? 'a retry stays on offer' : 'nothing is left to retry'}`, async t => {
    let outcome = failure
    const dashboard = createCloudDashboard({ logoutSite: async () => { if (outcome) throw outcome; return {} } })
    t.after(dashboard.dispose)
    dashboard.state.user = { user_id: 'A' }; dashboard.selectAccount(account); dashboard.state.snapshots.account = { payload: { nickname: 'old' } }
    await dashboard.logout()
    assert.equal(dashboard.state.user, null); assert.deepEqual(dashboard.state.snapshots, {})
    assert.equal(dashboard.state.logoutFailed, expected)
    if (!expected) return
    dashboard.clear(); assert.equal(dashboard.state.logoutFailed, true, 'a session reset must not turn a failed logout into a signed-out page')
    outcome = null
    const retry = dashboard.logout(); assert.equal(dashboard.state.logoutFailed, false, 'the retry is under way'); await retry
    assert.equal(dashboard.state.logoutFailed, false); assert.equal(dashboard.state.error, '')
  })


test('session reinitialization forgets CSRF after another tab rotates its cookie, without a request of its own',async t=>{
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
  let owner='A',csrfReads=0
  t.mock.method(globalThis,'fetch',async(path,options)=>{
    if(path.endsWith('/csrf')){csrfReads++;return new Response(JSON.stringify({csrf_token:`csrf-${owner}`}))}
    if(options.method==='POST')return new Response(JSON.stringify({ok:true}),{status:options.headers['X-CSRF-Token']===`csrf-${owner}`?200:403})
    return new Response(JSON.stringify(path==='/api/identity/me'?{user_id:owner}:{accounts:[]}))
  })
  const d=createCloudDashboard();t.after(d.dispose)
  await d.initialize();assert.equal(csrfReads,0,'a session check alone never asks for a CSRF token')
  assert.deepEqual(await requestJson('/api/accounts/synthetic/roles/r/refresh/account',{method:'POST'}),{ok:true})
  owner='B';await d.initialize();assert.equal(csrfReads,1)
  assert.deepEqual(await requestJson('/api/accounts/synthetic/roles/r/refresh/account',{method:'POST'}),{ok:true})
  assert.equal(csrfReads,2)
})

const endfieldAccounts = () => ['hypergryph', 'skland'].map((provider, i) => ({
  account_id: provider, provider, game: 'endfield', state: 'active', version: 1, grant_id: `${provider}-grant`, channel: 'bilibili', server: '1',
  capabilities: i ? ['account'] : ['account', 'gacha'], roles: [{ role_id: `${provider}-role`, game_uid: '123', is_default: true }],
}))
const endfieldSnapshot = (account, role, value = account) => ({ account_id: account, role_id: role, payload: { value }, state: 'ok', poll_status: { refresh_state: 'idle' } })
function endfieldSetup(t, api = {}) {
  const dashboard = createCloudDashboard(api); t.after(dashboard.dispose)
  dashboard.state.user = { user_id: 'u' }; dashboard.state.accounts = endfieldAccounts(); dashboard.selectAccount(dashboard.state.accounts[0])
  return dashboard
}
test('Endfield snapshots load concurrently by source and preserve the selected physical snapshot contract', async t => {
  const pending = []
  const dashboard = endfieldSetup(t, { getAccountSnapshot: (account, role, cap) => new Promise(resolve => pending.push({ account, role, cap, resolve })) })
  const loading = dashboard.loadSelectedSnapshots()
  assert.equal(pending.length, 3)
  for (const { account, role, cap, resolve } of pending.reverse()) resolve(endfieldSnapshot(account, role, `${account}-${cap}`))
  await loading
  assert.equal(dashboard.state.sourceSnapshots.hypergryph.account.payload.value, 'hypergryph-account')
  assert.equal(dashboard.state.sourceSnapshots.skland.account.payload.value, 'skland-account')
  assert.equal(dashboard.state.snapshots.account.payload.value, 'hypergryph-account')
  assert.equal(dashboard.state.snapshots.gacha.payload.value, 'hypergryph-gacha')
  dashboard.selectAccount(dashboard.state.accounts[1])
  assert.equal(dashboard.state.sources.hypergryph.account.account_id, 'hypergryph')
})
test('one source read failure preserves its successful payload and leaves the other source intact', async t => {
  let failure = false
  const dashboard = endfieldSetup(t, { getAccountSnapshot: async (account, role) => {
    if (failure && account === 'skland') throw new Error('来源暂时不可用')
    return endfieldSnapshot(account, role, failure ? 'fresh' : 'old')
  } })
  await dashboard.loadSelectedSnapshots(); failure = true; await dashboard.loadSelectedSnapshots()
  assert.equal(dashboard.state.sourceSnapshots.skland.account.payload.value, 'old')
  assert.equal(dashboard.state.sourceSnapshots.skland.account.state, 'error')
  assert.equal(dashboard.state.sourceSnapshots.hypergryph.account.payload.value, 'fresh')
})
test('Endfield rejects an envelope for another account or role before its payload enters either cache', async t => {
  let mismatch = 'account'
  const dashboard = endfieldSetup(t, { getAccountSnapshot: async (account, role) => endfieldSnapshot(mismatch === 'account' ? 'foreign' : account, mismatch === 'role' ? 'foreign' : role, 'foreign-secret') })
  for (mismatch of ['account', 'role']) {
    await dashboard.loadSelectedSnapshots()
    for (const source of Object.values(dashboard.state.sourceSnapshots)) for (const result of Object.values(source)) {
      assert.equal(result.payload, null); assert.match(result.error, /不匹配/)
      assert.notEqual(result.account_id, 'foreign'); assert.notEqual(result.role_id, 'foreign')
    }
    assert.equal(dashboard.state.snapshots.account.payload, null)
  }
})
for (const change of ['version', 'grant_id', 'state', 'role']) test(`a related Endfield authorization ${change} change clears both sources and rejects late data`, async t => {
  const finishes = []
  let rows = endfieldAccounts()
  const dashboard = endfieldSetup(t, { getAccounts: async () => ({ accounts: rows }), getAccountSnapshot: (account, role) => new Promise(resolve => finishes.push(() => resolve(endfieldSnapshot(account, role, 'old-secret')))) })
  dashboard.state.sourceSnapshots = { hypergryph: { account: { payload: 'old' } }, skland: { account: { payload: 'old' } } }
  const pending = dashboard.loadSelectedSnapshots()
  rows = endfieldAccounts()
  if (change === 'role') rows[1].roles = [{ role_id: 'new-role', game_uid: '456' }]
  else rows[1][change] = ({ version: 2, grant_id: 'new-grant', state: 'revoked' })[change]
  await dashboard.loadAccounts()
  assert.deepEqual(dashboard.state.sourceSnapshots, {}); assert.deepEqual(dashboard.state.snapshots, {})
  finishes.forEach(finish => finish()); await pending
  assert.deepEqual(dashboard.state.sourceSnapshots, {}); assert.deepEqual(dashboard.state.snapshots, {})
})
test('ordinary Endfield account polling retains snapshots while a role switch or logout drops both sources', async t => {
  const dashboard = endfieldSetup(t, { getAccounts: async () => ({ accounts: endfieldAccounts() }), logoutSite: async () => ({}), getAccountSnapshot: async (account, role) => endfieldSnapshot(account, role) })
  await dashboard.loadSelectedSnapshots(); const before = dashboard.state.revision
  await dashboard.loadAccounts()
  assert.equal(dashboard.state.revision, before)
  assert.equal(dashboard.state.sourceSnapshots.skland.account.payload.value, 'skland')
  dashboard.selectAccount(dashboard.state.accounts[0], 'another-role')
  assert.deepEqual(dashboard.state.sources, {}); assert.deepEqual(dashboard.state.sourceSnapshots, {})
  dashboard.selectAccount(dashboard.state.accounts[0]); await dashboard.loadSelectedSnapshots(); await dashboard.logout()
  assert.deepEqual(dashboard.state.sources, {}); assert.deepEqual(dashboard.state.sourceSnapshots, {})
})
test('Endfield refreshes track both account capabilities independently and keep a successful source on failure', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] })
  const receipts = []
  const dashboard = endfieldSetup(t, { refreshAccount: async (account, role, cap) => { receipts.push([account, role, cap]); return { state: 'queued' } }, getAccountSnapshot: async (account, role) => {
    if (account === 'skland') throw new Error('来源失败')
    return endfieldSnapshot(account, role)
  } })
  dashboard.state.sourceSnapshots.skland = { account: { payload: 'last-success' } }
  await dashboard.refreshSelected()
  assert.equal(receipts.length, 3)
  assert.equal(dashboard.state.refreshPending['hypergryph:account'], true); assert.equal(dashboard.state.refreshPending['skland:account'], true)
  t.mock.timers.tick(0); await flush()
  assert.equal(dashboard.state.refreshPending['hypergryph:account'], false); assert.equal(dashboard.state.refreshPending['skland:account'], false)
  assert.equal(dashboard.state.sourceSnapshots.hypergryph.account.payload.value, 'hypergryph')
  assert.equal(dashboard.state.sourceSnapshots.skland.account.payload, 'last-success')
  assert.match(dashboard.state.refreshing['skland:account'], /失败/)
})

for (const change of ['revoked', 'deleted', 'role-unavailable']) test(`an unavailable selected Endfield source (${change}) continues on its previously verified healthy partner`, async t => {
  let rows = endfieldAccounts()
  rows[1].authorization_source = 'manual'
  const calls = []
  const dashboard = endfieldSetup(t, { getAccounts: async () => ({ accounts: rows }), getAccountSnapshot: async (account, role, cap) => {
    calls.push([account, role, cap]); return endfieldSnapshot(account, role, 'healthy-partner')
  } })
  // The prior association, rather than the order of the replacement listing,
  // determines the only acceptable fallback.
  rows = endfieldAccounts(); rows[1].authorization_source = 'manual'
  if (change === 'revoked') rows[0].state = 'revoked'
  if (change === 'deleted') rows.shift()
  if (change === 'role-unavailable') rows[0].roles = [{ role_id: 'another-character', game_uid: 'different' }]
  rows.unshift({ ...endfieldAccounts()[0], account_id: 'unrelated', roles: [{ role_id: 'unrelated-role', game_uid: '999' }] })
  await dashboard.loadAccounts()
  assert.equal(dashboard.state.selected.account_id, 'skland')
  assert.equal(dashboard.state.role, 'skland-role')
  assert.deepEqual(Object.keys(dashboard.state.sources), ['skland'])
  assert.deepEqual(calls, [['skland', 'skland-role', 'account']])
  assert.equal(dashboard.state.snapshots.account.payload.value, 'healthy-partner')
  assert.equal(dashboard.state.sourceSnapshots.skland.account.account_id, 'skland')
})
for (const change of ['uid', 'channel', 'server', 'role', 'missing-uid', 'owner', 'ambiguous-role', 'ambiguous-account', 'revoked']) test(`an old Endfield partner with ${change} cannot take over the selected character`, async t => {
  let rows = endfieldAccounts(), reads = 0
  const dashboard = endfieldSetup(t, { getAccounts: async () => ({ accounts: rows }), getAccountSnapshot: async (account, role) => {
    reads++; return endfieldSnapshot(account, role)
  } })
  rows = endfieldAccounts(); rows[0].state = 'revoked'
  if (change === 'uid') rows[1].roles[0].game_uid = 'changed'
  if (change === 'channel') rows[1].channel = 'official'
  if (change === 'server') rows[1].server = '2'
  if (change === 'role') rows[1].roles[0].role_id = 'new-opaque-role'
  if (change === 'missing-uid') delete rows[1].roles[0].game_uid
  if (change === 'owner') rows[1].user_id = 'other-user'
  if (change === 'ambiguous-role') rows[1].roles.push({ role_id: 'second', game_uid: '123' })
  if (change === 'ambiguous-account') rows.push({ ...rows[1], account_id: 'second-skland' })
  if (change === 'revoked') rows[1].state = 'revoked'
  await dashboard.loadAccounts()
  assert.equal(dashboard.state.selected, null)
  assert.deepEqual(dashboard.state.sources, {}); assert.deepEqual(dashboard.state.sourceSnapshots, {})
  assert.equal(reads, 0)
})
test('removing an Endfield source without a prior verified partner does not select a different character', async t => {
  let rows = endfieldAccounts()
  rows[1].roles[0].game_uid = 'different-character'
  const dashboard = createCloudDashboard({ getAccounts: async () => ({ accounts: rows }) }); t.after(dashboard.dispose)
  dashboard.state.user = { user_id: 'u' }; dashboard.state.accounts = rows; dashboard.selectAccount(rows[0])
  assert.deepEqual(Object.keys(dashboard.state.sources), ['hypergryph'])
  rows = [rows[1]]; await dashboard.loadAccounts()
  assert.equal(dashboard.state.selected, null); assert.deepEqual(dashboard.state.sources, {})
  const revision = dashboard.state.revision
  await dashboard.loadAccounts()
  assert.equal(dashboard.state.selected, null); assert.equal(dashboard.state.revision, revision, 'a later poll must not choose the unrelated character')
  dashboard.selectAccount(rows[0])
  assert.equal(dashboard.state.selected.account_id, 'skland', 'an explicit selection still works')
})
test('a selected active Endfield source stays selected when only its authorization version changes', async t => {
  let rows = endfieldAccounts(), reads = 0
  const dashboard = endfieldSetup(t, { getAccounts: async () => ({ accounts: rows }), getAccountSnapshot: async () => { reads++ } })
  rows[0].version = 2; await dashboard.loadAccounts()
  assert.equal(dashboard.state.selected.account_id, 'hypergryph'); assert.equal(dashboard.state.selected.version, 2)
  assert.equal(dashboard.state.role, 'hypergryph-role'); assert.equal(reads, 0)
})
test('old dual-source reads and refresh receipts cannot restore a failed source after healthy-source migration', async t => {
  const oldReads = [], receipts = []
  let rows = endfieldAccounts(), hold = true
  const dashboard = endfieldSetup(t, { getAccounts: async () => ({ accounts: rows }),
    getAccountSnapshot: (account, role) => hold ? new Promise(resolve => oldReads.push(() => resolve(endfieldSnapshot(account, role, 'late-old-secret')))) : Promise.resolve(endfieldSnapshot(account, role, 'fresh-partner')),
    refreshAccount: () => new Promise(resolve => receipts.push(resolve)),
  })
  const pending = dashboard.loadSelectedSnapshots(), refresh = dashboard.refresh('account', 'hypergryph')
  rows[0].state = 'revoked'; hold = false; await dashboard.loadAccounts()
  assert.equal(dashboard.state.selected.account_id, 'skland')
  oldReads.forEach(resolve => resolve()); receipts.forEach(resolve => resolve({ state: 'queued' }))
  await Promise.all([pending, refresh])
  assert.deepEqual(Object.keys(dashboard.state.sources), ['skland'])
  assert.deepEqual(Object.keys(dashboard.state.sourceSnapshots), ['skland'])
  assert.equal(dashboard.state.snapshots.account.payload.value, 'fresh-partner')
  assert.deepEqual(dashboard.state.refreshing, {}); assert.deepEqual(dashboard.state.refreshPending, {})
})
test('an initial Endfield source failure carries only its requested account and role context with a null payload', async t => {
  const dashboard = endfieldSetup(t, { getAccountSnapshot: async () => { throw new Error('来源首次读取失败') } })
  await dashboard.loadSelectedSnapshots(); await dashboard.loadOverview()
  for (const provider of ['hypergryph', 'skland']) {
    const direct = dashboard.state.sourceSnapshots[provider].account, overview = dashboard.state.overview[provider].snapshots.account
    for (const error of [direct, overview]) {
      assert.equal(error.account_id, provider); assert.equal(error.role_id, `${provider}-role`)
      assert.equal(error.payload, null); assert.equal(error.state, 'error'); assert.equal(error.error, '来源首次读取失败')
    }
  }
})

// Unpaired: the Skland grant reports an unknown channel, so the two entries stay separate choices.
const unpairedAccounts = () => { const rows = endfieldAccounts(); rows[0].channel = 'official'; rows[1].channel = 'unknown'; return rows }
test('an unpaired Endfield entry reads the missing provider from its unique fallback scope without changing the selection', async t => {
  const reads = [], receipts = []
  const dashboard = createCloudDashboard({ getAccountSnapshot: async (account, role, cap) => { reads.push([account, role, cap]); return endfieldSnapshot(account, role) },
    refreshAccount: async (account, role, cap) => { receipts.push([account, role, cap]); return { state: 'queued' } } })
  t.after(dashboard.dispose)
  dashboard.state.user = { user_id: 'u' }; dashboard.state.accounts = unpairedAccounts(); dashboard.selectAccount(dashboard.state.accounts[0])
  assert.equal(dashboard.state.selected.account_id, 'hypergryph'); assert.equal(dashboard.state.role, 'hypergryph-role')
  assert.equal(dashboard.state.sources.skland.account.account_id, 'skland'); assert.equal(dashboard.state.sources.skland.fallback, true)
  assert.equal(dashboard.state.sources.hypergryph.fallback, undefined)
  assert.deepEqual(getAccountScope().sources.skland, { user_id: 'u', account_id: 'skland', role_id: 'skland-role', provider: 'skland', version: 1, grant_id: 'skland-grant' })
  await dashboard.loadSelectedSnapshots()
  assert.deepEqual(reads.sort(), [['hypergryph', 'hypergryph-role', 'account'], ['hypergryph', 'hypergryph-role', 'gacha'], ['skland', 'skland-role', 'account']])
  assert.equal(dashboard.state.sourceSnapshots.skland.account.account_id, 'skland')
  assert.equal(dashboard.state.snapshots.account.account_id, 'hypergryph', 'fallback data never enters the selected snapshot')
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] })
  await dashboard.refreshSelected()
  assert.deepEqual(receipts.sort(), [['hypergryph', 'hypergryph-role', 'account'], ['hypergryph', 'hypergryph-role', 'gacha'], ['skland', 'skland-role', 'account']])
  assert.equal(dashboard.state.refreshPending['skland:account'], true)
})
test('a fallback is dropped when it becomes ambiguous or paired, and never takes over a removed selection', async t => {
  let rows = unpairedAccounts()
  const dashboard = createCloudDashboard({ getAccounts: async () => ({ accounts: rows }), getAccountSnapshot: async (account, role) => endfieldSnapshot(account, role) })
  t.after(dashboard.dispose)
  dashboard.state.user = { user_id: 'u' }; dashboard.state.accounts = rows; dashboard.selectAccount(rows[0])
  rows = [...unpairedAccounts(), { ...unpairedAccounts()[1], account_id: 'second-skland' }]; await dashboard.loadAccounts()
  assert.deepEqual(Object.keys(dashboard.state.sources), ['hypergryph'])
  rows = unpairedAccounts(); await dashboard.loadAccounts()
  assert.equal(dashboard.state.sources.skland.fallback, true)
  const revision = dashboard.state.revision
  rows = unpairedAccounts(); rows[1].channel = 'official'; await dashboard.loadAccounts()
  assert.equal(dashboard.state.sources.skland.fallback, undefined, 'the same scope, now paired, is no longer a fallback')
  assert.ok(dashboard.state.revision > revision)
  rows = unpairedAccounts(); await dashboard.loadAccounts()
  rows = unpairedAccounts(); rows[0].state = 'revoked'; await dashboard.loadAccounts()
  assert.equal(dashboard.state.selected, null); assert.deepEqual(dashboard.state.sources, {})
})
