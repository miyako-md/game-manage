import test from 'node:test'
import assert from 'node:assert/strict'
import { reactive, nextTick } from 'vue'
import { loadVue, mount, content, nodes, choose } from '../test-utils/vue.js'
const Panel = await loadVue(new URL('./NteRolesPanel.vue', import.meta.url))
const entries = Array.from({ length: 5 }, (_, i) => ({ id: String(i + 1), name: `角色${i + 1}`, quality: i ? 'A' : 'S', element: i ? '光' : '灵', level: i, awaken_level: 0, mix_level: 1, affinity_exp: 650, weapon: { name: '弧光', level: 30, quality: 'A', mix_level: 2 }, properties: [{ name: '攻击', value: '320' }], skills: [{ name: '战技一', level: 5 }], city_skills: [{ name: '城区一', level: 2 }] }))
const snap = (items = entries) => ({ payload: { schema_version: 1, entries: items }, stale: true, fetched_at: '2026-09-16T10:00:00+08:00' })
const button = (root, label) => nodes(root, 'button').find(n => n.props['aria-label'] === label)
const cards = root => nodes(root, 'li').filter(n => n.props.class?.includes('role-card'))

test('website cards show quality as the shared rarity tag on the picture; images keep the inline rank', t => {
  const tags = root => nodes(root, 'span').filter(n => n.props.class === 'role-rarity')
  const ranks = root => nodes(root, 'span').filter(n => String(n.props.class).split(' ').includes('rank'))
  const web = mount(t, Panel, { snap: snap([...entries, { ...entries[1], id: '9', name: '未定品质', quality: null }]), accountId: 'a' })
  assert.equal(tags(web).length, 6)
  assert.ok(tags(web).every(n => n.parent.props.class === 'role-art'))
  assert.deepEqual(tags(web).filter(n => n.props['data-tier'] === 'top').map(content), ['S'])
  assert.ok(tags(web).some(n => content(n) === '未提供' && n.props['aria-label'] === '品质 未提供'))
  assert.equal(ranks(web).length, 0)
  assert.equal(nodes(web, 'section')[0].props['data-skin'], 'nte')
  const image = mount(t, Panel, { snap: snap(), imageMode: true })
  assert.equal(tags(image).length, 0)
  assert.equal(ranks(image).length, entries.length)
  assert.equal(nodes(image, 'section')[0].props['data-skin'], undefined)
})

test('wide single-role detail requires explicit mode and never follows a one-result search', async t => {
  const root=mount(t,Panel,{snap:snap(),accountId:'a'})
  nodes(root,'input').find(n=>n.props['aria-label']==='搜索角色').props.onInput({target:{value:'角色1'}})
  await nextTick()
  assert.equal(cards(root).length,1)
  assert.doesNotMatch(nodes(root,'section')[0].props.class,/role-detail-view/)
  const selected=mount(t,Panel,{snap:snap([entries[0]]),detailMode:true})
  assert.match(nodes(selected,'section')[0].props.class,/role-detail-view/)
  assert.equal(nodes(selected,'details')[0].props.open,true)
  assert.match(content(selected),/攻击.*320.*战技一.*Lv5/)
  // The image of a selected role is the role sheet: no disclosure, the same facts.
  const image=mount(t,Panel,{snap:snap([entries[0]]),detailMode:true,imageMode:true})
  assert.match(nodes(image,'section')[0].props.class,/role-detail-view/)
  assert.equal(nodes(image,'details').length,0)
  assert.match(content(image),/攻击.*320.*Lv5 战技一/)
})

test('image overview keeps the complete roster without mounting every detailed skill and equipment section', t => {
  const root = mount(t, Panel, { snap: snap(), imageMode: true, detailMode: false })
  assert.equal(cards(root).length, entries.length)
  assert.equal(nodes(root, 'details').length, 0)
  assert.match(content(root), /异环 角色/)
  assert.doesNotMatch(content(root), /战技一|城区一/)
})

test('selected image role draws the role sheet and preserves unknown versus zero', t => {
  const root = mount(t, Panel, { snap: snap([{ ...entries[0], awaken_level: null }]), imageMode: true, detailMode: true })
  assert.equal(nodes(root, 'div').filter(n => String(n.props.class).includes('nte-role-sheet')).length, 1)
  assert.equal(cards(root).length, 0)
  assert.match(content(root), /Lv5 战技一/)
  assert.match(content(root), /觉醒 未提供 混频 1/)
  assert.match(content(root), /角色1 Lv0/)
  assert.doesNotMatch(content(root), /城区一|角色总数/, 'city skills and roster counts stay out of a single role sheet')
})

test('catalog icons accompany remote role filters and full collapsible equipment details', async t => {
  const root = mount(t, Panel, { accountId: 'a', snap: snap([
    { ...entries[0], id: '1010', name: '娜娜莉', level: 70, weapon: { name: '预备备', level: 60 }, skills: [{ name: '普通攻击', level: 5 }] },
    { ...entries[1], name: '低等级角色', level: 1 },
  ]) })
  const role = cards(root)[0]
  assert.match(content(role), /娜娜莉/)
  assert.ok(nodes(role,'img').length >= 1)
  button(root,'查看娜娜莉面板').props.onClick();await nextTick()
  assert.match(content(nodes(root,'dialog')[0]),/弧盘.*预备备.*战技.*普通攻击.*Lv5/)
  choose(root, '排序方向', 'asc'); await nextTick()
  assert.match(content(cards(root)[0]), /低等级角色/)
})
test('search and filter inputs update visible cards while retaining full role details', async t => {
  const root = mount(t, Panel, { snap: snap(), accountId: 'a' })
  assert.equal(cards(root).length, 5)
  for (const expected of ['角色总数', '数据可能过期', '更新于']) assert.ok(content(root).includes(expected))
  nodes(root, 'input').find(n => n.props['aria-label'] === '搜索角色').props.onInput({ target: { value: '角色1' } })
  await nextTick(); assert.equal(cards(root).length, 1)
  assert.ok(content(cards(root)[0]).includes('角色1'))
  choose(root, '品质筛选', 'A')
  await nextTick(); assert.equal(cards(root).length, 0); assert.match(content(root), /没有符合/)
})
test('comparison keeps selections across filters, enforces four, removes selections, and needs two', async t => {
  const root = mount(t, Panel, { snap: snap(), accountId: '' })
  button(root, '对比角色1').props.onClick(); await nextTick()
  assert.match(content(root), /至少选择 2/); assert.equal(nodes(root, 'table').length, 0)
  for (const id of [2, 3, 4]) { button(root, `对比角色${id}`).props.onClick(); await nextTick() }
  assert.equal(button(root, '对比角色5').props.disabled, true)
  button(root, '对比角色5').props.onClick(); await nextTick()
  assert.equal(nodes(root, 'table').length, 1)
  nodes(root, 'input')[0].props.onInput({ target: { value: '角色5' } }); await nextTick()
  assert.match(content(nodes(root, 'table')[0]), /角色1.*角色2.*角色3.*角色4/)
  button(root, '移除对比角色2').props.onClick(); await nextTick()
  assert.equal(button(root, '对比角色5').props.disabled, false)
  assert.doesNotMatch(content(nodes(root, 'table')[0]), /角色2/)
})
test('element, sort direction and favorites filter control the card list', async t => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => '["1"]', setItem() {} } })
  t.after(() => previous ? Object.defineProperty(globalThis, 'localStorage', previous) : delete globalThis.localStorage)
  const root = mount(t, Panel, { snap: snap(), accountId: 'a' })
  assert.match(content(cards(root)[0]), /角色5/)
  choose(root, '排序方向', 'asc'); await nextTick()
  assert.match(content(cards(root)[0]), /角色1/)
  choose(root, '元素筛选', '灵'); await nextTick()
  assert.equal(cards(root).length, 1)
  choose(root, '元素筛选', '')
  nodes(root, 'input').find(n => n.props['aria-label'] === '仅收藏').props.onChange({ target: { checked: true } }); await nextTick()
  assert.equal(cards(root).length, 1); assert.match(content(cards(root)[0]), /角色1/)
  button(root, '取消收藏角色1').props.onClick(); await nextTick(); assert.equal(cards(root).length, 0)
})
test('roles default to newest first (role id) on the website and in images; other sorts stay available', async t => {
  const list = [{ id: '1003', name: '早雾', level: 90 }, { id: null, name: '无编号', level: 99 }, { id: '1076', name: '真红', level: 10 }, { id: '1057', name: '明音', level: 50 }]
  const names = root => cards(root).map(card => content(card).match(/早雾|无编号|真红|明音/)[0])
  for (const imageMode of [false, true]) assert.deepEqual(names(mount(t, Panel, { snap: snap(list), accountId: 'a', imageMode })), ['真红', '明音', '早雾', '无编号'])
  const root = mount(t, Panel, { snap: snap(list), accountId: 'a' })
  choose(root, '角色排序', 'level'); await nextTick()
  assert.deepEqual(names(root), ['无编号', '早雾', '明音', '真红'])
})
test('favorites survive remount, isolate accounts, and report unavailable storage without crashing', async t => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage'), map = new Map()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: k => map.get(k) ?? null, setItem: (k, v) => map.set(k, v) } })
  t.after(() => previous ? Object.defineProperty(globalThis, 'localStorage', previous) : delete globalThis.localStorage)
  const props = reactive({ snap: snap(), accountId: 'a' }), root = mount(t, Panel, props)
  button(root, '收藏角色1').props.onClick(); await nextTick()
  assert.ok(button(root, '取消收藏角色1'))
  const second = mount(t, Panel, { snap: snap(), accountId: 'a' })
  assert.ok(button(second, '取消收藏角色1'))
  props.accountId = 'b'; await nextTick(); assert.ok(button(root, '收藏角色1'))
  props.accountId = ''; await nextTick(); assert.equal(button(root, '收藏角色1').props.disabled, true)
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw Error('denied') } })
  props.accountId = 'c'; await nextTick(); assert.match(content(root), /收藏.*(读取|存储|保存)/)
  button(root, '收藏角色1').props.onClick(); await nextTick(); assert.match(content(root), /收藏.*(存储|保存)/)
})
test('legacy, empty, unsafe and failed portraits remain supported', async t => {
  assert.match(content(mount(t, Panel, { snap: null })), /暂无数据/)
  assert.match(content(mount(t, Panel, { snap: { payload: { raw: 1 } } })), /格式已更新/)
  assert.match(content(mount(t, Panel, { snap: snap([]) })), /暂无数据/)
  const root = mount(t, Panel, { snap: snap([{ name: '甲', icon_url: 'javascript:alert(1)' }, { name: '乙', icon_url: 'https://cdn.example.com/a.png' }]) })
  assert.equal(nodes(root, 'img').length, 1)
  const image = nodes(root, 'img')[0]; image.props.onError({ currentTarget: { src: image.props.src } }); await nextTick()
  assert.equal(nodes(root, 'img').length, 0)
})
test('search waits for IME composition to finish before filtering', async t => {
  const root = mount(t, Panel, { snap: snap(), accountId: 'a' })
  const input = nodes(root, 'input').find(n => n.props['aria-label'] === '搜索角色')
  input.props.onInput({ isComposing: true, target: { value: 'jiaose' } }); await nextTick()
  assert.equal(cards(root).length, 5, 'pinyin letters while composing must not filter the list')
  input.props.onCompositionend({ target: { value: '角色2' } }); await nextTick()
  assert.equal(cards(root).length, 1)
})


test('screen roster mounts equipment only after opening a single role',async t=>{
 const root=mount(t,Panel,{snap:snap(),accountId:'a'})
 assert.doesNotMatch(content(root),/战技一/)
 const open=button(root,'查看角色1面板')
 assert.ok(open)
 open.props.onClick();await nextTick()
 assert.equal(nodes(root,'dialog').length,1)
 assert.match(content(nodes(root,'dialog')[0]),/战技一.*Lv5/)
 nodes(root,'button').find(n=>content(n)==='关闭详情').props.onClick();await nextTick()
 assert.equal(nodes(root,'dialog').length,0)
})


test('an open role detail follows new same-scope snapshots and closes when removed',async t=>{
 const props=reactive({snap:snap(),accountId:'a'})
 const root=mount(t,Panel,props)
 button(root,'查看角色1面板').props.onClick();await nextTick()
 props.snap=snap([{...entries[0],level:90,properties:[{name:'攻击',value:'9999'}]}]);await nextTick()
 assert.match(content(nodes(root,'dialog')[0]),/Lv90.*攻击.*9999/)
 props.snap=snap([]);await nextTick();assert.equal(nodes(root,'dialog').length,0)
})


test('first-level roles retain known awakening and mixing and show level distribution',t=>{
 const root=mount(t,Panel,{snap:snap()})
 assert.ok(nodes(root,'ol').some(n=>n.props['aria-label']==='角色等级分布'))
 assert.match(content(cards(root)[0]),/觉醒 0.*混频 1/)
 assert.doesNotMatch(content(cards(root)[0]),/战技一|城区一/)
})
