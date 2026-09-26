import { reactive } from 'vue'
import { DAY_MS, parseBeijingTime, safeUrl } from './calendar.js'

const PUBLIC_CAPS = new Set(['events', 'announcement', 'news', 'teams'])
export const GAME_STYLE = {
  wuthering_waves: { mark: '鸣', icon: '/game-icons/wuthering_waves-mark.svg', iconLight: '/game-icons/wuthering_waves-mark-light.svg', color: 'var(--game-wuwa)', english: 'WUTHERING WAVES', resource: '结晶波片' },
  nte: { mark: '异', icon: '/game-icons/nte-mark.svg', iconLight: '/game-icons/nte-mark-light.svg', color: 'var(--game-nte)', english: 'NEVERNESS TO EVERNESS', resource: '本性像素' },
  league_of_legends: { mark: 'L', icon: '/game-icons/league_of_legends-mark.svg', iconLight: '/game-icons/league_of_legends-mark-light.svg', color: 'var(--game-lol)', english: 'LEAGUE OF LEGENDS' },
}
// Colours are theme variables (style.css), so each game keeps a readable accent by day and by night.
export const gameStyle = (id) => GAME_STYLE[id] || { mark: '游', color: 'var(--text-muted)', english: 'MY GAME', resource: '体力' }
export const finiteValue = (value) => typeof value === 'number' && Number.isFinite(value) ? value : null
export function formatTime(value, options = {}) {
  const ts = typeof value === 'number' ? value : parseBeijingTime(value)
  // A finite number outside the Date range makes an Invalid Date, which Intl rejects.
  const date = new Date(ts ?? NaN)
  if (!Number.isFinite(date.getTime())) return '未提供'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', ...options,
  }).format(date)
}
export function summaryFor(game, snapshots = {}) {
  const validPayload = (cap) => {
    const p = snapshots[cap]?.payload
    if (!p || typeof p !== 'object' || Array.isArray(p)) return null
    if (game.game_id === 'nte' && !PUBLIC_CAPS.has(cap) && p.schema_version !== 1) return null
    return p
  }
  const account = validPayload('account')
  const stamina = validPayload('stamina')
  const stats = validPayload('stats')
  const hasStamina = game.capabilities.includes('stamina')
  const value = finiteValue(hasStamina ? stamina?.current : stats?.winrate)
  const maximum = finiteValue(stamina?.maximum)
  const primary = snapshots[hasStamina ? 'stamina' : 'stats'] || snapshots.account
  return {
    nickname: account?.nickname || null, level: finiteValue(account?.level), hasStamina,
    value, maximum, percent: hasStamina ? value != null && maximum > 0 ? Math.max(0, Math.min(100, value / maximum * 100)) : null : value,
    expectedFullAt: stamina?.expected_full_at || null, totalGames: finiteValue(stats?.total_games), wins: finiteValue(stats?.wins), remakes: finiteValue(stats?.remakes) ?? 0,
    fetchedAt: primary?.fetched_at || null, stale: !!primary?.stale,
  }
}

export function upcomingEvents(games, snapshots, now = Date.now()) {
  return games.flatMap(game => {
    const snap = snapshots[game.game_id]?.events
    if (!Array.isArray(snap?.payload)) return []
    return snap.payload.flatMap((ev, index) => {
      if (!ev || typeof ev !== 'object') return []
      // Same start and staleness rules as the calendar (eventGeometry, collectCalendarEvents).
      const end = parseBeijingTime(ev.end_at), start = parseBeijingTime(ev.start_at || ev.start_date)
      if (end == null || end <= now || (ev.start_at && start == null) || (start != null && start > end)) return []
      return [{ ...ev, id: `${game.game_id}:${index}`, gameId: game.game_id, gameName: game.display_name,
        endTime: end, remainingDays: Math.ceil((end - now) / DAY_MS), upcoming: start != null && start > now,
        stale: Boolean(snap.stale || ev.source_stale) }]
    })
  }).sort((a, b) => a.endTime - b.endTime)
}

export function recentNews(games, snapshots) {
  const rows = games.flatMap(game => {
    const primary = ['nte', 'wuthering_waves'].includes(game.game_id) && snapshots[game.game_id]?.news?.primary_source === 'bilibili'
    return (primary ? ['news', 'announcement'] : ['announcement', 'news']).flatMap(cap => {
    const snap = snapshots[game.game_id]?.[cap]
    if (!Array.isArray(snap?.payload)) return []
    return snap.payload.filter(row => row && typeof row.title === 'string').map(row => ({ ...row,
      gameName: game.display_name, gameId: game.game_id, capability: cap, primary, stale: !!snap.stale || !!row.source_stale,
      url: safeUrl(row.url), publishedTime: parseBeijingTime(row.published_at) || 0 }))
  })})
  const selected = new Map()
  for (const row of rows) {
    const key = `${row.gameId}:${row.primary ? row.title.normalize('NFKC').replace(/[^\p{L}\p{N}]/gu, '') : row.url || row.title}`
    const previous = selected.get(key)
    const priority = item => item.primary && item.source === 'bilibili' ? 1 : 0
    if (!previous || priority(row) > priority(previous) || (priority(row) === priority(previous) && row.publishedTime > previous.publishedTime)) selected.set(key, row)
  }
  // Only configured mobile community supplements move behind primary notices.
  // LOL keeps its original source and chronological order.
  const supplement = row => row.primary && row.source !== 'bilibili' ? 1 : 0
  return [...selected.values()].sort((a, b) => supplement(a) - supplement(b) || b.publishedTime - a.publishedTime)
}

export function readRoute(hash) {
  try {
    const url = new URL((hash || '').replace(/^#/, '') || '/', 'http://local')
    if (url.pathname === '/calendar') return { page: 'calendar', game: url.searchParams.get('game') || '' }
    if (url.pathname === '/accounts') return { page: 'accounts', game: '' }
    if (url.pathname.startsWith('/game/')) return { page: 'game', game: decodeURIComponent(url.pathname.slice(6)) }
  } catch { /* A malformed bookmark returns to the overview. */ }
  return { page: 'overview', game: '' }
}

export function createDashboard(api) {
  const state = reactive({ games: [], snapshots: {}, notify: null, accounts: {}, collection: [], readErrors: {}, refreshErrors: {}, refreshing: {},
    loading: false, loadError: '', serviceError: '', loadedAt: null })
  const requests = new Map(), epochs = new Map()
  let catalogRequest = 0, statusRequest = 0, disposed = false

  function mergeCollection(rows) {
    if (!Array.isArray(rows)) return
    const merged = new Map(state.collection.map(row => [`${row.game_id}:${row.capability}`, row]))
    for (const row of rows) {
      if (!row?.game_id || !row?.capability) continue
      const key = `${row.game_id}:${row.capability}`, previous = merged.get(key)
      const observed = parseBeijingTime(row.observed_at), previousObserved = parseBeijingTime(previous?.observed_at)
      const latest = observed != null ? previousObserved == null || observed >= previousObserved
        : previousObserved == null && (parseBeijingTime(row.last_attempt_at) || 0) >= (parseBeijingTime(previous?.last_attempt_at) || 0)
      if (!previous || latest) merged.set(key, row)
    }
    state.collection = [...merged.values()]
  }

  async function loadStatus() {
    const request = ++statusRequest
    const results = await Promise.allSettled([api.getStatus(), api.getAuthStatus ? api.getAuthStatus() : Promise.resolve(null)])
    if (disposed || request !== statusRequest) return
    if (results[0].status === 'fulfilled') { state.notify = results[0].value?.notify || null; mergeCollection(results[0].value?.collection); state.serviceError = '' }
    else state.serviceError = '服务状态读取失败，请检查后端连接。'
    if (results[1].status === 'fulfilled' && results[1].value) state.accounts = results[1].value.accounts || {}
  }

  async function loadSnapshots(gameId) {
    const selected = gameId ? state.games.filter(g => g.game_id === gameId) : [...state.games]
    await Promise.all(selected.map(async game => {
      const id = game.game_id, request = (requests.get(id) || 0) + 1
      requests.set(id, request)
      const results = await Promise.allSettled(game.capabilities.map(cap => api.getSnapshot(id, cap)))
      if (disposed || request !== requests.get(id)) return
      const next = { ...(state.snapshots[id] || {}) }, failed = []
      results.forEach((r, index) => {
        const cap = game.capabilities[index]
        if (r.status === 'fulfilled' && r.value && 'payload' in r.value) {
          next[cap] = r.value
          if (r.value.poll_status) mergeCollection([r.value.poll_status])
        }
        else failed.push(cap)
      })
      state.snapshots[id] = next
      state.readErrors[id] = failed.length ? `快照读取失败（${failed.join('、')}），保留已有数据。` : ''
    }))
    if (!disposed) state.loadedAt = Date.now()
  }

  async function load() {
    const request = ++catalogRequest
    state.loading = true
    const status = loadStatus()
    try {
      const games = await api.getGames()
      if (disposed || request !== catalogRequest) return
      if (!Array.isArray(games)) throw Error('invalid catalog')
      state.games = games
      state.loadError = ''
      await loadSnapshots()
    } catch {
      if (!disposed && request === catalogRequest) state.loadError = '无法连接游戏数据服务，请确认后端已启动后重试。'
    } finally {
      await status
      if (!disposed && request === catalogRequest) state.loading = false
    }
  }

  function invalidateGame(id) {
    statusRequest += 1
    epochs.set(id, (epochs.get(id) || 0) + 1)
    requests.set(id, (requests.get(id) || 0) + 1)
    state.snapshots[id] = Object.fromEntries(Object.entries(state.snapshots[id] || {}).filter(([cap]) => PUBLIC_CAPS.has(cap)))
    state.collection = state.collection.filter(row => row.game_id !== id || PUBLIC_CAPS.has(row.capability))
    delete state.readErrors[id]; delete state.refreshErrors[id]; delete state.accounts[id]
    state.refreshing[id] = false
  }

  async function refresh(id) {
    if (state.refreshing[id]) return
    const epoch = epochs.get(id) || 0
    state.refreshing[id] = true
    try {
      const result = await api.refreshGame(id)
      if (disposed || epoch !== (epochs.get(id) || 0)) return
      const failed = Object.entries(result?.results || {}).filter(([, r]) => r?.ok !== true && !['offline', 'unconfigured', 'account_changed'].includes(r?.error_kind))
      state.refreshErrors[id] = failed.length ? failed.map(([cap, r]) => `${cap}：${r?.error || '拉取失败'}`).join('；') : ''
    } catch {
      if (!disposed && epoch === (epochs.get(id) || 0)) state.refreshErrors[id] = '刷新请求失败，请检查连接后重试。'
    } finally {
      if (!disposed && epoch === (epochs.get(id) || 0)) {
        await loadSnapshots(id)
        if (!disposed && epoch === (epochs.get(id) || 0)) state.refreshing[id] = false
      }
    }
  }

  return { state, load, loadSnapshots, loadStatus, refresh, invalidateGame, dispose() { disposed = true } }
}
