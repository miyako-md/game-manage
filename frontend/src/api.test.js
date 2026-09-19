import test from 'node:test'
import assert from 'node:assert/strict'
import { refreshGame } from './api.js'

test('manual refresh sends the local API write header', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/games/nte/refresh')
    assert.equal(options.method, 'POST')
    assert.equal(options.headers['X-Game-Assistant'], '1')
    return { ok: true, json: async () => ({ results: {} }) }
  })
  assert.deepEqual(await refreshGame('nte'), { results: {} })
})
