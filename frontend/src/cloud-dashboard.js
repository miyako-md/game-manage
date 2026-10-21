import { reactive } from 'vue'
import * as identity from './identity-api.js'
import * as accounts from './accounts-api.js'
import { setAccountScope, subscribeSessionInvalidation, obtainCsrf } from './http-client.js'
import { collectionState } from './snapshot-state.js'
import { endfieldPageSources } from './endfield-accounts.js'
const REFRESH_READ_INTERVAL = 2000, REFRESH_READ_LIMIT = 10, REFRESH_TRACK_TIMEOUT = 30000
export function createCloudDashboard(overrides = {}) {
  const api = { ...identity, ...accounts, obtainCsrf, ...overrides }
  const state = reactive({ user: null, accounts: [], selected: null, role: '', snapshots: {}, readStates: {}, sources: {}, sourceSnapshots: {}, overview: {}, overviewLoading: false, sessions: [], error: '', loading: false, ready: false, logoutFailed: false, refreshing: {}, refreshPending: {}, revision: 0 })
  let epoch = 0, initializeGeneration = 0, disposed = false, keepSelectionEmpty = false
  let overviewGeneration = 0
  const refreshVersions = new Map(), readVersions = new Map(), refreshJobs = new Map(), reads = new Map(), scopedReads = new Map()
  const current = version => !disposed && version === epoch
  function stopRefresh(cap, job = refreshJobs.get(cap)) {
    if (!job || refreshJobs.get(cap) !== job) return
    clearTimeout(job.timer); clearTimeout(job.deadline); refreshJobs.delete(cap); state.refreshPending[cap] = false
  }
  function stopTracking() { for (const [cap, job] of refreshJobs) { state.refreshing[cap] = '刷新结果未确认，请稍后重试。'; stopRefresh(cap, job) } }
  function clear() { keepSelectionEmpty = false; stopTracking(); reads.clear(); scopedReads.clear(); epoch++; initializeGeneration++; overviewGeneration++; state.revision++; setAccountScope(null); Object.assign(state, { user: null, accounts: [], selected: null, role: '', snapshots: {}, readStates: {}, sources: {}, sourceSnapshots: {}, overview: {}, overviewLoading: false, sessions: [], error: '', loading: false, refreshing: {}, refreshPending: {} }) }
  const stop = subscribeSessionInvalidation(clear)
  async function initialize() {
    stopTracking()
    let version = ++initializeGeneration; state.loading = true
    const valid = () => !disposed && version === initializeGeneration
    try {
      const user = await api.getMe(); if (!valid()) return
      await api.obtainCsrf(true); if (!valid()) return
      if (state.user && state.user.user_id !== user.user_id) { clear(); version = initializeGeneration }
      state.user = user; state.error = ''; await loadAccounts()
    }
    catch (error) { if (valid() && error.status !== 401 && error.name !== 'AbortError') state.error = error.message }
    finally { if (!disposed) state.ready = true; if (valid()) state.loading = false }
  }
  async function loadAccounts() {
    const version = epoch, user = state.user?.user_id
    if (!user) return
    try {
      const data = await api.getAccounts()
      if (!current(version) || state.user?.user_id !== user) return
      state.accounts = Array.isArray(data.accounts) ? data.accounts : []
      for (const id of Object.keys(state.overview)) {
        const row = state.accounts.find(a => a.account_id === id), cached = state.overview[id]
        if (!row || row.state === 'revoked' || cached.version !== row.version || cached.grant_id !== row.grant_id || JSON.stringify(cached.roles) !== JSON.stringify(row.roles)) delete state.overview[id]
      }
      const previous = state.selected, previousRole = state.role
      let selected = state.accounts.find(row => row.account_id === previous?.account_id), role = previousRole, migrated = false
      if (isEndfieldAccount(previous)) {
        const usable = selected?.provider === previous.provider && selected.state === 'active' && isEndfieldAccount(selected) && selected.roles?.some(row => row.role_id === role)
        if (!usable) {
          const fallback = survivingEndfieldSource(state.accounts, state.sources, previous.account_id)
          selected = fallback?.account || null; role = fallback?.role || ''; migrated = !!fallback
        }
      } else if (!keepSelectionEmpty) selected ||= state.accounts[0]
      if (!selected && !previous && keepSelectionEmpty) return
      const nextSources = endfieldPageSources(state.accounts, selected, role)
      if (selected && selected.account_id === state.selected?.account_id && authorizationKey(selected) === authorizationKey(state.selected) && sourcesKey(nextSources) === sourcesKey(state.sources)) {
        state.selected = selected; state.sources = nextSources
      } else selectAccount(selected || null, selected?.roles?.some(row => row.role_id === role) ? role : undefined)
      if (isEndfieldAccount(previous) && !selected) keepSelectionEmpty = true
      if (migrated) await loadSelectedSnapshots()
    } catch (error) { if (current(version) && error.name !== 'AbortError') state.error = error.message }
  }
  const authorizationKey = account => JSON.stringify(account && {
    account_id: account.account_id, provider: account.provider, game: account.game, channel: account.channel, server: account.server,
    user_id: account.user_id, state: account.state, version: account.version, grant_id: account.grant_id,
    roles: [...(account.roles || [])].sort((a, b) => a.role_id.localeCompare(b.role_id)), capabilities: account.capabilities,
  })
  const sourcesKey = sources => JSON.stringify(Object.keys(sources).sort().map(provider => [provider, sources[provider].role, authorizationKey(sources[provider].account), !!sources[provider].fallback]))
  const isEndfieldAccount = account => account && (account.game == null || account.game === 'endfield') && ['hypergryph', 'skland'].includes(account.provider)
  // Only the previously confirmed partner may take over. A new binding with an
  // equal display name, changed identity, missing UID or ambiguous role is not a
  // continuation of the selected character.
  function survivingEndfieldSource(rows, previousSources, selectedId) {
    const candidates = []
    for (const source of Object.values(previousSources)) {
      // A page fallback was never confirmed as the same character.
      if (source.account.account_id === selectedId || source.fallback) continue
      const oldRole = source.account.roles?.find(role => role.role_id === source.role), oldUid = oldRole?.game_uid
      if (!['official', 'bilibili'].includes(source.account.channel) || !source.account.server || oldUid == null || String(oldUid) === '') continue
      const matching = rows.filter(account => isEndfieldAccount(account) && account.state === 'active' && account.provider === source.account.provider &&
        account.channel === source.account.channel && account.server === source.account.server && account.user_id === source.account.user_id)
        .flatMap(account => (account.roles || []).filter(role => role.game_uid != null && String(role.game_uid) === String(oldUid)).map(role => ({ account, role: role.role_id })))
      if (matching.length === 1 && matching[0].account.account_id === source.account.account_id && matching[0].role === source.role) candidates.push(matching[0])
    }
    return candidates.length === 1 ? candidates[0] : null
  }
  const isEndfield = () => isEndfieldAccount(state.selected)
  const scopeFor = (account, role) => ({ user_id: state.user?.user_id, account_id: account.account_id, role_id: role, provider: account.provider, version: account.version, grant_id: account.grant_id })
  function selectAccount(account, role) {
    const nextRole = role || account?.roles?.find(row => row.is_default)?.role_id || account?.roles?.[0]?.role_id || ''
    const nextSources = endfieldPageSources(state.accounts, account, nextRole)
    if (account && state.selected && nextRole === state.role && authorizationKey(account) === authorizationKey(state.selected) && sourcesKey(nextSources) === sourcesKey(state.sources)) {
      state.selected = account; state.sources = nextSources; return
    }
    keepSelectionEmpty = false
    stopTracking(); reads.clear(); scopedReads.clear()
    epoch++; state.revision++; state.selected = account; state.role = role || account?.roles?.find(row => row.is_default)?.role_id || account?.roles?.[0]?.role_id || ''
    state.sources = endfieldPageSources(state.accounts, account, state.role)
    state.snapshots = {}; state.readStates = {}; state.sourceSnapshots = {}; state.refreshing = {}; state.refreshPending = {}; state.error = ''; state.loading = false
    const scope = account && state.role ? scopeFor(account, state.role) : null
    if (scope && isEndfield()) scope.sources = Object.fromEntries(Object.entries(state.sources).map(([provider, source]) => [provider, scopeFor(source.account, source.role)]))
    setAccountScope(scope)
  }
  function scopedSnapshot(account, role, cap) {
    const refreshKey = isEndfieldAccount(account) ? account.provider + ':' + cap : cap
    const key = JSON.stringify([epoch, state.user?.user_id, account.account_id, role, account.provider, account.channel, account.server, account.version, account.grant_id, cap, refreshVersions.get(refreshKey), state.refreshing[refreshKey] === '正在排队'])
    if (scopedReads.has(key)) return scopedReads.get(key)
    const pending = Promise.resolve(api.getAccountSnapshot(account.account_id, role, cap)).finally(() => { if (scopedReads.get(key) === pending) scopedReads.delete(key) })
    scopedReads.set(key, pending)
    return pending
  }
  function setReadState(target, cap, value) {
    state.readStates[target.key] = value
    if (target.account.account_id === state.selected?.account_id && target.role === state.role) state.readStates[cap] = value
  }
  function targetFor(cap, provider) {
    if (!state.selected || !state.role) return null
    if (!isEndfield()) return { account: state.selected, role: state.role, key: cap, provider: state.selected.provider, endfield: false }
    provider ||= state.selected.provider
    const source = state.sources[provider]
    return source && accounts.accountCapabilities(source.account).includes(cap) ? { ...source, key: `${provider}:${cap}`, provider, endfield: true } : null
  }
  const validEnvelope = (data, account, role) => data?.account_id === account.account_id && data?.role_id === role
  function storeSnapshot(target, cap, data) {
    if (target.endfield) {
      state.sourceSnapshots[target.provider] ||= {}
      state.sourceSnapshots[target.provider][cap] = data
    }
    if (target.account.account_id === state.selected?.account_id && target.role === state.role) state.snapshots[cap] = data
  }
  function previousSnapshot(target, cap) {
    return target.endfield ? state.sourceSnapshots[target.provider]?.[cap] : state.snapshots[cap]
  }
  function selectedTasks(action) {
    if (!isEndfield()) return Promise.all(accounts.accountCapabilities(state.selected).map(cap => action(cap)))
    return Promise.all(Object.entries(state.sources).flatMap(([provider, source]) => accounts.accountCapabilities(source.account).map(cap => action(cap, provider))))
  }
  const loadSelectedSnapshots = () => selectedTasks(loadSnapshot)
  const refreshSelected = () => selectedTasks(refresh)
  async function loadOverview() {
    const version = ++overviewGeneration, owner = state.user?.user_id, accountVersion = JSON.stringify(state.accounts)
    if (!owner) return
    const valid = () => !disposed && version === overviewGeneration && owner === state.user?.user_id && accountVersion === JSON.stringify(state.accounts)
    state.overviewLoading = true
    try {
      await Promise.all(state.accounts.filter(a => a.state !== 'revoked').map(async account => {
        const role = account.roles?.find(r => r.is_default)?.role_id || account.roles?.[0]?.role_id
        if (!role) return
        const caps = accounts.accountCapabilities(account).filter(cap => ['account','stamina','gacha'].includes(cap))
        const old = state.overview[account.account_id]
        const entry = { role, version: account.version, grant_id: account.grant_id, roles: account.roles, snapshots: old?.role === role ? { ...old.snapshots } : {} }
        const publish = () => { if (valid()) state.overview[account.account_id] = { ...entry, snapshots: { ...entry.snapshots } } }
        publish()
        await Promise.all(caps.map(async cap => {
          try {
            const data = account.account_id === state.selected?.account_id && role === state.role && state.snapshots[cap] ? state.snapshots[cap] : await scopedSnapshot(account, role, cap)
            if (isEndfieldAccount(account) && !validEnvelope(data, account, role)) throw new Error('角色数据响应不匹配，请重试')
            entry.snapshots[cap] = data
          }
          catch (error) { if (error.name !== 'AbortError') entry.snapshots[cap] = { ...(entry.snapshots[cap] || { payload: null }), ...(isEndfieldAccount(account) ? { account_id: account.account_id, role_id: role } : {}), state: 'error', error: error.message } }
          publish()
        }))
      }))
    } finally { if (version === overviewGeneration) state.overviewLoading = false }
  }
  function loadSnapshot(cap, provider, trackedJob) {
    if (provider && typeof provider === 'object') { trackedJob = provider; provider = trackedJob.provider }
    const target = targetFor(cap, provider)
    if (!target) return Promise.resolve()
    const key = JSON.stringify([epoch, target.account.account_id, target.role, target.key, refreshVersions.get(target.key), !!trackedJob])
    if (reads.has(key)) return reads.get(key)
    const pending = readSnapshot(cap, provider, trackedJob).finally(() => { if (reads.get(key) === pending) reads.delete(key) })
    reads.set(key, pending)
    return pending
  }
  async function readSnapshot(cap, provider, trackedJob) {
    // Keep the existing internal tracked-job argument compatible.
    if (provider && typeof provider === 'object') { trackedJob = provider; provider = trackedJob.provider }
    const target = targetFor(cap, provider)
    if (!target) return
    const { account, role, key } = target, version = epoch
    const refreshVersion = refreshVersions.get(key), mutationPending = state.refreshing[key] === '正在排队'
    const readVersion = (readVersions.get(key) || 0) + 1
    readVersions.set(key, readVersion)
    const valid = () => current(version) && refreshVersion === refreshVersions.get(key) && readVersion === readVersions.get(key) && (!trackedJob || refreshJobs.get(key) === trackedJob)
    setReadState(target, cap, { status: 'loading', startedAt: Date.now(), error: '' })
    try {
      const data = await scopedSnapshot(account, role, cap)
      if (!valid()) return
      if (target.endfield && !validEnvelope(data, account, role)) throw new Error('角色数据响应不匹配，请重试')
      storeSnapshot(target, cap, data)
      setReadState(target, cap, { status: 'success', startedAt: null, error: '' })
      const entry = state.overview[account.account_id]
      if (entry?.role === role) entry.snapshots[cap] = data
      if (!mutationPending && state.refreshing[key] !== '正在排队') {
        const refreshState = data.poll_status?.refresh_state
        if (refreshState === 'queued' && refreshJobs.has(key)) state.refreshing[key] = '刷新已排队，正在读取状态…'
        else if (refreshState === 'running' && refreshJobs.has(key)) state.refreshing[key] = '刷新中…'
        else if (refreshState === 'idle' && state.refreshing[key]) {
          state.refreshing[key] = collectionState(data) === 'failed' ? `刷新失败，${data.payload == null ? '尚无成功数据' : '保留上次成功数据'}` : data.state === 'never' ? '刷新已结束，尚未采集到数据' : ''
          stopRefresh(key)
        }
      }
      return data
    }
    catch (error) { if (valid() && error.name !== 'AbortError') {
      storeSnapshot(target, cap, { ...(previousSnapshot(target, cap) || { payload: null }), ...(target.endfield ? { account_id: account.account_id, role_id: role } : {}), state: 'error', error: error.message })
      setReadState(target, cap, { status: 'error', startedAt: null, error: error.message })
      if (refreshJobs.has(key) && !mutationPending) { state.refreshing[key] = '刷新失败，显示上次的数据。'; stopRefresh(key) }
    } }
  }
  function trackRefresh(cap, job) {
    const key = job.key
    const valid = () => current(job.epoch) && refreshJobs.get(key) === job
    function timeout() {
      if (!valid()) return
      state.refreshing[key] = '刷新仍未完成，请稍后重试。'
      const target = targetFor(cap, job.provider)
      if (target && state.readStates[key]?.status === 'loading') setReadState(target, cap, { status: 'error', startedAt: null, error: '读取状态尚未确认，请稍后重试；已有数据仍保留。' })
      // Ignore a hanging/late read after the bounded tracking window.
      readVersions.set(key, (readVersions.get(key) || 0) + 1); stopRefresh(key, job)
    }
    async function poll() {
      if (!valid()) return
      await loadSnapshot(cap, job.provider, job)
      if (!valid()) return
      if (++job.reads >= REFRESH_READ_LIMIT) timeout()
      else job.timer = setTimeout(poll, REFRESH_READ_INTERVAL)
    }
    job.deadline = setTimeout(timeout, REFRESH_TRACK_TIMEOUT)
    job.timer = setTimeout(poll, 0)
  }
  async function refresh(cap, provider) {
    const version = epoch, target = targetFor(cap, provider)
    if (!target || refreshJobs.has(target.key)) return
    const { account, role, key } = target
    refreshVersions.set(key, (refreshVersions.get(key) || 0) + 1)
    state.refreshing[key] = '正在排队'
    const job = { epoch: version, reads: 0, key, provider: target.provider }; refreshJobs.set(key, job); state.refreshPending[key] = true
    try {
      const receipt = await api.refreshAccount(account.account_id, role, cap)
      if (current(version) && refreshJobs.get(key) === job) {
        // Reads started during POST cannot settle or overwrite the accepted job.
        readVersions.set(key, (readVersions.get(key) || 0) + 1)
        state.refreshing[key] = receipt.state === 'coalesced' ? '已有刷新任务，正在读取状态…' : '刷新已排队，正在读取状态…'
        trackRefresh(cap, job)
      }
    }
    catch (error) { if (current(version) && refreshJobs.get(key) === job && error.name !== 'AbortError') { state.refreshing[key] = ''; state.error = error.message; stopRefresh(key, job) } }
  }
  async function loadSessions() {
    const version = epoch
    try { const data = await api.getSessions(); if (current(version)) state.sessions = data.sessions || [] }
    catch (error) { if (current(version) && error.name !== 'AbortError') state.error = error.message }
  }
  async function logout() {
    // Begin the server mutation before clearing in-memory data; its response is
    // deliberately irrelevant to private state. A failure keeps a retry on offer
    // (logoutFailed, which clear() leaves alone): the site session may still be valid,
    // so the login form would claim a sign-out that has not happened.
    state.logoutFailed = false
    const pending = api.logoutSite(); clear()
    try { await pending } catch (error) { if (error.name !== 'AbortError' && error.status !== 401) state.logoutFailed = true }
  }
  return { state, initialize, loadAccounts, selectAccount, loadSnapshot, loadSelectedSnapshots, loadOverview, refresh, refreshSelected, loadSessions, logout, clear,
    dispose() { disposed = true; clear(); stop() } }
}
