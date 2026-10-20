import test from 'node:test'
import assert from 'node:assert/strict'
import { pityLabel, ledgerDate, poolLabel, previewLedger, importLedger, getLedgerSummary } from './nte-gacha-api.js'
test('pity distinguishes exact, lower bound and unknown, including a real zero', () => {
  assert.equal(pityLabel({ status: 'exact', count: 0 }), '0 抽')
  assert.equal(pityLabel({ status: 'lower_bound', count: 12 }), '至少 12 抽')
  assert.equal(pityLabel({ status: 'unknown', count: 12 }), '未知')
  assert.equal(ledgerDate('2026-09-16 10:11:12'), '2026-09-16 10:11:12')
  assert.equal(ledgerDate(null), '未提供')
  assert.equal(poolLabel('Lottery_Permanent'), '常驻棋盘')
})
test('import preview writes only to local ledger with required header and reports safe validation errors', async t => {
  const old = globalThis.fetch; t.after(() => { globalThis.fetch = old })
  globalThis.fetch = async (url, init) => {
    assert.equal(url, '/api/nte/gacha/preview'); assert.equal(init.headers['X-Game-Assistant'], '1')
    assert.equal(JSON.parse(init.body).latest_confirmed, false)
    return new Response(JSON.stringify({ detail: '文件角色身份与当前异环角色不一致' }), { status: 409 })
  }
  await assert.rejects(previewLedger({ document: {}, latest_confirmed: false }), /角色身份/)
})
test('a machine code answered by the cloud service is replaced by fixed Chinese text', async t => {
  const old = globalThis.fetch; t.after(() => { globalThis.fetch = old })
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'authorization_changed' }), { status: 409 })
  await assert.rejects(previewLedger({ document: {} }), error => error.message === '账本请求失败，请检查导入文件或当前账号')
})
test('an unreachable local service gives a Chinese message instead of the raw fetch error', async t => {
  const old = globalThis.fetch; t.after(() => { globalThis.fetch = old })
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
  await assert.rejects(getLedgerSummary(), error => error.message === '无法连接服务，请稍后重试')
})
test('an abort reaches the caller unchanged', async t => {
  const old = globalThis.fetch; t.after(() => { globalThis.fetch = old })
  const aborted = Object.assign(new Error('The operation was aborted.'), { name: 'AbortError' })
  globalThis.fetch = async () => { throw aborted }
  await assert.rejects(getLedgerSummary(), error => error === aborted)
})

test('NTE preview and import bound their actual UTF-8 JSON request including confirmation metadata', async t => {
  const limit = 8 * 1024 * 1024
  let calls = 0
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    calls++
    assert.equal(new TextEncoder().encode(options.body).byteLength, limit)
    return new Response('{}')
  })
  for (const send of [previewLedger, importLedger]) {
    const body = { document: { name: '中文', padding: '' }, latest_confirmed: false, preview_id: 'ticket' }
    const overhead = new TextEncoder().encode(JSON.stringify(body)).byteLength
    body.document.padding = 'a'.repeat(limit - overhead)
    await send(body)
    body.document.padding += 'a'
    await assert.rejects(send(body), /连同确认信息超过 8 MB.*当前账本未更改/)
    body.document.padding = '汉'.repeat(Math.ceil((limit - overhead) / 3))
    assert.ok(JSON.stringify(body).length < limit)
    await assert.rejects(send(body), /超过 8 MB/)
  }
  assert.equal(calls, 2)
})
