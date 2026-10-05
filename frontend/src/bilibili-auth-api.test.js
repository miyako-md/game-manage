import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
const url = new URL('./bilibili-auth-api.js', import.meta.url)
async function api() { assert.ok(existsSync(url), 'Bilibili API missing'); return import(url) }
test('Bilibili routes use separate prefix, same-origin writes, signal and raw password/code', async t => {
  const a = await api(); const requests = []
  t.mock.method(globalThis,'fetch', async (url, options) => { requests.push({url,...options}); return new Response('{}') })
  const signal = new AbortController().signal
  await a.createBilibiliSession('qr', signal)
  await a.submitBilibiliPassword('FAKE', {password:' FAKE_PASSWORD ',proof:{}}, signal)
  await a.submitBilibiliSms('FAKE','012345', signal)
  await a.cancelBilibiliSession('FAKE', signal)
  assert.equal(requests[0].url, '/api/auth/bilibili-source/login/sessions')
  for (const r of requests) { assert.equal(r.headers['X-Game-Assistant'],'1'); assert.equal(r.credentials,'same-origin'); assert.ok(r.signal) }
  assert.equal(JSON.parse(requests[1].body).password, ' FAKE_PASSWORD ')
  assert.equal(JSON.parse(requests[2].body).code, '012345')
})
test('pending-save and cooldown survive safe error handling; HTML is never displayed', async t => {
  const a = await api()
  t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify({detail:'稍后保存',state:'pending_save',error_code:'COLLECTION_BUSY',retry_after:60}), {status:409}))
  await assert.rejects(a.commitBilibiliSession('FAKE'), e=>e.status===409&&e.state==='pending_save'&&e.errorCode==='COLLECTION_BUSY'&&e.retryAfter===60)
  globalThis.fetch = async()=>new Response('<html>FAKE_SECRET</html>',{status:502})
  await assert.rejects(a.pollBilibiliQr('FAKE'),e=>!e.message.includes('FAKE_SECRET'))
})
