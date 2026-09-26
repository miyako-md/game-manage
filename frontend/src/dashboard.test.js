import test from 'node:test'
import assert from 'node:assert/strict'
import { createDashboard, formatTime, summaryFor, upcomingEvents, recentNews, readRoute } from './dashboard.js'
import { collectCalendarEvents, eventStatus } from './calendar.js'

const game = { game_id: 'nte', display_name: '异环', capabilities: ['account', 'stamina', 'events'] }
test('mobile duplicate notices prefer Bilibili but LOL keeps both different links', () => {
  const lol = { game_id: 'league_of_legends', display_name: '英雄联盟' }
  const native = { title: '更新公告', url: 'https://community.test/1', published_at: '2026-09-16T00:00:00Z' }
  const bili = { ...native, url: 'https://t.bilibili.com/123', source: 'bilibili', published_at: '2026-09-15T00:00:00Z' }
  const snaps = {
    nte: { news: { primary_source: 'bilibili', payload: [bili] }, announcement: { payload: [native] } },
    league_of_legends: { news: { payload: [bili] }, announcement: { payload: [native] } },
  }
  const rows = recentNews([game,lol],snaps)
  assert.equal(rows.filter(r => r.gameId === 'nte').length, 1)
  assert.equal(rows.find(r => r.gameId === 'nte').source, 'bilibili')
  assert.equal(rows.filter(r => r.gameId === 'league_of_legends').length, 2)
})
const snapshot = (payload) => ({ payload, stale: false, fetched_at: '2026-09-14T12:30:00Z' })
const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r }); return { promise, resolve } }
function api(overrides = {}) {
  return { getGames: async () => [game], getStatus: async () => ({ notify: { enabled: false } }),
    getSnapshot: async (_id, cap) => snapshot(cap === 'events' ? [] : { nickname: '当前账号', current: 0, maximum: 120 }),
    refreshGame: async () => ({ results: { account: { ok: true } } }), ...overrides }
}

test('failed snapshot reads retain last data and expose affected capability', async () => {
  let fail = false
  const d = createDashboard(api({ getSnapshot: async () => { if (fail) throw Error('offline'); return snapshot({ nickname: '旧快照' }) } }))
  await d.load(); fail = true; await d.loadSnapshots()
  assert.equal(d.state.snapshots.nte.account.payload.nickname, '旧快照')
  assert.match(d.state.readErrors.nte, /account/)
})

test('account invalidation prevents previous in-flight private snapshots reappearing', async () => {
  const pending = deferred()
  let delayed = false
  const d = createDashboard(api({ getSnapshot: async (_id, cap) => delayed && cap === 'account' ? pending.promise : snapshot({ nickname: '已保存' }) }))
  await d.load(); delayed = true
  const oldRead = d.loadSnapshots('nte')
  d.invalidateGame('nte')
  pending.resolve(snapshot({ nickname: '不应出现的旧账号' })); await oldRead
  assert.equal(d.state.snapshots.nte.account, undefined)
  assert.ok(d.state.snapshots.nte.events)
})

test('a late older read cannot overwrite a newer read', async () => {
  let delayed = false; const pending = deferred()
  const d = createDashboard(api({ getSnapshot: async (_id, cap) => delayed && cap === 'account' ? pending.promise : snapshot({ nickname: '新' }) }))
  await d.load(); delayed = true; const old = d.loadSnapshots('nte')
  delayed = false; await d.loadSnapshots('nte')
  pending.resolve(snapshot({ nickname: '旧' })); await old
  assert.equal(d.state.snapshots.nte.account.payload.nickname, '新')
})

test('automatic load reads cache only; failed manual collection reports errors after reading snapshot', async () => {
  let calls = 0
  const d = createDashboard(api({ refreshGame: async () => { calls++; return { results: { stamina: { ok: false, error: '登录已失效' } } } } }))
  await d.load(); await d.loadSnapshots(); assert.equal(calls, 0)
  await d.refresh('nte')
  assert.equal(calls, 1); assert.match(d.state.refreshErrors.nte, /登录已失效/)
  assert.equal(d.state.refreshing.nte, false)
})

test('refresh result belonging to a previous account is discarded', async () => {
  const pending = deferred()
  const d = createDashboard(api({ refreshGame: () => pending.promise }))
  await d.load(); const refresh = d.refresh('nte'); d.invalidateGame('nte')
  pending.resolve({ results: { account: { ok: false, error: '旧账号错误' } } }); await refresh
  assert.equal(d.state.refreshErrors.nte, undefined)
  assert.equal(d.state.snapshots.nte.account, undefined)
})

test('older refresh cleanup cannot clear the new account refresh indicator', async () => {
  const oldSnapshot = deferred(), newRefresh = deferred()
  let holdSnapshot = false, newAccount = false
  const d = createDashboard(api({
    getSnapshot: async (_id, cap) => holdSnapshot && cap === 'account' ? oldSnapshot.promise : snapshot({ nickname: '当前' }),
    refreshGame: async () => newAccount ? newRefresh.promise : { results: { account: { ok: true } } },
  }))
  await d.load(); holdSnapshot = true
  const old = d.refresh('nte'); await new Promise(setImmediate)
  d.invalidateGame('nte'); holdSnapshot = false; newAccount = true
  const current = d.refresh('nte')
  assert.equal(d.state.refreshing.nte, true)
  oldSnapshot.resolve(snapshot({ nickname: '旧' })); await old
  assert.equal(d.state.refreshing.nte, true)
  newRefresh.resolve({ results: { account: { ok: true } } }); await current
  assert.equal(d.state.refreshing.nte, false)
})

test('stamina summary preserves real zero and unknown denominator', () => {
  const s = summaryFor(game, { stamina: snapshot({ schema_version: 1, current: 0, maximum: null }) })
  assert.equal(s.value, 0); assert.equal(s.maximum, null); assert.equal(s.percent, null)
  const unknown = summaryFor(game, { stamina: snapshot({ schema_version: 1, current: null, maximum: 120 }) })
  assert.equal(unknown.value, null); assert.equal(unknown.percent, null)
})

test('LoL win rate summary carries the decided-game count used as its denominator', () => {
  const lol = { game_id: 'league_of_legends', capabilities: ['account', 'match', 'stats'] }
  const s = summaryFor(lol, { stats: snapshot({ total_games: 20, wins: 10, winrate: 55.6, decided_games: 18, remakes: 1 }) })
  assert.equal(s.value, 55.6); assert.equal(s.totalGames, 20); assert.equal(s.decided, 18)
  const old = summaryFor(lol, { stats: snapshot({ total_games: 20, wins: 11, winrate: 55 }) })
  assert.equal(old.decided, null)
})

test('NTE legacy raw data cannot silently become a valid account or stamina summary', () => {
  const s = summaryFor(game, { account: snapshot({ nickname: '旧结构' }), stamina: snapshot({ current: 50, maximum: 100 }) })
  assert.equal(s.value, null); assert.equal(s.nickname, null)
})

test('expired and malformed events are excluded from upcoming summary without guessing dates', () => {
  const now = Date.parse('2026-09-14T12:00:00Z')
  const items = upcomingEvents([game], { nte: { events: snapshot([
    { name: '已结束', end_at: '2026-09-14T19:00:00+08:00' },
    { name: '仍进行', end_at: '2026-09-15T03:59:00+08:00' },
    { name: '未知', end_at: null },
    { name: '损坏的开始时间', start_at: 'bad', end_at: '2026-09-15T03:59:00+08:00' },
    { name: '逆序', start_at: '2026-09-20T00:00:00+08:00', end_at: '2026-09-16T00:00:00+08:00' },
  ]) } }, now)
  assert.deepEqual(items.map(e => e.name), ['仍进行'])
  assert.equal(items[0].remainingDays, 1)
})

test('news are sorted by timestamp, unsafe links omitted and duplicate sources merged', () => {
  const g = { ...game, capabilities: ['announcement', 'news'] }
  const news = recentNews([g], { nte: { announcement: snapshot([{ title: '较早', published_at: '2026-09-13T00:00:00Z', url: 'https://example.com/old' }]),
    news: snapshot([{ title: '较新', published_at: '2026-09-14T00:00:00Z', url: 'javascript:alert(1)' }, { title: '较早', url: 'https://example.com/old' }]) } })
  assert.deepEqual(news.map(n => n.title), ['较新', '较早'])
  assert.equal(news[0].url, null)
})

test('hash routes support calendar game links and fail closed on malformed locations', () => {
  assert.deepEqual(readRoute('#/calendar?game=nte'), { page: 'calendar', game: 'nte' })
  assert.deepEqual(readRoute('#/game/wuthering_waves'), { page: 'game', game: 'wuthering_waves' })
  assert.deepEqual(readRoute('#/accounts'), { page: 'accounts', game: '' })
  assert.deepEqual(readRoute('#/game/%E0%A4'), { page: 'overview', game: '' })
})

test('collection status is loaded and cleared for a switched private account', async () => {
  const d = createDashboard(api({ getStatus: async () => ({ notify: { enabled: false }, collection: [
    { game_id: 'nte', capability: 'account', state: 'auth_expired' },
    { game_id: 'nte', capability: 'events', state: 'ok' },
  ] }) }))
  await d.load()
  assert.equal(d.state.collection[0].state, 'auth_expired')
  d.invalidateGame('nte')
  assert.deepEqual(d.state.collection.map(row => row.capability), ['events'])
})

test('snapshot collection status replaces older status but cannot be rolled back by a status response', async () => {
  const d = createDashboard(api({ getStatus: async () => ({ collection: [{ game_id: 'nte', capability: 'account', state: 'error', last_attempt_at: '2026-09-14T12:00:00Z' }] }),
    getSnapshot: async (_id, cap) => ({ ...snapshot({ nickname: '当前' }), poll_status: { game_id: 'nte', capability: cap, state: 'ok', last_attempt_at: '2026-09-14T12:01:00Z' } }),
  }))
  await d.load(); await d.loadStatus()
  assert.equal(d.state.collection.find(row => row.capability === 'account').state, 'ok')
})

test('expected unavailable manual refresh is shown as source state without a fault banner', async () => {
  const d = createDashboard(api({ refreshGame: async () => ({ results: { account: { ok: false, error: '客户端未运行', error_kind: 'offline' } } }) }))
  await d.load(); await d.refresh('nte')
  assert.equal(d.state.refreshErrors.nte, '')
})

test('a newer observation of cleared collection state replaces older failures', async () => {
  let cleared = false
  const d = createDashboard(api({ getStatus: async () => ({ collection: [{ game_id: 'nte', capability: 'account',
    state: cleared ? 'never' : 'auth_expired', last_attempt_at: cleared ? null : '2026-09-14T12:00:00Z',
    observed_at: cleared ? '2026-09-14T12:03:00Z' : '2026-09-14T12:02:00Z' }] }),
  }))
  await d.load(); cleared = true; await d.loadStatus()
  assert.equal(d.state.collection[0].state, 'never')
})

test('late older observations cannot roll back a newer cleared status', async () => {
  let old = false
  const d = createDashboard(api({ getStatus: async () => ({ collection: [{ game_id: 'nte', capability: 'account',
    state: old ? 'error' : 'never', last_attempt_at: old ? '2026-09-14T12:00:00Z' : null,
    observed_at: old ? '2026-09-14T12:02:00Z' : '2026-09-14T12:03:00Z' }] }),
  }))
  await d.load(); old = true; await d.loadStatus()
  assert.equal(d.state.collection[0].state, 'never')
})
test('formatTime shows missing, unparseable and out-of-range times as not provided', () => {
  assert.equal(formatTime(null), '未提供')
  assert.equal(formatTime('not a date'), '未提供')
  assert.equal(formatTime(8.64e15 + 1), '未提供')
  assert.equal(formatTime('2026-09-14T02:00:00Z'), '09/14 10:00')
})

test('overview events agree with the calendar on date-only starts and stale source rows', () => {
  const now = Date.parse('2026-09-15T00:00:00+08:00')
  const snapshots = { nte: { events: snapshot([
    { name: '次日开放', start_date: '2026-09-16', end_at: '2026-09-20T03:59:00+08:00' },
    { name: '社区补充', end_at: '2026-09-18T03:59:00+08:00', source_stale: true },
  ]) } }
  const overview = upcomingEvents([game], snapshots, now)
  assert.deepEqual(overview.map(e => [e.name, e.upcoming, e.stale]), [['社区补充', false, true], ['次日开放', true, false]])
  const calendar = collectCalendarEvents([game], snapshots)
  assert.deepEqual(calendar.map(e => [e.name, eventStatus(e, now) === '未开始', e.stale]), [['次日开放', true, false], ['社区补充', false, true]])
})
