import test from 'node:test'
import assert from 'node:assert/strict'
import { h, ref } from 'vue'
import { mount } from './test-utils/vue.js'
import { wuwaRequest, useWuwaRequest } from './wuwa-api.js'

function requestHarness(t, identity) {
  let api
  mount(
    t,
    {
      setup() {
        api = useWuwaRequest(() => identity.value)
        return () => h('div')
      },
    },
    {},
  )
  return api
}
test('private request rejects a successful HTTP response owned by another account or server', async (t) => {
  let payload = { role_id: 'other', server_id: 'server' }
  t.mock.method(globalThis, 'fetch', async () => ({
    ok: true,
    json: async () => ({ payload }),
  }))
  const api = requestHarness(t, ref('account:server'))
  await assert.rejects(api.run('roles/1501'), /账号会话已变化/)
  payload = { role_id: 'account', server_id: 'other-server' }
  await assert.rejects(api.run('roles/1501'), /账号会话已变化/)
})
test('explicit writes protect their local route and never reflect error body authorization', async (t) => {
  let observed,
    bodyRead = false
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    observed = { url, options }
    return {
      ok: false,
      status: 422,
      json: async () => {
        bodyRead = true
        return { detail: 'SECRET' }
      },
    }
  })
  await assert.rejects(
    wuwaRequest('gacha/import', {
      body: { url: 'https://example.invalid/?record_id=SECRET' },
    }),
    (error) =>
      /参数无效/.test(error.message) && !error.message.includes('SECRET'),
  )
  assert.equal(observed.url, '/api/wuwa/gacha/import')
  assert.equal(observed.options.headers['X-Game-Assistant'], '1')
  assert.equal(observed.options.referrerPolicy, 'no-referrer')
  assert.equal(observed.options.cache, 'no-store')
  assert.equal(bodyRead, false)
})
test('account switch aborts the transport and discards even a late successful result', async (t) => {
  let finish, signal
  t.mock.method(globalThis, 'fetch', (_url, options) => {
    signal = options.signal
    return new Promise((resolve) => {
      finish = resolve
    })
  })
  const identity = ref('account:server'),
    api = requestHarness(t, identity)
  const pending = api.run('gacha')
  identity.value = 'other:server'
  assert.equal(signal.aborted, true)
  finish({
    ok: true,
    json: async () => ({
      role_id: 'account',
      server_id: 'server',
      items: [{ name: 'private' }],
    }),
  })
  assert.equal(await pending, null)
})
