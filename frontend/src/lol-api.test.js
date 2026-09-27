import test from 'node:test'
import assert from 'node:assert/strict'
import { getLolAnalysis, collectLol, getLolMatch } from './lol-api.js'

test('analysis filters preserve all-time zero and omit all queue', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => { calls.push({ url, options }); return new Response('{}') })
  await getLolAnalysis({ days: 0, queue: '' })
  await getLolAnalysis({ days: 7, queue: '2400' })
  assert.equal(calls[0].url, '/api/lol/analysis?days=0')
  assert.equal(calls[1].url, '/api/lol/analysis?days=7&queue_id=2400')
  assert.equal(calls[0].options.cache, 'no-store')
})

test('collect is an explicit protected local write and failures never reflect body', async t => {
  let observed, bodyRead = false
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    observed = { url, options }
    return { ok: false, status: 503, json: async () => { bodyRead = true; return { detail: 'secret' } } }
  })
  await assert.rejects(collectLol(), /客户端/)
  assert.equal(observed.url, '/api/lol/collect')
  assert.equal(observed.options.method, 'POST')
  assert.equal(observed.options.headers['X-Game-Assistant'], '1')
  assert.equal(bodyRead, false)
})

test('archive detail uses the local archived endpoint and encodes identifiers', async t => {
  let url
  t.mock.method(globalThis, 'fetch', async value => { url = value; return new Response('{"payload":{}}') })
  await getLolMatch('a/b')
  assert.equal(url, '/api/lol/matches/a%2Fb')
})
