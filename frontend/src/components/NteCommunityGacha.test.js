import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'

const Panel = await loadVue(new URL('./NteCommunityGacha.vue', import.meta.url))
const snapshot = pools => ({ payload: { schema_version: 1, pools }, fetched_at: '2026-09-16T12:00:00Z' })
const pools = [
  { name: '限定卡池', total_draws: 100, s_count: 2, average: 50, details: [
    { item_id: 'a', name: '角色甲', pity: 80, obtained_at: '2026-09-02T00:00:00Z' },
    { item_id: 'b', name: '角色乙', pity: 20, obtained_at: '2026-09-01T00:00:00Z' },
  ] },
  { name: '常驻卡池', total_draws: 0, s_count: 0, average: null, details: [] },
  { name: '弧盘池', total_draws: null, s_count: null, average: null, details: [
    { item_id: 'c', name: '未匹配弧盘', pity: null, obtained_at: null },
  ] },
]

test('image groups every current pool using the shared history rows, including unknown and zero', t => {
  const root=mount(t,Panel,{snap:snapshot(pools),imageMode:true})
  const histories=nodes(root,'section').filter(n=>String(n.props.class).includes('history-panel'))
  assert.equal(histories.length,3)
  assert.match(content(histories[0]),/限定卡池.*角色甲.*80 抽.*角色乙.*20 抽/)
  assert.match(content(histories[1]),/常驻卡池.*暂无已出 S 明细/)
  assert.match(content(histories[2]),/弧盘池.*未匹配弧盘.*本次抽数未提供/)
  assert.match(content(root),/0 抽/)
  assert.equal(nodes(root,'li').length,3)
  assert.equal(nodes(root,'nav').length,0)
})
test('community view switches pool history without inventing pity, coverage or luck', async t => {
  const root = mount(t, Panel, { snap: snapshot(pools) })
  assert.match(content(root), /100 抽/)
  assert.match(content(root), /角色甲/)
  assert.match(content(root), /80 抽/)
  assert.doesNotMatch(content(root), /未匹配弧盘|十连二金|必出/)
  for (const row of nodes(root, 'li')) assert.doesNotMatch(content(row), /超欧|超非/)
  const buttons = nodes(root, 'button')
  buttons.find(n => content(n) === '常驻卡池').props.onClick(); await nextTick()
  assert.match(content(root), /暂无已出 S 明细/)
  assert.doesNotMatch(content(root), /角色甲/)
  buttons.find(n => content(n) === '弧盘池').props.onClick(); await nextTick()
  assert.match(content(root), /未匹配弧盘/)
  assert.match(content(root), /本次抽数未提供/)
  assert.doesNotMatch(content(root), /NaN|Infinity/)
})
test('avatars use item identity and gracefully fall back after an image fails', async t => {
  const root = mount(t, Panel, { snap: snapshot(pools), roles: [
    { id: 'a', name: '角色甲', icon_url: 'https://example.com/a.png' },
    { id: 'b', name: '角色乙', icon_url: 'javascript:alert(1)' },
  ] })
  const pictures = nodes(root, 'img')
  assert.equal(pictures.length, 1)
  assert.equal(pictures[0].props.alt, '角色甲')
  pictures[0].props.onError(); await nextTick()
  assert.equal(nodes(root, 'img').length, 0)
  assert.match(content(root), /角色甲/)
})
test('snapshot changes reset unavailable selection and legacy or missing data stays unknown', async t => {
  const props = reactive({ snap: snapshot(pools) }), root = mount(t, Panel, props)
  nodes(root, 'button').find(n => content(n) === '弧盘池').props.onClick(); await nextTick()
  props.snap = snapshot([pools[0]]); await nextTick()
  assert.match(content(root), /角色甲/)
  props.snap = { payload: { pools }, stale: true }; await nextTick()
  assert.match(content(root), /刷新/)
  assert.doesNotMatch(content(root), /100 抽/)
  props.snap = null; await nextTick()
  assert.match(content(root), /暂无抽卡数据.*刷新/)
})

test('official rating codes drive labels and colors independently of pull counts', t => {
  const data = snapshot([{ name: '限定卡池', guarantee: 90, details: [
    ...[0, 1, 2, 3, 4, 99].map(code => ({ item_id: `r${code}`, name: `角色${code}`, pity: 80, lucky_type: code })),
  ] }])
  data.payload.luck_title = '一般过路人'; data.payload.luck_type = 8
  const root = mount(t, Panel, { snap: data })
  assert.match(content(root), /一般过路人/)
  const rows = nodes(root, 'li')
  for (const [i, label] of [[1, '超欧'], [2, '欧'], [3, '非'], [4, '超非']]) assert.match(content(rows[i]), new RegExp(label))
  assert.doesNotMatch(content(rows[0]), /超非|超欧/)
  assert.doesNotMatch(content(rows[5]), /超非|超欧/)
  const bars = nodes(root, 'div').filter(n => String(n.props.class).includes('pull-bar'))
  assert.match(bars[1].props.class, /short/)
  assert.match(bars[4].props.class, /long/)
  assert.match(bars[5].props.class, /unknown/)
  assert.equal(bars[0].props.style.width, `${80 / 90 * 100}%`)
})

test('community artwork uses known names and catalog fallbacks before leaving a placeholder', async t => {
 const root=mount(t,Panel,{snap:snapshot([{name:'记录',details:[
  {item_id:'fork_yuren',name:'勿忘伞'},
  {name:'「光波眩晕」'},
  {item_id:'1057',name:'明音'},
  {name:'未收录物品'},
 ]}]),roles:[{id:'1057',icon_url:'https://example.com/missing.png'}]})
 assert.deepEqual(nodes(root,'img').map(n=>n.props.src),[
  'https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/character/fork/fork_yuren.png',
  'https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/character/fork/fork_bopu.png',
  'https://example.com/missing.png',
 ])
 nodes(root,'img')[2].props.onError(); await nextTick()
 assert.equal(nodes(root,'img')[2].props.src,'https://webstatic.tajiduo.com/bbs/pic/player_057_256.png')
 assert.match(content(root),/未收录物品/)
})


test('pull dates share strict calendar parsing while preserving the missing-time label', t => {
  const root = mount(t, Panel, { snap: snapshot([{ name: '记录', details: [
    { name: '非法日期', obtained_at: '2026-02-30T10:00:00+08:00' },
    { name: '有效日期', obtained_at: '2026-09-20T21:14:00+0800' },
    { name: '缺失日期', obtained_at: null },
    { name: '非字符串', obtained_at: 1789910040000 },
  ] }]) })
  assert.deepEqual(nodes(root, 'time').filter(node => node.props.class === 'pull-time').map(content), [
    '时间未提供', '2026-09-20 21:14', '时间未提供', '时间未提供',
  ])
})
