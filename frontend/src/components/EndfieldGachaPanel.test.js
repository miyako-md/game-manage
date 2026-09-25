import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
const Panel = await loadVue(new URL('./EndfieldGachaPanel.vue', import.meta.url))
const flush = async () => { await new Promise(setImmediate); await nextTick() }
function api(t, handler) {
  const old = globalThis.fetch, calls = []
  t.after(() => { globalThis.fetch = old })
  globalThis.fetch = async url => { calls.push(url); const [status, body] = await handler(url); return new Response(JSON.stringify(body), { status }) }
  return calls
}
const summary = { schema_version: 1, role_id: 'r1', total: 30, complete: false, pools: [
  { key: 'E_CharacterGachaPoolType_Special', label: '特许寻访', kind: 'character', total: 30, six_star: 1, five_star: 3, free: 0,
    since_last_six: { count: 2, status: 'exact' }, gaps: 1, pending: true,
    history: [{ name: '提弗洛斯', pool_name: '冬猎', obtained_at: 1788300000000, pulls: 28, status: 'lower_bound' }] }] }
const snap = { payload: summary, fetched_at: '2026-09-24T12:00:00+08:00' }

test('pools show exact and lower-bound pity wording and an unfinished sync', async t => {
  const calls = api(t, () => [200, { total: 0, records: [] }])
  const root = mount(t, Panel, { snap, accountId: 'r1' }); await flush()
  const text = content(root)
  assert.match(text, /距上次 6★ 2 抽/)
  assert.match(text, /提弗洛斯 至少 28 抽/)
  assert.match(text, /还有未同步完的记录/)
  assert.match(text, /有未同步完的区段/)
  assert.equal(calls.length, 0) // 逐条记录未展开时不读取
})

test('opening the record list reads the selected pool and pages through the local ledger', async t => {
  const calls = api(t, url => [200, { total: 60, records: [{ seq_id: '99', pool_key: 'E_CharacterGachaPoolType_Special', name: '提弗洛斯', rarity: 6, gacha_ts: 1788300000000 }] }])
  const root = mount(t, Panel, { snap, accountId: 'r1' }); await flush()
  nodes(root, 'details')[0].props.onToggle({ target: { open: true } }); await flush()
  assert.match(calls[0], /records\?pool_key=&offset=0&limit=50/)
  assert.match(content(root), /提弗洛斯 6★/)
  await nodes(root, 'button').find(n => content(n) === '下一页').props.onClick(); await flush()
  assert.match(calls.at(-1), /offset=50/)
})

test('missing login, legacy snapshots and read errors are explained without inventing data', async t => {
  api(t, () => [409, { detail: '请先登录终末地' }])
  assert.match(content(mount(t, Panel, { snap: null, accountId: '' })), /登录终末地后/)
  assert.match(content(mount(t, Panel, { snap: { payload: { pools: summary.pools } }, accountId: 'r1' })), /尚未同步寻访记录/)
  const props = reactive({ snap, accountId: 'r1' })
  const root = mount(t, Panel, props); await flush()
  nodes(root, 'details')[0].props.onToggle({ target: { open: true } }); await flush()
  assert.match(content(root), /请先登录终末地/)
})
