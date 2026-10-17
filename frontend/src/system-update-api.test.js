import test from 'node:test'
import assert from 'node:assert/strict'
import { getSystemUpdate, checkSystemUpdate, applySystemUpdate } from './system-update-api.js'
import { configureHttpClient, invalidateSession, setAccountScope } from './http-client.js'

const OLD = '1'.repeat(40), TARGET = '2'.repeat(40)
const reply = body => new Response(JSON.stringify(body))
test('update requests use the common local headers and exact target body', async t => {
  configureHttpClient({ mode: 'local' })
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options) => { calls.push({ path, options }); return reply({ current: { sha: OLD } }) })
  await getSystemUpdate()
  await checkSystemUpdate()
  await applySystemUpdate({ expected_sha: OLD, target_sha: TARGET, extra: 'not sent' })
  assert.deepEqual(calls.map(call => [call.path, call.options.method]), [
    ['/api/system/update', 'GET'], ['/api/system/update/check', 'POST'], ['/api/system/update/apply', 'POST'],
  ])
  assert.equal(calls[0].options.headers['X-Game-Assistant'], undefined)
  for (const call of calls.slice(1)) assert.equal(call.options.headers['X-Game-Assistant'], '1')
  assert.equal(calls[1].options.body, '{}')
  assert.deepEqual(JSON.parse(calls[2].options.body), { expected_sha: OLD, target_sha: TARGET })
  assert.ok(calls.every(call => call.options.credentials === 'same-origin' && call.options.cache === 'no-store'))
})

test('cloud update requests remain session-level and use CSRF instead of a game-owner route', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  setAccountScope({ user_id: 'u', account_id: 'a', role_id: 'r', provider: 'skland' })
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    calls.push({ path, options }); return reply(path === '/api/identity/csrf' ? { csrf_token: 'session-csrf' } : { ok: true })
  })
  await checkSystemUpdate(); await applySystemUpdate({ expected_sha: OLD, target_sha: TARGET })
  const writes = calls.filter(call => call.options.method === 'POST')
  assert.deepEqual(writes.map(call => call.path), ['/api/system/update/check', '/api/system/update/apply'])
  assert.ok(writes.every(call => call.options.headers['X-CSRF-Token'] === 'session-csrf'))
})

test('a late version response from an ended session is discarded', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  let resolve
  t.mock.method(globalThis, 'fetch', () => new Promise(done => { resolve = done }))
  const pending = getSystemUpdate()
  invalidateSession(); resolve(reply({ latest: { sha: TARGET } }))
  await assert.rejects(pending, error => error.name === 'AbortError')
})
