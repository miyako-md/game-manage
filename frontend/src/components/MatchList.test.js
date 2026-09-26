import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
const MatchList = await loadVue(new URL('./MatchList.vue', import.meta.url))
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
const detail = name => new Response(JSON.stringify({ payload: { teams: [{ team_id: 100, win: true, participants: [{ champion_name: name }] }] } }))

test('switching matches ignores stale detail and stale loading cleanup', async t => {
  const first = deferred(), second = deferred()
  t.mock.method(globalThis, 'fetch', async url => url.includes('/first/') ? first.promise : second.promise)
  const root = mount(t, MatchList, { gameId: 'lol', snap: { payload: [{ match_id: 'first' }, { match_id: 'second' }] } })
  nodes(root, 'button')[0].props.onClick(); await nextTick()
  nodes(root, 'button')[1].props.onClick(); await nextTick()
  first.resolve(detail('不应出现的旧详情')); await new Promise(setImmediate); await nextTick()
  assert.match(content(root), /对局详情加载中/)
  assert.doesNotMatch(content(root), /不应出现/)
  second.resolve(detail('当前对局详情')); await new Promise(setImmediate); await nextTick()
  assert.match(content(root), /当前对局详情/)
})

test('a closed detail response cannot overwrite a newly selected match', async t => {
  const first = deferred(), second = deferred()
  t.mock.method(globalThis, 'fetch', async url => url.includes('/first/') ? first.promise : second.promise)
  const root = mount(t, MatchList, { gameId: 'lol', snap: { payload: [{ match_id: 'first' }, { match_id: 'second' }] } })
  nodes(root, 'button')[0].props.onClick(); await nextTick()
  nodes(root, 'button')[0].props.onClick(); await nextTick()
  nodes(root, 'button')[1].props.onClick(); await nextTick()
  second.resolve(detail('当前')); await new Promise(setImmediate); await nextTick()
  first.resolve(detail('旧')); await new Promise(setImmediate); await nextTick()
  assert.match(content(root), /当前/); assert.doesNotMatch(content(root), /旧/)
})

const game = (id, win, extra = {}) => ({ match_id: id, win, mode: 'CLASSIC', kills: 5, deaths: 2, assists: 6, duration_seconds: 1800, damage: 20000, start_at: '2026-09-26T12:00:00Z', ...extra })

test('remakes and unknown results stay out of the win rate, streak and header count', t => {
  const root = mount(t, MatchList, { gameId: 'lol', snap: { payload: [
    game('remake', false, { duration_seconds: 210, kills: 0, deaths: 0, assists: 0 }),
    game('w1', true),
    game('unknown', null),
    game('l1', false),
  ] } })
  const text = content(root)
  assert.match(text, /近 4 场 1 胜 · 1 场重开不计 · 1 场结果未知/)
  assert.match(text, /50\s*%/)
  assert.match(text, /1 胜 1 负/)
  assert.match(text, /1\s*连胜/)
  assert.match(text, /重开.*不计入统计/)
  assert.doesNotMatch(text, /连败/)
})

test('a remake flagged by the backend counts as a remake whatever its length', t => {
  const root = mount(t, MatchList, { gameId: 'lol', snap: { payload: [game('flagged', false, { remake: true }), game('w', true)] } })
  assert.match(content(root), /近 2 场 1 胜 · 1 场重开不计/)
  assert.match(content(root), /100\s*%/)
})

test('a long break between games is marked on the newer game', t => {
  const root = mount(t, MatchList, { gameId: 'lol', snap: { payload: [
    game('new', true, { start_at: '2026-09-26T12:00:00Z' }),
    game('old', false, { start_at: '2026-09-16T12:00:00Z' }),
  ] } })
  assert.match(content(root), /隔 10 天/)
})

test('games are shown newest first even when the snapshot is out of order', t => {
  const root = mount(t, MatchList, { gameId: 'lol', snap: { payload: [
    game('older', false, { start_at: '2026-09-20T12:00:00Z' }),
    game('newer', true, { start_at: '2026-09-26T12:00:00Z' }),
  ] } })
  const cards = nodes(root, 'article')
  assert.match(content(cards[0]), /09-26/)
  assert.match(content(cards[1]), /09-20/)
  assert.match(content(root), /1\s*连胜/)
})

test('an expanded remake shows 重开 for both teams instead of the recorded win and loss', async t => {
  const teams = [{ team_id: 100, win: true, participants: [{ champion_name: '安妮', is_own: true }] }, { team_id: 200, win: false, participants: [{ champion_name: '盖伦' }] }]
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ payload: { teams } })))
  const root = mount(t, MatchList, { gameId: 'lol', snap: { payload: [game('remake', true, { remake: true, duration_seconds: 200 }), game('played', true)] } })
  const detailButton = name => nodes(root, 'button').find(b => b.props['aria-expanded'] !== undefined && content(b) === name)
  detailButton('详情').props.onClick(); await new Promise(setImmediate); await nextTick()
  const results = () => nodes(root, 'span').filter(n => /team-result/.test(n.props.class ?? '')).map(content)
  assert.deepEqual(results(), ['重开', '重开'])
  nodes(root, 'button').find(b => content(b) === '收起').props.onClick(); await nextTick()
  nodes(root, 'button').filter(b => content(b) === '详情')[1].props.onClick(); await new Promise(setImmediate); await nextTick()
  assert.deepEqual(results(), ['胜利', '失败'])
})

test('a champion name on the match wins over the career top-five list', t => {
  const root = mount(t, MatchList, { gameId: 'lol', stats: { top_champions: [{ champion_id: 1, champion_name: '旧名' }] }, snap: { payload: [
    game('named', true, { champion_id: 1, champion_name: '安妮' }),
    game('rare', true, { champion_id: 99 }),
  ] } })
  assert.match(content(root), /安妮/)
  assert.doesNotMatch(content(root), /旧名/)
})
