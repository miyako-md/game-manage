import test from 'node:test'
import assert from 'node:assert/strict'
import { pityLabel, ledgerDate, poolLabel, previewLedger } from './nte-gacha-api.js'
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
test('a null error body stays on the fixed ledger message', async t => {
  const old = globalThis.fetch; t.after(() => { globalThis.fetch = old })
  globalThis.fetch = async () => new Response('null', { status: 500, headers: { 'content-type': 'application/json' } })
  await assert.rejects(previewLedger({}), /账本请求失败/)
})
