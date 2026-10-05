import test from 'node:test'
import assert from 'node:assert/strict'
import { getLolEsports, refreshLolEsports } from './lol-esports-api.js'
const snap = { payload: { schema_version: 1 } }
test('cached read and dedicated refresh only use local esports endpoints', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => { calls.push([url, options]); return new Response(JSON.stringify(options.method === 'POST' ? { ok: true, snapshot: snap } : snap)) })
  await getLolEsports(); await refreshLolEsports()
  assert.equal(calls[0][0], '/api/games/league_of_legends/snapshot/esports')
  assert.equal(calls[1][0], '/api/lol/esports/refresh')
  assert.equal(calls[1][1].headers['X-Game-Assistant'], '1')
})
test('unknown schema and source cooldown are explicit', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('{"payload":{"schema_version":99}}'))
  await assert.rejects(getLolEsports(), /版本/)
  t.mock.method(globalThis, 'fetch', async () => new Response('{}', { status: 429, headers: { 'Retry-After': '60' } }))
  await assert.rejects(refreshLolEsports(), /60/)
})
