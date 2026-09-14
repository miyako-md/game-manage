import test from 'node:test'
import assert from 'node:assert/strict'
import { getAuthStatus, createAuthSession, sendAuthSms, loginAuth, logoutAuth } from './auth-api.js'

test('auth requests preserve session/captcha and protect every write with the application header', async (t) => {
  const requests = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, ...options })
    return new Response(JSON.stringify({ ok: true, accounts: {} }))
  })
  await getAuthStatus()
  await createAuthSession('wuthering_waves')
  const captcha = { captcha_id: 'captcha-id', lot_number: 'lot', captcha_output: 'answer', pass_token: 'pass', gen_time: 'time' }
  await sendAuthSms('wuthering_waves', { session_id: 'one-session', mobile: '13800000000', captcha })
  await loginAuth('wuthering_waves', { session_id: 'one-session', mobile: '13800000000', code: '012345' })
  await logoutAuth('nte')
  assert.equal(requests[0].url, '/api/auth/status')
  assert.equal(requests[0].method, 'GET')
  assert.deepEqual(requests.slice(1).map((r) => [r.url, r.method]), [
    ['/api/auth/wuthering_waves/sessions', 'POST'],
    ['/api/auth/wuthering_waves/sms', 'POST'],
    ['/api/auth/wuthering_waves/login', 'POST'],
    ['/api/auth/nte', 'DELETE'],
  ])
  for (const request of requests.slice(1)) {
    assert.equal(request.headers['X-Game-Assistant'], '1')
    assert.equal(request.credentials, 'same-origin')
  }
  assert.deepEqual(JSON.parse(requests[2].body).captcha, captcha)
  assert.equal(JSON.parse(requests[2].body).session_id, JSON.parse(requests[3].body).session_id)
  assert.equal(JSON.parse(requests[3].body).code, '012345')
})

test('429 preserves the safe detail and Retry-After for the SMS countdown', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ detail: '短信发送过于频繁' }), {
    status: 429, headers: { 'Retry-After': '37' },
  }))
  await assert.rejects(createAuthSession('nte'), (error) => {
    assert.equal(error.status, 429)
    assert.equal(error.retryAfter, 37)
    assert.equal(error.message, '短信发送过于频繁')
    return true
  })
})

test('410 retains the expired status for session restart', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ detail: '登录会话已过期' }), { status: 410 }))
  await assert.rejects(loginAuth('nte', {}), (error) => error.status === 410 && error.message === '登录会话已过期')
})

test('non-string errors never expose validation objects or HTML responses', async (t) => {
  for (const body of ['<html>private upstream diagnostic</html>', JSON.stringify({ detail: [{ input: 'private-value' }] })]) {
    t.mock.method(globalThis, 'fetch', async () => new Response(body, { status: 500 }))
    await assert.rejects(getAuthStatus(), (error) => error.status === 500 && error.message === '登录服务暂时不可用，请稍后重试')
  }
})

test('network errors use a safe recoverable message', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new Error('private network details') })
  await assert.rejects(getAuthStatus(), (error) => error.status === 0 && error.message === '无法连接登录服务，请检查网络后重试')
})

test('invalid success responses cannot be treated as successful login', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('unexpected response'))
  await assert.rejects(loginAuth('nte', {}), /登录服务响应异常，请重试/)
})

test('login allows the multi-step upstream exchange 120 seconds while other operations retain 30 seconds', async (t) => {
  const timeouts = []
  t.mock.method(AbortSignal, 'timeout', (milliseconds) => {
    timeouts.push(milliseconds)
    return new AbortController().signal
  })
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ ok: true })))
  await getAuthStatus()
  await createAuthSession('nte')
  await sendAuthSms('nte', {})
  await loginAuth('nte', {})
  await logoutAuth('nte')
  assert.deepEqual(timeouts, [30000, 30000, 30000, 120000, 30000])
})
