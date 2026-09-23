import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
const Panel = await loadVue(new URL('./NteGachaLedger.vue', import.meta.url))
const flush = async () => { await new Promise(setImmediate); await nextTick() }
const button = (root, label) => nodes(root, 'button').find(n => content(n) === label)
function api(t, handler) {
  const old = globalThis.fetch; t.after(() => { globalThis.fetch = old })
  globalThis.fetch = async (url, init) => new Response(JSON.stringify(await handler(url, init)), { status: 200 })
}
const read = url => url.includes('/summary') ? { total_records: 0, pools: [] } : url.includes('/rules') ? { rules: [] } : { total: 0, records: [] }
test('missing identity does not read private ledger and shows login guidance', async t => {
  let calls = 0; api(t, () => { calls++; return {} })
  const root = mount(t, Panel, { accountId: '' }); await flush()
  assert.equal(calls, 0); assert.match(content(root), /登录异环/)
})
test('file import requires preview, carries confirmations, and changing coverage invalidates preview', async t => {
  const sent = []
  api(t, (url, init) => {
    if (!init?.body) return read(url)
    const body = JSON.parse(init.body); sent.push([url, body])
    if (url.endsWith('preview')) return { preview_id: 'ticket', record_count: 2, new_records: 2, duplicates: 0, warnings: [], missing_requirements: [] }
    return { imported: 2, duplicates: 0 }
  })
  const root = mount(t, Panel, { accountId: 'r' }); await flush()
  const file = nodes(root, 'input').find(n => n.props.type === 'file')
  await file.props.onChange({ target: { files: [{ name: 'records.json', size: 30, text: async () => '{"format":"test"}' }] } }); await nextTick()
  await button(root, '校验并预览').props.onClick(); await nextTick()
  assert.match(content(root), /新增 2/)
  const confirm = nodes(nodes(root, 'label').find(n => content(n).includes('记录包含截至导出时')), 'input')[0]
  confirm.props['onUpdate:modelValue'](true); await nextTick()
  assert.equal(button(root, '确认导入到本机'), undefined)
  await button(root, '校验并预览').props.onClick(); await nextTick()
  await button(root, '确认导入到本机').props.onClick(); await flush()
  assert.equal(sent.at(-1)[1].preview_id, 'ticket'); assert.equal(sent.at(-1)[1].latest_confirmed, true)
  assert.match(content(root), /导入完成/)
})
test('old account read cannot replace the currently selected account', async t => {
  let release
  api(t, url => url.endsWith('/summary') ? new Promise(resolve => { release = resolve }) : read(url))
  const props = reactive({ accountId: 'old' }), root = mount(t, Panel, props)
  await nextTick(); props.accountId = ''; await nextTick(); release({ total_records: 999, pools: [] }); await flush()
  assert.doesNotMatch(content(root), /999/)
})
test('a slower previous file read cannot overwrite the newly selected file', async t => {
  let release, received
  api(t, (url, init) => {
    if (!init?.body) return read(url)
    received = JSON.parse(init.body).document
    return { preview_id: 'ticket', record_count: 1, new_records: 1 }
  })
  const root = mount(t, Panel, { accountId: 'r' }); await flush()
  const file = nodes(root, 'input').find(n => n.props.type === 'file')
  const pending = file.props.onChange({ target: { files: [{ name: 'old.json', size: 20, text: () => new Promise(resolve => { release = resolve }) }] } })
  await file.props.onChange({ target: { files: [{ name: 'new.json', size: 20, text: async () => '{"file":"new"}' }] } })
  release('{"file":"old"}'); await pending; await nextTick()
  await button(root, '校验并预览').props.onClick(); assert.equal(received.file, 'new')
})
test('selecting another file requires new identity and coverage confirmations', async t => {
  let body
  api(t, (url, init) => {
    if (!init?.body) return read(url)
    body = JSON.parse(init.body); return { preview_id: 'ticket', record_count: 1 }
  })
  const root = mount(t, Panel, { accountId: 'r' }); await flush()
  const file = nodes(root, 'input').find(n => n.props.type === 'file')
  await file.props.onChange({ target: { files: [{ name: 'a.json', size: 2, text: async () => '{}' }] } })
  for (const box of nodes(root, 'input').filter(n => n.props.type === 'checkbox')) box.props['onUpdate:modelValue'](true)
  await nextTick()
  await file.props.onChange({ target: { files: [{ name: 'b.json', size: 2, text: async () => '{}' }] } }); await nextTick()
  await button(root, '校验并预览').props.onClick()
  assert.equal(body.latest_confirmed, false); assert.equal(body.continuity_confirmed, false); assert.equal(body.identity_confirmed, false)
})
test('segmented export continues from the server next offset rather than assuming fixed segment size', async t => {
  const oldDocument = globalThis.document
  const oldDocumentClass = globalThis.Document, oldShadowRoot = globalThis.ShadowRoot
  globalThis.Document = class Document {}
  globalThis.ShadowRoot = class ShadowRoot {}
  globalThis.document = { createElement: () => ({ click() {} }) }
  t.after(() => { globalThis.document = oldDocument; globalThis.Document = oldDocumentClass; globalThis.ShadowRoot = oldShadowRoot })
  const offsets = []
  api(t, url => {
    if (!url.includes('/export?')) return read(url)
    const start = Number(new URL(url, 'http://local').searchParams.get('offset')); offsets.push(start)
    return { records: [{ uid: 'test' }], export_page: { offset: start, limit: 1234, total: 2468, next_offset: start ? null : 1234 } }
  })
  const root = mount(t, Panel, { accountId: 'r' }); await flush()
  const segmented = nodes(nodes(root, 'label').find(n => content(n).includes('分段导出大账本')), 'input')[0]
  segmented.props['onUpdate:modelValue'](true); await nextTick()
  await button(root, '导出记录').props.onClick(); await nextTick()
  assert.match(content(root), /下一段从第 1235 条/)
  button(root, '下载下一段').props.onClick(); await flush()
  assert.deepEqual(offsets, [0, 1234]); assert.match(content(root), /已到末尾/)
})
test('pool cards and record rows render the backend ledger fields', async t => {
  api(t, url => url.includes('/summary')
    ? { total_records: 1, pools: [{ pool_id: 'Lottery_LimitedCharacter', total_records: 1, total_pulls: 1, pity: { status: 'lower_bound', count: 1 }, warnings: [] }] }
    : url.includes('/rules') ? { rules: [] }
      : { total: 1, records: [{ uid: 'r1', pool_group_id: 'Lottery_LimitedCharacter', timestamp: '2026-09-12 10:00:00', reward_id: 'c1', reward_name: '', reward_rank: 'S', quantity: 1, result_type: 'dice' }] })
  const root = mount(t, Panel, { accountId: '100001' }); await flush(); await flush()
  const card = nodes(root, 'article').find(n => content(n).includes('当前垫抽'))
  assert.match(content(card), /限定角色棋盘/); assert.match(content(card), /已导入 1 次计数抽取/)
  const cells = nodes(root, 'td').map(content)
  assert.deepEqual(cells, ['2026-09-12 10:00:00', '限定角色棋盘', 'c1', 'S', '1', '计数投掷'])
})
