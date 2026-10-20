import test from 'node:test'
import assert from 'node:assert/strict'
import { getRecords, pityText, pityParts, pullDay } from './endfield-gacha-api.js'
import { configureHttpClient, setAccountScope } from './http-client.js'
function serve(t, handler) {
  const old = globalThis.fetch; t.after(() => { globalThis.fetch = old })
  globalThis.fetch = handler
}
test('an unreachable local service gives a Chinese message instead of the raw fetch error', async t => {
  serve(t, async () => { throw new TypeError('Failed to fetch') })
  await assert.rejects(getRecords(), error => error.message === '无法连接服务，请稍后重试')
})
test('an abort reaches the caller unchanged', async t => {
  const aborted = Object.assign(new Error('The operation was aborted.'), { name: 'AbortError' })
  serve(t, async () => { throw aborted })
  await assert.rejects(getRecords(), error => error === aborted)
})

test('weapon category requests keep the server kind filter alongside pagination and exact pools', async t => {
  const calls = []
  serve(t, async url => { calls.push(new URL(url, 'http://localhost')); return new Response(JSON.stringify({ total: 0, records: [] })) })
  await getRecords('', 50, 50, 'weapon')
  assert.equal(calls[0].searchParams.get('kind'), 'weapon')
  assert.equal(calls[0].searchParams.get('offset'), '50')
  assert.equal(calls[0].searchParams.get('pool_key'), '')
  await getRecords('weapon:one', 0, 50)
  assert.equal(calls[1].searchParams.get('pool_key'), 'weapon:one')
  assert.equal(calls[1].searchParams.has('kind'), false)
})

test('cloud weapon pagination keeps its filter on the owned Eagle account route', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  setAccountScope({ account_id: 'eagle-account', role_id: 'role-one', provider: 'hypergryph' })
  let called
  serve(t, async url => { called = new URL(url, 'http://localhost'); return new Response(JSON.stringify({ total: 0, records: [] })) })
  await getRecords('', 100, 50, 'weapon')
  assert.equal(called.pathname, '/api/accounts/eagle-account/roles/role-one/endfield/gacha/records')
  assert.equal(called.searchParams.get('kind'), 'weapon')
  assert.equal(called.searchParams.get('offset'), '100')
})
test('server errors keep their own message and a non-JSON page is replaced by fixed text', async t => {
  serve(t, async () => new Response(JSON.stringify({ detail: '没有可用的寻访记录' }), { status: 409 }))
  await assert.rejects(getRecords(), /没有可用的寻访记录/)
  globalThis.fetch = async () => new Response('<html>Bad Gateway</html>', { status: 502 })
  await assert.rejects(getRecords(), error => error.message === '寻访账本服务返回异常，请稍后重试')
})
test('a machine code answered by the cloud service is replaced by fixed Chinese text', async t => {
  serve(t, async () => new Response(JSON.stringify({ detail: 'authorization_changed' }), { status: 409 }))
  await assert.rejects(getRecords(), error => error.message === '寻访账本请求失败，请稍后重试')
})

test('pity parts split the big numeral from its unit and agree with the plain wording', () => {
  for (const pity of [{ count: 20, status: 'lower_bound' }, { count: 0, status: 'exact' }, { count: 17, status: 'exact' }]) {
    const parts = pityParts(pity)
    assert.equal(`${parts.prefix}${parts.count} ${parts.unit}`, pityText(pity))
  }
  assert.equal(pityParts({ count: 3, status: 'unknown' }).prefix, '≥')
  for (const missing of [null, undefined, {}, { count: 1.5 }, { count: '3' }]) { assert.equal(pityParts(missing), null); assert.equal(pityText(missing), '未知') }
})

test('pull days use the Beijing calendar and tolerate a missing time', () => {
  assert.equal(pullDay(Date.UTC(2026, 9, 16, 17, 0)), '10月17日')
  assert.equal(pullDay(Date.UTC(2026, 9, 16, 15, 59)), '10月16日')
  assert.equal(pullDay(null), '时间未提供')
  assert.equal(pullDay(NaN), '时间未提供')
})
