import test from 'node:test'
import assert from 'node:assert/strict'
import { h, ref, nextTick } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
const LolDashboard = await loadVue(new URL('./LolDashboard.vue', import.meta.url))
const flush = async () => { await new Promise(setImmediate); await nextTick() }
const response = value => new Response(JSON.stringify(value))
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
const data = (name = '本地召唤师') => ({
  schema_version: 1, account: { nickname: name, level: 0 }, source: 'local_lcu_archive',
  overview: { games: 2, wins: 0, losses: 1, unknown_results: 1, winrate: 0, average_score: null, avg_kills: 0, avg_deaths: null, avg_assists: 0, play_minutes: 0 },
  coverage: { archived_games: 2, filtered_games: 2, detail_games: 1, score_games: 0, scope_note: '仅客户端采集窗口' },
  matches: [{ match_id: 'm1', champion_name: '测试英雄', win: null, kills: 0, deaths: null, assists: 0, score: null, kp: 0, damage_share: null, augments: [] }],
  trend: [{ date: '2026-09-25', games: 2, wins: 0, winrate: 0, average_score: null }],
  heatmap: [{ date: '2026-09-25', games: 2, wins: 0 }], champions: [], highlights: [],
  hextech: { games: 2, recorded_games: 1, augments: [], combinations: [], rating_status: 'unavailable' },
})
const button = (root, label) => nodes(root, 'button').find(n => content(n).includes(label))

test('announcements and news remain separately accessible without an archive', async t => {
  t.mock.method(globalThis, 'fetch', async () => response({ ...data(), overview: { games: 0 }, coverage: { archived_games: 0 } }))
  const root = mount(t, LolDashboard, { snaps: {
    announcement: { payload: [{ title: '维护公告', url: 'https://example.com/announcement' }], stale: true },
    news: { payload: [{ title: '赛事资讯', url: 'https://example.com/news' }] },
  } })
  await flush()
  assert.ok(button(root, '公告'), 'announcement navigation must remain reachable')
  button(root, '公告').props.onClick(); await flush()
  assert.match(content(root), /维护公告/)
  assert.match(content(root), /数据可能过期/)
  assert.doesNotMatch(content(root), /赛事资讯/)
  button(root, '资讯').props.onClick(); await flush()
  assert.match(content(root), /赛事资讯/)
  assert.doesNotMatch(content(root), /维护公告/)
})

test('remakes display separately from unknown results and retain neutral detail labels', async t => {
  const archive = data()
  archive.overview = { ...archive.overview, games: 4, wins: 1, losses: 1, remakes: 1, unknown_results: 1, winrate: 50 }
  archive.matches = [{ ...archive.matches[0], remake: true, win: null }]
  t.mock.method(globalThis, 'fetch', async url => response(url.includes('/matches/')
    ? { payload: { remake: true, teams: [{ team_id: 100, win: false, participants: [] }] } } : archive))
  const root = mount(t, LolDashboard, {})
  await flush()
  assert.match(content(root), /1 重开/)
  assert.match(content(root), /有效胜负 2 场/)
  button(root, '对局记录').props.onClick(); await flush()
  const row = nodes(root, 'article').find(node => node.props.class?.includes('lol-match'))
  assert.match(content(row), /重开/)
  assert.doesNotMatch(content(row), /胜负未知|失败/)
  assert.match(row.props.class, /remake/)
  button(root, '查看详情').props.onClick(); await flush()
  assert.match(content(row), /重开.*队伍 100/)
  assert.doesNotMatch(content(row), /失败/)
})

test('offline empty archive exposes collection directly without a popup', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, opts) => {
    calls.push({ url, opts })
    if (opts.method === 'POST') return new Response('{}', { status: 503 })
    return response({ ...data(), account: null, overview: { games: 0 }, matches: [], coverage: { archived_games: 0 } })
  })
  const root = mount(t, LolDashboard, { snaps: { account: { error: 'offline' } } })
  await flush()
  assert.match(content(root), /本机尚无归档/)
  assert.equal(calls.length, 1)
  button(root, '采集客户端战绩').props.onClick(); await flush()
  assert.equal(calls[1].url, '/api/lol/collect')
  assert.equal(calls[1].opts.headers['X-Game-Assistant'], '1')
  assert.match(content(root), /客户端/)
})

test('real zero and unknown remain distinct; unknown result never becomes a loss', async t => {
  t.mock.method(globalThis, 'fetch', async () => response(data()))
  const root = mount(t, LolDashboard, {})
  await flush()
  assert.match(content(root), /0(?:\.0)?%/)
  assert.match(content(root), /0 胜 · 1 负 · 1 未知/)
  assert.match(content(root), /LOLhelper v3/)
  assert.match(content(root), /有效胜负 1 场/)
  button(root, '对局记录').props.onClick(); await flush()
  assert.match(content(root), /胜负未知/)
  assert.match(content(root), /0 \/ 未知 \/ 0/)
  assert.match(content(root), /参团 0(?:\.0)?%/)
  button(root, '海克斯').props.onClick(); await flush()
  assert.match(content(root), /2 场/)
  assert.match(content(root), /1 场/)
  assert.match(content(root), /不代表.*强度/)
})

test('filter changes abort old requests and late responses cannot replace current data', async t => {
  const old = deferred(), fresh = deferred(), calls = []
  t.mock.method(globalThis, 'fetch', (url, opts) => { calls.push({ url, opts }); return calls.length === 1 ? old.promise : fresh.promise })
  const root = mount(t, LolDashboard, {})
  nodes(root, 'select')[0].props.onChange({ target: { value: '7' } }); await nextTick()
  assert.equal(calls[0].opts.signal.aborted, true)
  assert.match(calls[1].url, /days=7/)
  fresh.resolve(response(data('当前数据'))); await flush()
  old.resolve(response(data('过时数据'))); await flush()
  assert.match(content(root), /当前数据/)
  assert.doesNotMatch(content(root), /过时数据/)
})

test('failed reload preserves old records and their filter label', async t => {
  let count = 0
  t.mock.method(globalThis, 'fetch', async () => ++count === 1 ? response(data()) : new Response('{}', { status: 502 }))
  const root = mount(t, LolDashboard, {})
  await flush()
  nodes(root, 'select')[0].props.onChange({ target: { value: '7' } }); await flush()
  assert.match(content(root), /保留上次成功读取/)
  assert.match(content(root), /当前展示：近 90 天/)
  assert.match(content(root), /本地召唤师/)
})

test('match details read archived records and preserve unknown participant metrics', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async url => { calls.push(url); return response(url.includes('/matches/') ? { payload: { teams: [{ team_id: 100, win: null, participants: [{ champion_name: '详情英雄', kills: null, deaths: 0, assists: null }] }] } } : data()) })
  const root = mount(t, LolDashboard, {})
  await flush(); button(root, '对局记录').props.onClick(); await flush()
  button(root, '查看详情').props.onClick(); await flush()
  assert.equal(calls[1], '/api/lol/matches/m1')
  assert.match(content(root), /详情英雄/)
  assert.match(content(root), /未知 \/ 0 \/ 未知/)
})

test('collection failure keeps the previously loaded archive visible', async t => {
  t.mock.method(globalThis, 'fetch', async (_url, opts) => opts.method === 'POST' ? new Response('{}', { status: 503 }) : response(data('保留的账号')))
  const root = mount(t, LolDashboard, {})
  await flush(); button(root, '采集客户端战绩').props.onClick(); await flush()
  assert.match(content(root), /保留的账号/)
  assert.match(content(root), /已有分析数据仍保留/)
  assert.match(content(root), /0 胜 · 1 负 · 1 未知/)
})

test('changing the expanded archive match ignores a late earlier detail', async t => {
  const first = deferred(), second = deferred(), archive = data()
  archive.matches.push({ ...archive.matches[0], match_id: 'm2' })
  t.mock.method(globalThis, 'fetch', url => url.endsWith('/m1') ? first.promise : url.endsWith('/m2') ? second.promise : Promise.resolve(response(archive)))
  const root = mount(t, LolDashboard, {})
  await flush(); button(root, '对局记录').props.onClick(); await flush()
  button(root, '查看详情').props.onClick(); await flush()
  button(root, '查看详情').props.onClick(); await flush()
  const teams = name => ({ payload: { teams: [{ team_id: 100, participants: [{ champion_name: name }] }] } })
  second.resolve(response(teams('正确详情'))); await flush()
  first.resolve(response(teams('过时详情'))); await flush()
  assert.match(content(root), /正确详情/)
  assert.doesNotMatch(content(root), /过时详情/)
})

test('unmount aborts outstanding analysis and discards its late response', async t => {
  const pending = deferred(), visible = ref(true); let signal
  t.mock.method(globalThis, 'fetch', (_url, options) => { signal = options.signal; return pending.promise })
  const root = mount(t, { setup: () => () => visible.value ? h(LolDashboard) : h('p', '已关闭') }, {})
  visible.value = false; await nextTick()
  assert.equal(signal.aborted, true)
  pending.resolve(response(data('不应出现'))); await flush()
  assert.equal(content(root), '已关闭')
})

test('account identity change clears prior analysis and aborts details even when the new read fails', async t => {
  const snaps = ref({ account: { payload: { extra: { puuid: 'account-a' } }, fetched_at: 'first' } })
  const pending = deferred(); let detailSignal, reads = 0
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url.includes('/matches/')) { detailSignal = options.signal; return pending.promise }
    return ++reads === 1 ? response(data('账号甲')) : new Response('{}', { status: 502 })
  })
  const root = mount(t, { setup: () => () => h(LolDashboard, { snaps: snaps.value }) }, {})
  await flush(); button(root, '对局记录').props.onClick(); await flush()
  button(root, '查看详情').props.onClick(); await flush()
  snaps.value = { account: { payload: { extra: { puuid: 'account-b' } }, fetched_at: 'second' } }
  await flush()
  assert.equal(detailSignal.aborted, true)
  assert.equal(reads, 2)
  assert.doesNotMatch(content(root), /账号甲|测试英雄|保留上次成功/)
  pending.resolve(response({ payload: { teams: [{ team_id: 100, participants: [{ champion_name: '账号甲详情' }] }] } })); await flush()
  assert.doesNotMatch(content(root), /账号甲详情/)
})

test('an in-flight analysis from a previous account cannot replace the new account', async t => {
  const snaps = ref({ account: { payload: { extra: { puuid: 'account-a' } } } }), old = deferred(), fresh = deferred(), signals = []
  t.mock.method(globalThis, 'fetch', (_url, options) => { signals.push(options.signal); return signals.length === 1 ? old.promise : fresh.promise })
  const root = mount(t, { setup: () => () => h(LolDashboard, { snaps: snaps.value }) }, {})
  snaps.value = { account: { payload: { extra: { puuid: 'account-b' } } } }; await nextTick()
  assert.equal(signals[0].aborted, true)
  fresh.resolve(response(data('账号乙'))); await flush()
  old.resolve(response(data('账号甲'))); await flush()
  assert.match(content(root), /账号乙/)
  assert.doesNotMatch(content(root), /账号甲/)
})

test('same-account snapshot revisions reload analysis and preserve prior data on failure', async t => {
  const snaps = ref({ account: { payload: { extra: { puuid: 'account-a' } }, fetched_at: 'a1' }, match: { fetched_at: 'm1' }, stats: { fetched_at: 's1' } })
  let reads = 0
  t.mock.method(globalThis, 'fetch', async () => {
    reads++
    return reads === 3 ? new Response('{}', { status: 502 }) : response(data(`账号甲版本${reads}`))
  })
  const root = mount(t, { setup: () => () => h(LolDashboard, { snaps: snaps.value }) }, {})
  await flush()
  snaps.value.match.fetched_at = 'm2'; await flush()
  assert.equal(reads, 2)
  assert.match(content(root), /账号甲版本2/)
  snaps.value.stats.fetched_at = 's2'; await flush()
  assert.equal(reads, 3)
  assert.match(content(root), /账号甲版本2/)
  assert.match(content(root), /保留上次成功读取/)
  snaps.value.account.fetched_at = 'a2'; await flush()
  assert.equal(reads, 4)
  assert.match(content(root), /账号甲版本4/)
})
