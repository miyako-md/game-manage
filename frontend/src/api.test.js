import test from 'node:test'
import assert from 'node:assert/strict'
import { getSnapshot, refreshGame } from './api.js'

test('manual refresh sends the local API write header', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/games/nte/refresh')
    assert.equal(options.method, 'POST')
    assert.equal(options.headers['X-Game-Assistant'], '1')
    return { ok: true, json: async () => ({ results: {} }) }
  })
  assert.deepEqual(await refreshGame('nte'), { results: {} })
})


test('local snapshot body reads share the request deadline and preserve timeout errors', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let bodyStarted, signal
  const started = new Promise(resolve => { bodyStarted = resolve })
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    signal = options.signal
    assert.equal('readResponse' in options, false)
    return { ok: true, status: 200, json: () => { bodyStarted(); return new Promise(() => {}) } }
  })
  const pending = getSnapshot('nte', 'stamina')
  const rejected = assert.rejects(pending, error => error.name === 'RequestTimeoutError')
  await started
  t.mock.timers.tick(20000)
  await rejected
  assert.equal(signal.aborted, true)
})

test('local snapshot reads preserve HTTP and JSON failures and stop on cancellation', async t => {
  let read = false
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, status: 404, json: () => { read = true } }))
  await assert.rejects(getSnapshot('nte', 'stamina'), error => error.constructor === Error && error.message === '404')
  assert.equal(read, false)
  t.mock.method(globalThis, 'fetch', async () => ({ ok: true, json: async () => { throw new SyntaxError('invalid JSON') } }))
  await assert.rejects(getSnapshot('nte', 'stamina'), SyntaxError)
  let bodyStarted
  const started = new Promise(resolve => { bodyStarted = resolve })
  t.mock.method(globalThis, 'fetch', async () => ({ ok: true, json: () => { bodyStarted(); return new Promise(() => {}) } }))
  const controller = new AbortController()
  const pending = getSnapshot('nte', 'stamina', { signal: controller.signal })
  const rejected = assert.rejects(pending, error => error.name === 'AbortError')
  await started; controller.abort(); await rejected
})
