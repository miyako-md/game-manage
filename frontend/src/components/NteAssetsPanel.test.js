import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, content, nodes, choose } from '../test-utils/vue.js'

const NteAssetsPanel = await loadVue(new URL('./NteAssetsPanel.vue', import.meta.url))
const snap = (payload) => ({ payload: { schema_version: 1, ...payload }, fetched_at: '2026-09-14T10:00:00+08:00', stale: false })
const card = (t, capability, payload) => mount(t, NteAssetsPanel, { capability, snap: snap(payload) })

test('houses show unknown counts, residents and distinct furniture ownership in expandable details', (t) => {
  const root = mount(t, NteAssetsPanel, { capability: 'realestate', roles: [{ id: '1019', name: '薄荷', icon_url: 'https://example.com/role.png' }],
    snap: snap({ owned_count: 0, total: null, entries: [{ id: 'h1', name: '海景房', owned: false,
      resident_ids: ['1019', '1020'], furniture: [{ id: 'f1', name: '椅子', owned: true }, { id: 'f2', name: '桌子', owned: null }] }] }) })
  assert.match(content(root), /拥有 0 \/ 未知/)
  assert.match(content(root), /海景房.*未拥有/)
  const detail = nodes(root, 'details')[0]
  assert.ok(detail)
  assert.match(content(nodes(detail, 'summary')[0]), /海景房.*详情/)
  assert.match(content(detail), /薄荷.*角色 1020/)
  assert.match(content(detail), /椅子.*已拥有.*桌子.*未知/)
  assert.equal(nodes(root, 'img')[0].props.src, 'https://example.com/role.png')
})

test('asset search combines with owned state without counting unknown as unowned', async (t) => {
  const root = card(t, 'realestate', { entries: [
    { id: '1', name: '海景公寓', owned: true }, { id: '2', name: '海景别墅', owned: false }, { id: '3', name: '山间小屋', owned: null },
  ] })
  nodes(root, 'input')[0].props.onInput({ target: { value: '海景' } })
  await nextTick()
  assert.equal(nodes(root, 'details').length, 2)
  choose(root, '拥有状态', 'unowned')
  await nextTick()
  assert.equal(nodes(root, 'details').length, 1)
  assert.match(content(nodes(root, 'details')[0]), /海景别墅/)
  nodes(root, 'input')[0].props.onInput({ target: { value: '' } })
  choose(root, '拥有状态', 'unknown')
  await nextTick()
  assert.match(content(nodes(root, 'details')[0]), /山间小屋/)
})

test('vehicle details display source values, missing maxima and coating type without invented units', (t) => {
  const root = card(t, 'vehicles', { show_name: '街道之星', entries: [{ id: 'v1', name: '街道之星', owned: true,
    base: [{ name: '最高时速', value: '146' }], advanced: [{ name: '加速', value: '0', maximum: null }],
    models: [{ id: 'model1', type: 'paint-red' }, { id: 'v008_tyre_03', type: 'evmt_tyre' }] }] })
  assert.match(content(root), /展示载具：街道之星/)
  assert.match(content(root), /最高时速.*146.*加速.*0 \/ 未知/)
  // Internal slot keys and model IDs mean nothing to players: a Chinese type only.
  assert.match(content(root), /装饰 \/ 涂装 装饰 轮胎/)
  assert.doesNotMatch(content(root), /paint-red|model1|evmt_tyre|v008_tyre_03|ID /)
  assert.doesNotMatch(content(root), /146%|146 km|undefined|null/)
})

test('official recommendations display safe linked images and descriptions as text', (t) => {
  const root = card(t, 'teams', { entries: [{ id: 't1', name: '官方组合', description: '<img onerror="bad">配队描述',
    icon_url: 'javascript:bad', image_urls: ['https://example.com/team.png', 'data:image/png,bad', 'https://user:pass@example.com/x'] }] })
  assert.match(content(root), /来源：塔吉多官方配队推荐/)
  assert.match(content(root), /<img onerror="bad">配队描述/)
  assert.equal(nodes(root, 'ul').filter(n => n.props.role === 'listbox').length, 0)
  const images = nodes(root, 'img')
  assert.equal(images.length, 1)
  assert.equal(images[0].props.src, 'https://example.com/team.png')
  const links = nodes(root, 'a')
  assert.equal(links.length, 1)
  assert.match(links[0].props.rel, /noopener/)
  assert.equal(nodes(root, 'p').some(n => n.props.innerHTML), false)
})

test('recommendation search includes its plain description', async (t) => {
  const root = card(t, 'teams', { entries: [{ id: '1', name: '队伍一', description: '灵属性组合' }, { id: '2', name: '队伍二', description: '魂属性组合' }] })
  nodes(root, 'input')[0].props.onInput({ target: { value: '灵属性' } })
  await nextTick()
  assert.equal(nodes(root, 'details').length, 1)
  assert.match(content(nodes(root, 'details')[0]), /队伍一/)
})

test('snapshots distinguish absent, legacy, stale and valid empty data', (t) => {
  assert.match(content(mount(t, NteAssetsPanel, { capability: 'teams', snap: null })), /暂无数据/)
  const legacy = mount(t, NteAssetsPanel, { capability: 'teams', snap: { payload: { entries: [{ id: 'x', name: '旧数据' }] } } })
  assert.match(content(legacy), /刷新/)
  assert.doesNotMatch(content(legacy), /旧数据/)
  assert.match(content(card(t, 'teams', { entries: [] })), /暂无官方配队推荐/)
  const stale = mount(t, NteAssetsPanel, { capability: 'vehicles', snap: { ...snap({ entries: [] }), stale: true } })
  assert.ok(nodes(stale, 'span').some(node => String(node.props.class).includes('badge-stale') && content(node) === '缓存已过期'))
})

test('house search resolves resident names and furniture names', async (t) => {
  const root = mount(t, NteAssetsPanel, { capability: 'realestate', roles: [{ id: '1019', name: '薄荷' }],
    snap: snap({ entries: [{ id: '1', name: '海景房', resident_ids: ['1019'], furniture: [{ id: 'f1', name: '古董椅' }] },
      { id: '2', name: '城郊小屋', resident_ids: [] }] }) })
  for (const query of ['薄荷', '古董椅']) {
    nodes(root, 'input')[0].props.onInput({ target: { value: query } })
    await nextTick()
    assert.equal(nodes(root, 'details').length, 1)
    assert.match(content(nodes(root, 'details')[0]), /海景房/)
  }
})

test('broken recommendation images retain an accessible link and descriptive content', async (t) => {
  const root = card(t, 'teams', { entries: [{ id: '1', name: '队伍一', description: '推荐说明', image_urls: ['https://example.com/team.png'] }] })
  nodes(root, 'img')[0].props.onError({ currentTarget: { src: 'https://example.com/team.png' } })
  await nextTick()
  assert.equal(nodes(root, 'img').length, 0)
  assert.match(content(root), /推荐说明.*图片暂时无法加载/)
  assert.equal(nodes(root, 'a')[0].props.href, 'https://example.com/team.png')
})


test('official asset pictures fail back without losing ownership or fields',async t=>{
 for(const [kind,id] of [['realestate','bigword_l_1'],['vehicles','vehicle008']]){
  const root=card(t,kind,{entries:[{id,name:'有来源的资产',owned:null,base:[{name:'车辆耐久',value:'-1'}]}]})
  const pic=nodes(root,'img')[0];assert.ok(pic.props.src.startsWith('https://webstatic.tajiduo.com/'))
  pic.props.onError({currentTarget:{src:pic.props.src}});await nextTick()
  assert.equal(nodes(root,'img').length,0);assert.match(content(root),/有来源的资产.*拥有状态未知/)
  if(kind==='vehicles')assert.match(content(root),/来源未说明/)
 }
})

test('the team image lists each name once while the website keeps every official entry', (t) => {
  const entries = [{ id: '1', name: '主角·零', description: '男' }, { id: '2', name: '主角·零', description: '女' }, { id: '3', name: '合成配队' }]
  assert.equal(nodes(card(t, 'teams', { entries }), 'details').length, 3)
  const image = mount(t, NteAssetsPanel, { capability: 'teams', imageMode: true, snap: snap({ entries }) })
  assert.deepEqual(nodes(image, 'details').map(n => content(nodes(n, 'strong')[0])), ['主角·零', '合成配队'])
})

test('the team image filters by the roster the server attaches, ahead of the roles prop', async (t) => {
  const { defineComponent, h, provide } = await import('vue')
  const entries = [{ id: '1', name: '娜娜莉配队' }, { id: '2', name: '安魂曲配队' }, { id: '3', name: '合成配队' }]
  const wrapped = (roles) => defineComponent({ setup() {
    provide('renderRoleCatalog', { nte: [{ id: '1', name: '娜娜莉' }, { id: '2', name: '安魂曲' }] })
    return () => h(NteAssetsPanel, { capability: 'teams', imageMode: true, roles, snap: snap({ entries, owned_role_names: ['娜娜莉'] }) })
  } })
  const names = root => nodes(root, 'details').map(n => content(nodes(n, 'strong')[0]))
  // 安魂曲 is a known but unowned role; a name with no known role is kept.
  assert.deepEqual(names(mount(t, wrapped([{ name: '安魂曲' }]), {})), ['娜娜莉配队', '合成配队'])
})
