import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes, choose } from '../test-utils/vue.js'
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

test('the chosen pool shows exact and lower-bound pity and an unfinished sync without reading the ledger', async t => {
  const calls = api(t, () => [200, { total: 0, records: [] }])
  const root = mount(t, Panel, { snap, accountId: 'r1' }); await flush()
  const text = content(root)
  assert.match(text, /已垫 2 抽 距上次 6★/)
  assert.match(text, /提弗洛斯 冬猎 · .* ≥28 抽/)
  assert.match(text, /还有记录未同步完/)
  assert.match(text, /部分待同步/)
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
  choose(root, '卡池', 'E_CharacterGachaPoolType_Special'); await flush()
  assert.match(calls.at(-1), /pool_key=E_CharacterGachaPoolType_Special&offset=0/)
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

test('the headline keeps operators and weapons apart, averages exact intervals only and never reads unknown as a lower bound', t => {
  api(t, () => [200, {}])
  const report = { schema_version: 1, total: 50, six_star: 2, five_star: 5, free: 0, gaps: 1, pending: true }
  const weapon = { ...summary.pools[0], key: 'weapon:w1', label: '熔铸申领', kind: 'weapon', total: 20, six_star: 1, five_star: 2, history: [{ name: '遥望', pulls: 12, status: 'exact' }] }
  const root = mount(t, Panel, { snap: { payload: { ...summary, report, pools: [{ ...summary.pools[0], history: [{ name: '未知区间', pulls: 12, status: 'unknown' }] }, weapon] } }, accountId: 'r1' })
  const kinds = by(root, 'section', 'kind-block')
  assert.deepEqual(kinds.map(node => content(node)), ['干员寻访 30 抽 6★ 1 5★ 3 平均出 6★ —', '武器申领 20 抽 6★ 1 5★ 2 平均出 6★ 只统计已展示历史中 1 次抽数准确的 6★；跨缺口或含免费寻访的区间不计入。 12 抽'])
  assert.doesNotMatch(content(root), /50 抽/) // the report's mixed total is never shown
  assert.match(content(root), /未知区间 .*抽数未知/); assert.doesNotMatch(content(root), /未知区间 .*≥12/)
  assert.match(content(root), /已知记录缺口 1 处/)
})


test('closing the ledger while its response is pending discards late private records',async t=>{
  let resolve
  api(t,()=>new Promise(done=>{resolve=()=>done([200,{total:1,records:[{name:'迟到私人记录'}]}])}))
  const root=mount(t,Panel,{snap,accountId:'r1'});nodes(root,'details')[0].props.onToggle({target:{open:true}});await flush()
  nodes(root,'details')[0].props.onToggle({target:{open:false}});await flush();resolve();await flush()
  assert.doesNotMatch(content(root),/迟到私人记录/)
})

test('pool coverage and unknown rarity are shown instead of inventing a four-star remainder', t => {
  const pool = { ...summary.pools[0], six_star: 51, four_star: null, unknown_rarity: 4, history: Array.from({ length: 50 }, () => ({ name: '报告出货' })), history_limit: 50 }
  const root = mount(t, Panel, { accountId: 'r1', snap: { payload: { ...summary, report: { schema_version: 1, pools: [pool] } } } })
  assert.match(content(root), /4★ 未知/); assert.match(content(root), /未知 \/ 其他 4/)
  assert.match(content(root), /仅显示最近 50 次 6★（账本共 51 次）/); assert.match(content(root), /逐条记录中查看或导出/)
  assert.doesNotMatch(content(root), /提弗洛斯/)
  const zero = mount(t, Panel, { accountId: 'r1', snap: { payload: { ...summary, pools: [{ ...summary.pools[0], four_star: 26, unknown_rarity: 0 }] } } })
  assert.doesNotMatch(content(zero), /未知 \/ 其他/)
  assert.match(content(zero), /6★ 1 3\.3%/)
})

const by = (root, type, name) => nodes(root, type).filter(node => String(node.props.class).split(' ').includes(name))
const history = [
  { name: '提弗洛斯', pool_name: '冬猎', obtained_at: 1788300000000, pulls: 66, status: 'exact' },
  { name: '余烬', pool_name: '熔火灼痕', obtained_at: 1786000000000, pulls: 52, status: 'lower_bound' },
]
const second = { key: 'E_CharacterGachaPoolType_Standard', label: '基础寻访', kind: 'character', total: 48, six_star: 1, five_star: 7, four_star: 40, unknown_rarity: 0, free: 0,
  since_last_six: { count: 17, status: 'exact' }, gaps: 0, pending: false, newest_at: 1790000000000, history: [{ name: '别礼', pulls: 31, status: 'lower_bound', obtained_at: 1790000000000 }] }
const wide = { ...summary.pools[0], total: 148, six_star: 2, five_star: 20, four_star: 126, unknown_rarity: 0, history, newest_at: 1788300000000 }

const tiles = root => nodes(root, 'button').filter(node => String(node.props.class).includes('pool-tile'))
const details = root => by(root, 'article', 'pool-detail')

test('a tile per operator pool type and one for all weapon banners; choosing one switches the detail and the ledger filter', async t => {
  const calls = api(t, () => [200, { total: 0, records: [] }])
  const weapon = { ...second, key: 'weapon:w1', label: '熔铸申领', kind: 'weapon', newest_at: 1791000000000, since_last_six: { count: 20, status: 'exact' }, history: [{ name: '遥望', pulls: 30, status: 'exact', obtained_at: 1790000000000 }] }
  const older = { ...weapon, key: 'weapon:w0', label: '行舟申领', newest_at: 1780000000000, since_last_six: { count: 4, status: 'exact' }, history: [] }
  const root = mount(t, Panel, { accountId: 'r1', snap: { payload: { ...summary, pools: [wide, older, second, weapon] }, fetched_at: '2026-09-24T12:00:00+08:00' } })
  assert.deepEqual(tiles(root).map(node => content(nodes(node, 'span')[0])), ['特许寻访', '基础寻访', '武器申领'])
  assert.deepEqual(tiles(root).map(node => node.props['aria-pressed']), [true, false, false])
  assert.match(content(tiles(root)[1]), /基础寻访 已垫 17 48 抽 · 6★ 1/)
  assert.match(content(tiles(root)[2]), /武器申领 当期已垫 20 96 抽 · 6★ 2 · 2 期/) // the newest weapon banner's pity
  assert.equal(details(root).length, 1); assert.match(content(details(root)[0]), /^特许寻访/)
  tiles(root)[1].props.onClick(); await flush()
  nodes(root, 'details')[0].props.onToggle({ target: { open: true } }); await flush()
  assert.match(calls.at(-1), /pool_key=E_CharacterGachaPoolType_Standard&offset=0/)
  tiles(root)[2].props.onClick(); await flush()
  assert.deepEqual(tiles(root).map(node => node.props['aria-pressed']), [false, false, true])
  const detail = details(root)[0]
  assert.match(content(detail), /^武器申领 武器申领 .*当期已垫 20 抽 熔铸申领 · 距上次 6★/)
  assert.deepEqual(by(detail, 'section', 'banner').map(node => content(nodes(node, 'header')[0])), ['熔铸申领 已垫 20 · 48 抽 · 6★ 1 · 5★ 7', '行舟申领 已垫 4 · 48 抽 · 6★ 1 · 5★ 7'])
  assert.match(calls.at(-1), /pool_key=&offset=0&limit=50&kind=weapon/) // weapons span several ledger pools, excluding operators
})

test('weapon ledger pagination retains its kind and a pool change drops late records', async t => {
  let finishOld
  const calls = api(t, url => {
    if (url.includes('offset=50')) return new Promise(resolve => { finishOld = resolve })
    return [200, { total: 60, records: [{ seq_id: 'w1', pool_key: 'weapon:w1', name: '武器记录', rarity: 4 }] }]
  })
  const weapon = { ...second, key: 'weapon:w1', kind: 'weapon', label: '武库申领' }
  const root = mount(t, Panel, { accountId: 'r1', snap: { payload: { ...summary, pools: [wide, weapon] } } })
  tiles(root)[1].props.onClick(); await flush()
  nodes(root, 'details')[0].props.onToggle({ target: { open: true } }); await flush()
  assert.match(calls.at(-1), /kind=weapon/)
  const pending = nodes(root, 'button').find(node => content(node) === '下一页').props.onClick(); await flush()
  assert.match(calls.at(-1), /offset=50&limit=50&kind=weapon/)
  tiles(root)[0].props.onClick(); await flush()
  assert.match(calls.at(-1), /pool_key=E_CharacterGachaPoolType_Special&offset=0/)
  assert.doesNotMatch(calls.at(-1), /kind=weapon/)
  finishOld([200, { total: 60, records: [{ seq_id: 'old', name: '迟到的武器记录' }] }]); await pending; await flush()
  assert.doesNotMatch(content(root), /迟到的武器记录/)
})

test('gifts stay labelled in the ledger while verified totals and legacy-record notices coexist', async t => {
  api(t, () => [200, { total: 2, records: [
    { seq_id: 'gift', pool_key: 'weapon:w1', kind: 'weapon', record_kind: 'gift_10', reward_label: '额外奖励', name: '赠送武器', rarity: 6 },
    { seq_id: 'pull', pool_key: 'weapon:w1', kind: 'weapon', record_kind: 'draw', name: '申领武器', rarity: 6 },
    { seq_id: 'old', pool_key: 'weapon:w1', kind: 'weapon', record_kind: null, name: '旧武器', rarity: 6 },
  ] }])
  const weapon = { ...second, key: 'weapon:w1', kind: 'weapon', label: '武库申领', total: 12, six_star: 1,
    gifts: 1, unverified_records: 3, history: [{ name: '正常出货', pulls: 12, status: 'exact' }, { name: '不应显示的赠礼', record_kind: 'gift', pulls: 0, status: 'exact' }] }
  const root = mount(t, Panel, { accountId: 'r1', snap: { payload: { ...summary, pools: [weapon] } } })
  assert.match(content(root), /武器申领 12 抽 6★ 1/)
  assert.match(content(root), /另有 3 条武器记录类型不明确，暂不计入统计/)
  assert.match(content(root), /超出查询期限的记录会保留在明细中/)
  assert.match(content(root), /正常出货/)
  assert.doesNotMatch(content(root), /不应显示的赠礼/)
  nodes(root, 'details')[0].props.onToggle({ target: { open: true } }); await flush()
  const table = by(root, 'table', 'records')[0], entries = nodes(table, 'tr').slice(1)
  assert.match(content(entries[0]), /赠送武器 额外奖励 6★/)
  assert.doesNotMatch(entries[0].props.class, /\bsix\b/)
  assert.match(entries[1].props.class, /\bsix\b/)
  assert.match(content(entries[2]), /旧武器 类型待核验/)
  assert.doesNotMatch(entries[2].props.class, /\bsix\b/)
  assert.match(content(root), /额外奖励不计入抽数、出货和垫抽/)
})

test('an operator pool type lists each banner with its own counts and only its own 6★', t => {
  api(t, () => [200, {}])
  const banners = [{ pool_id: 's2', name: '晨星', total: 100, six_star: 1, five_star: 9, newest_at: 1790000000000, oldest_at: 1789000000000 },
    { pool_id: 's1', name: '冬猎', total: 20, six_star: 0, five_star: 2, newest_at: 1788000000000, oldest_at: 1787000000000 },
    { pool_id: 's0', name: '熔火灼痕', total: 28, six_star: 2, five_star: 9, newest_at: 1786000000000, oldest_at: 1785000000000 }]
  const pool = { ...wide, banners, history: [{ name: '伊冯', pool_id: 's2', pool_name: '晨星', pulls: 70, status: 'exact', obtained_at: 1789500000000 },
    { name: '余烬', pool_id: 's0', pool_name: '熔火灼痕', pulls: 30, status: 'exact', obtained_at: 1785500000000 }], six_star: 3 }
  const root = mount(t, Panel, { accountId: 'r1', snap: { payload: { ...summary, pools: [pool] } } })
  assert.match(content(root), /按期统计 3 期/)
  const sections = by(details(root)[0], 'section', 'banner')
  assert.deepEqual(sections.map(node => content(nodes(node, 'strong')[0])), ['晨星', '冬猎', '熔火灼痕'])
  assert.match(content(sections[0]), /100 抽 · 6★ 1 · 5★ 9 伊冯/)
  assert.doesNotMatch(content(sections[0]), /余烬|已垫/) // operator banners share the type's pity, so none is shown per banner
  assert.match(content(sections[1]), /本期未出 6★/)
  assert.match(content(sections[2]), /余烬 .*30 抽.* 另有 1 次 6★ 不在已展示的历史中/)
  assert.ok(nodes(sections[0], 'li').every(row => !content(row).includes('晨星'))) // the header names the banner, not each row
  const legacy = mount(t, Panel, { accountId: 'r1', snap: { payload: { ...summary, pools: [{ ...pool, banners: undefined }] } } })
  assert.deepEqual(by(legacy, 'section', 'banner').map(node => content(nodes(node, 'header')[0])), ['晨星 未知 抽 · 6★ 未知 · 5★ 未知', '熔火灼痕 未知 抽 · 6★ 未知 · 5★ 未知'])
})


test('the detail paces exact intervals only and tags the fastest and slowest 6★', t => {
  api(t, () => [200, {}])
  const pool = { ...wide, history: [...history, { name: '伊冯', pool_name: '晨星于此闪耀', obtained_at: 1789000000000, pulls: 12, status: 'exact' }] }
  const root = mount(t, Panel, { accountId: 'r1', snap: { payload: { ...summary, pools: [pool] } } })
  const stats = by(root, 'dl', 'detail-stats')[0]
  assert.match(content(stats), /平均出 6★ 39 抽/) // (66 + 12) / 2, the ≥52 lower bound is left out
  assert.match(content(stats), /最欧 12 抽 伊冯/); assert.match(content(stats), /最非 66 抽 提弗洛斯/)
  const rows = by(root, 'li', 'pull-row')
  assert.deepEqual(rows.map(row => by(row, 'span', 'pull-tag').map(content)[0] ?? ''), ['最非', '', '最欧'])
  assert.ok(String(rows[1].props.class).includes('lower'))
  const one = mount(t, Panel, { accountId: 'r1', snap: { payload: { ...summary, pools: [{ ...wide, history: history.slice(0, 1) }] } } })
  assert.match(content(by(one, 'dl', 'detail-stats')[0]), /最欧 — 最非 —/)
  assert.equal(by(one, 'span', 'pull-tag').length, 0)
})

test('6★ bars share one ruler per kind, so a weapon bar is never measured against operator pulls', t => {
  api(t, () => [200, {}])
  const weapon = { ...second, key: 'weapon:w1', label: '熔铸申领', kind: 'weapon', history: [{ name: '遥望', pulls: 15, status: 'exact' }, { name: '玉中身', pulls: 30, status: 'exact' }] }
  const root = mount(t, Panel, { imageMode: true, snap: { payload: { ...summary, pools: [wide, weapon] } } })
  const widths = by(root, 'i', 'pull-fill').map(node => node.props.style.width)
  assert.deepEqual(widths, ['94.29%', '74.29%', '50%', '100%']) // 66 and 52 of 70; 15 and 30 of 30
  const unknown = mount(t, Panel, { imageMode: true, snap: { payload: { ...summary, pools: [{ ...wide, history: [{ name: '?', pulls: null, status: 'unknown' }] }] } } })
  assert.deepEqual(by(unknown, 'i', 'pull-fill').map(node => node.props.style.width), ['0%'])
})

test('a bot image prints every pool and 6★ row with no tiles and no controls', t => {
  api(t, () => [200, {}])
  const root = mount(t, Panel, { imageMode: true, accountId: '', snap: { payload: { ...summary, pools: [wide, second] }, fetched_at: '2026-09-24T12:00:00+08:00' } })
  assert.deepEqual(details(root).map(node => content(nodes(node, 'h3')[0])), ['特许寻访', '基础寻访'])
  assert.equal(by(root, 'li', 'pull-row').length, 3)
  for (const name of ['提弗洛斯', '余烬', '别礼']) assert.ok(content(root).includes(name), name)
  for (const type of ['button', 'input', 'select', 'details', 'nav']) assert.equal(nodes(root, type).length, 0, type)
  assert.match(content(root), /寻访分析 部分待同步/)
})

test('QQ six-star rows keep exact operator artwork and unknown names', t => {
  api(t, () => { throw Error('image must not fetch') })
  const history = [{ name: '秋栗', pulls: 30, status: 'exact' }, { name: '未收录干员', pulls: null, status: 'unknown' }]
  const root = mount(t, Panel, { imageMode: true, snap: { payload: { ...summary, pools: [{ ...summary.pools[0], history }] } } })
  assert.deepEqual(nodes(root, 'img').map(n => n.props.src), ['https://web.hycdn.cn/endfield/official-v4/_next/static/media/akekuri.3df4a3dc.png'])
  assert.match(content(root), /秋栗 .*30 抽.*未收录干员 .*抽数未知/)
  assert.equal(by(root, 'li', 'pull-row').length, 2)
})

test('6★ rows show weapons by pool kind and keep the name when artwork fails', async t => {
  const weaponPool = { ...summary.pools[0], key: 'weapon:sample', kind: 'weapon', label: '武库申领',
    history: [{ name: '破碎君王', pulls: 12, status: 'exact', obtained_at: 1792000000000 },
      { name: '玉中身', pulls: 0, status: 'lower_bound', obtained_at: 1791900000000 }] }
  const characterPool = { ...summary.pools[0], history: [{ name: '祀', pulls: 18, status: 'lower_bound', obtained_at: 1791800000000 }] }
  const props = { accountId: 'r1', snap: { payload: { ...summary, pools: [weaponPool, characterPool] } } }
  const shared = mount(t, Panel, { ...props, imageMode: true })
  const rows = by(shared, 'li', 'pull-row')
  assert.deepEqual(rows.map(row => nodes(row, 'img')[0]?.props.alt), ['祀', '破碎君王', '玉中身'])
  assert.ok(nodes(rows[1], 'img')[0].props.src.startsWith('https://bbs.hycdn.cn/image/'))
  assert.match(content(rows[2]), /玉中身 .*抽数未知/); assert.doesNotMatch(content(shared), /≥0/)
  assert.match(content(shared), /≥ 表示含未计入的免费抽或记录断档/)
  nodes(rows[1], 'img')[0].props.onError()
  await nextTick()
  assert.equal(nodes(rows[1], 'img').length, 0)
  assert.match(content(rows[1]), /破碎君王/)
})

test('a chosen pool that disappears after a sync falls back to the first pool and the whole ledger', async t => {
  const calls = api(t, () => [200, { total: 0, records: [] }])
  const props = reactive({ accountId: 'r1', snap: { payload: { ...summary, pools: [wide, second] } } })
  const root = mount(t, Panel, props)
  tiles(root)[1].props.onClick(); await flush()
  props.snap = { payload: { ...summary, pools: [wide] } }; await flush()
  assert.match(content(details(root)[0]), /^特许寻访/)
  nodes(root, 'details')[0].props.onToggle({ target: { open: true } }); await flush()
  assert.match(calls.at(-1), /records\?pool_key=&offset=0/)
})

test('every ledger row shows its own operator or weapon artwork, keeping a name tile when none matches', async t => {
  api(t, () => [200, { total: 3, records: [
    { seq_id: '3', pool_key: 'E_CharacterGachaPoolType_Special', kind: 'character', name: '秋栗', rarity: 4, gacha_ts: 1788300000000 },
    { seq_id: '2', pool_key: 'weapon:w1', name: '破碎君王', rarity: 6, gacha_ts: 1788200000000 },
    { seq_id: '1', pool_key: 'E_CharacterGachaPoolType_Special', kind: 'character', name: '未收录干员', rarity: 5, gacha_ts: 1788100000000 }] }])
  const root = mount(t, Panel, { snap, accountId: 'r1' }); await flush()
  nodes(root, 'details')[0].props.onToggle({ target: { open: true } }); await flush()
  const cells = nodes(root, 'td').filter(node => String(node.props.class).includes('name'))
  assert.equal(nodes(cells[0], 'img')[0].props.src, 'https://web.hycdn.cn/endfield/official-v4/_next/static/media/akekuri.3df4a3dc.png')
  assert.ok(nodes(cells[1], 'img')[0].props.src.startsWith('https://bbs.hycdn.cn/image/')) // weapon kind from its pool key
  assert.equal(nodes(cells[2], 'img').length, 0); assert.match(content(cells[2]), /未 未收录干员/)
})

test('pulls of unstated rarity stay as empty track, so the rarity bar has the scale of the legend shares', async t => {
  api(t, () => [200, { total: 0, records: [] }])
  // The fixture pool states 1 six-star and 3 five-star of 30 pulls; its 4★ count is unknown.
  const root = mount(t, Panel, { snap, accountId: 'r1' }); await flush()
  const bar = nodes(root, 'div').find(node => String(node.props.class).includes('stack-bar'))
  assert.deepEqual(nodes(bar, 'i').map(node => [node.props.class ?? '', node.props.style.flex]), [['', 1], ['', 3], ['stack-rest', 26]])
  const full = { ...summary.pools[0], four_star: 26, unknown_rarity: 0 }
  const whole = mount(t, Panel, { snap: { payload: { ...summary, pools: [full] } }, accountId: 'r1' }); await flush()
  const filled = nodes(whole, 'div').find(node => String(node.props.class).includes('stack-bar'))
  assert.deepEqual(nodes(filled, 'i').map(node => node.props.style.flex), [1, 3, 26])
})

test('pools the last sync could not read are named with their reason, without hiding what did sync', t => {
  api(t, () => [200, {}])
  const errors = [{ key: 'weapon:w1', label: '熔铸申领', message: '接口错误 code=1001：参数错误' }, { key: 'weapon:*', label: '武器池列表', message: '' }]
  const root = mount(t, Panel, { accountId: 'r1', snap: { payload: { ...summary, errors } } })
  assert.match(content(root), /本次未能读取： 熔铸申领 （接口错误 code=1001：参数错误） 、 武器池列表 （原因未知） 。其他卡池已正常同步，下次刷新会重试。/)
  assert.match(content(root), /特许寻访/)
  assert.doesNotMatch(content(mount(t, Panel, { accountId: 'r1', snap })), /本次未能读取/)
})

test('a zero lower-bound pity reads as unknown in the image instead of ≥0', t => {
  const pool = { ...summary.pools[0], since_last_six: { count: 0, status: 'lower_bound' } }
  const root = mount(t, Panel, { imageMode: true, snap: { payload: { ...summary, pools: [pool] } } })
  assert.match(content(root), /已垫 未知 距上次 6★/)
  assert.doesNotMatch(content(root), /≥0/)
})
