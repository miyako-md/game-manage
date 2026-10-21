import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { configureHttpClient, invalidateSession } from './http-client.js'
import { collectProgress, createCollectController, COLLECT_LIMIT_MS, COLLECT_POLL_MS } from './cloud-collect.js'

const tick = async () => { for (let i = 0; i < 4; i++) { await new Promise(resolve => setImmediate(resolve)); await nextTick() } }
const json = (value, init) => new Response(JSON.stringify(value), init)

function server(t, status) {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    calls.push([path, options])
    if (path.endsWith('/csrf')) return json({ csrf_token: 'fixture' })
    if (options.method === 'POST') return json({ games: [{ game_id: 'wuthering_waves', state: 'queued', job_id: 'a', generation: 3 }, { game_id: 'endfield', state: 'merged', job_id: 'b', generation: 0 }], private_refresh: { requested: 4, skipped: 0 }, backfill: true })
    return json(status())
  })
  return calls
}

test('a game is finished only after a job completes past its receipt, and backoff or failures are named', () => {
  const receipt = { generation: 2 }
  assert.equal(collectProgress(receipt, undefined), 'queued')
  assert.equal(collectProgress(receipt, { queue_state: 'running', generation: 2, outcome: { state: 'done' } }), 'running')
  assert.equal(collectProgress(receipt, { queue_state: 'idle', generation: 2, outcome: { state: 'done' } }), 'queued')
  assert.equal(collectProgress(receipt, { queue_state: 'idle', generation: 3, outcome: { state: 'done', bilibili: 'ok' } }), 'done')
  assert.equal(collectProgress(receipt, { queue_state: 'idle', generation: 3, outcome: { state: 'done', bilibili: 'backoff' } }), 'backoff')
  assert.equal(collectProgress(receipt, { queue_state: 'queued', generation: 3, outcome: { state: 'failed', bilibili: 'error' } }), 'failed')
})

test('collect posts once, follows per-game progress and re-reads the overview when every game is done', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] })
  let rows = [{ game_id: 'wuthering_waves', queue_state: 'running', generation: 3, outcome: null }, { game_id: 'endfield', queue_state: 'queued', generation: 0, outcome: null }]
  const calls = server(t, () => ({ games: rows, retry_after: 300 }))
  let done = 0
  const collect = createCollectController({ onDone: () => done++ }); t.after(collect.dispose)
  await collect.start(); await tick()
  const post = calls.find(([, o]) => o.method === 'POST')
  assert.equal(post[0], '/api/admin/collect')
  assert.deepEqual(JSON.parse(post[1].body), { backfill: true })
  assert.equal(post[1].headers['X-CSRF-Token'], 'fixture')
  assert.equal(collect.state.busy, true)
  assert.equal(collect.state.privateRequested, 4)
  assert.deepEqual(collect.state.games.map(g => [g.name, g.progress]), [['鸣潮', 'queued'], ['终末地', 'queued']])
  t.mock.timers.tick(COLLECT_POLL_MS); await tick()
  assert.deepEqual(collect.state.games.map(g => g.progress), ['running', 'queued'])
  rows = [{ game_id: 'wuthering_waves', queue_state: 'idle', generation: 4, outcome: { state: 'done', bilibili: 'ok', failed: [] } }, { game_id: 'endfield', queue_state: 'idle', generation: 1, outcome: { state: 'done', bilibili: 'backoff', failed: [] } }]
  t.mock.timers.tick(COLLECT_POLL_MS); await tick()
  assert.deepEqual(collect.state.games.map(g => g.progress), ['done', 'backoff'])
  assert.equal(collect.state.busy, false)
  assert.equal(done, 1)
  assert.match(collect.state.message, /采集完成/)
  const reads = calls.length
  t.mock.timers.tick(COLLECT_LIMIT_MS); await tick()
  assert.equal(calls.length, reads, 'polling stops once done')
  assert.equal(calls.filter(([, o]) => o.method === 'POST').length, 1)
})

test('collect stops polling after about five minutes and says the work continues in the background', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] })
  const calls = server(t, () => ({ games: [{ game_id: 'wuthering_waves', queue_state: 'running', generation: 3, outcome: null }, { game_id: 'endfield', queue_state: 'queued', generation: 0, outcome: null }] }))
  let done = 0
  const collect = createCollectController({ onDone: () => done++ }); t.after(collect.dispose)
  await collect.start(); await tick()
  for (let elapsed = 0; elapsed <= COLLECT_LIMIT_MS + COLLECT_POLL_MS; elapsed += COLLECT_POLL_MS) { t.mock.timers.tick(COLLECT_POLL_MS); await tick() }
  assert.equal(collect.state.busy, false)
  assert.match(collect.state.message, /仍在后台进行/)
  assert.equal(done, 0)
  const reads = calls.length
  t.mock.timers.tick(COLLECT_LIMIT_MS); await tick()
  assert.equal(calls.length, reads)
})

test('a cooldown answer names the wait and a lost session clears the progress', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  t.mock.method(globalThis, 'fetch', async (path, options) => path.endsWith('/csrf') ? json({ csrf_token: 'fixture' })
    : json({ detail: 'collect_cooldown', retry_after: 240 }, { status: 429, headers: { 'Retry-After': '240' } }))
  const collect = createCollectController(); t.after(collect.dispose)
  await collect.start(); await tick()
  assert.equal(collect.state.busy, false)
  assert.match(collect.state.error, /4 分钟后再试/)
  invalidateSession()
  assert.equal(collect.state.error, '')
})
