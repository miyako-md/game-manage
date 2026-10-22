import test from 'node:test'
import assert from 'node:assert/strict'
import { configureHttpClient } from './http-client.js'
import { getCloudGuideStatus, checkCloudGuides } from './cloud-guides-api.js'

const json = (value, status = 200, headers = {}) => new Response(JSON.stringify(value), { status, headers })
const csrf = path => path.endsWith('/csrf') ? json({ csrf_token: 'fixture' }) : null
const cloud = t => { configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' })) }

test('cooldown and scheduler errors become fixed text with the retry time kept', async t => {
  cloud(t)
  t.mock.method(globalThis, 'fetch', async path => csrf(path) || json({ detail: 'guide_check_cooldown', retry_after: 420 }, 429, { 'Retry-After': '420' }))
  const cooling = await checkCloudGuides().catch(error => error)
  assert.equal(cooling.message, '立即检查冷却中，请稍后再试'); assert.equal(cooling.status, 429); assert.equal(cooling.retryAfter, 420)
  t.mock.method(globalThis, 'fetch', async path => csrf(path) || json({ detail: 'scheduler_unavailable' }, 503))
  const down = await checkCloudGuides().catch(error => error)
  assert.equal(down.message, '后台调度暂不可用，请稍后重试'); assert.equal(down.detail, 'scheduler_unavailable')
  t.mock.method(globalThis, 'fetch', async path => csrf(path) || json({ detail: 'Traceback private' }, 500))
  assert.equal((await getCloudGuideStatus().catch(error => error)).message, '攻略更新状态暂不可用，请稍后重试')
})

test('a status without the contract sections is rejected instead of shown as empty', async t => {
  cloud(t)
  t.mock.method(globalThis, 'fetch', async () => json({ job: { state: 'idle' } }))
  await assert.rejects(getCloudGuideStatus(), /响应异常/)
})
