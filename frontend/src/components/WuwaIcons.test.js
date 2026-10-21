import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
import { characterIcon } from '../wuwa-icons.js'

test('a missing role picture retries the same character catalog before showing its initial', async t => {
  const Roles = await loadVue(new URL('./WuwaRoles.vue', import.meta.url))
  const root = mount(t, Roles, { snap: { payload: [{ role_id: 1102, name: '散华', level: 60, icon_url: 'https://web-static.kurobbs.com/missing.png' }] } })
  const picture = () => nodes(root, 'img').find(node => node.props.alt === '散华')
  assert.equal(picture().props.src, 'https://web-static.kurobbs.com/missing.png')
  picture().props.onError(); await nextTick()
  assert.equal(picture().props.src, characterIcon(1102))
  picture().props.onError(); await nextTick()
  assert.equal(picture(), undefined)
  assert.match(content(root), /散华/)
})

test('image role preserves nested source attributes while raw keys and effect text stay absent', async t => {
  const Detail=await loadVue(new URL('./WuwaRoleDetail.vue',import.meta.url))
  const root=mount(t,Detail,{imageMode:true,data:{role:{role_id:'synthetic-character',role_name:'合成角色',level:0,
    role_attribute_list:[{attribute_name:'攻击',attribute_value:'1234'},{attribute_name:'防御',attribute_value:null}]},
    skill_list:[{level:0,skill:{name:'战技',description:'完整技能条件'}}],
    weapon_data:{level:0,weapon:{weapon_name:'合成武器',effect_description:'完整武器效果'}}}})
  assert.match(content(root),/完整属性.*攻击.*1234.*防御.*未知/)
  assert.match(content(root),/合成武器.*战技.*Lv.0/)
  assert.doesNotMatch(content(root),/完整技能条件|完整武器效果|来源补充字段|role_id|role_attribute_list|attribute_name|synthetic-character/)
})

test('R1: the image detail leads with a portrait card and fits skills and chains in one row; the website keeps its basics', async t => {
  const Detail = await loadVue(new URL('./WuwaRoleDetail.vue', import.meta.url))
  const data = {
    role: { role_name: '角色甲', level: 0, role_icon_url: 'https://web-static.kurobbs.com/role.png' },
    role_skin: { skin_name: '外观甲', skin_icon: 'https://web-static.kurobbs.com/skin.png' },
    skill_list: Array.from({ length: 9 }, (_, i) => ({ level: i, skill: { name: `技能${i}` } })),
    chain_list: Array.from({ length: 6 }, (_, i) => ({ order: i + 1, name: `链${i}`, unlocked: i < 2 })),
  }
  const byClass = (root, name) => nodes(root, 'div').concat(nodes(root, 'section')).filter(n => String(n.props.class ?? '').split(/\s+/).includes(name))
  const image = mount(t, Detail, { imageMode: true, data })
  const [figure] = nodes(image, 'figure')
  assert.equal(figure.props.class, 'wuwa-portrait')
  assert.deepEqual(nodes(figure, 'img').map(n => n.props.src), ['https://web-static.kurobbs.com/skin.png'])
  assert.match(content(figure), /角色甲 Lv.0/)
  assert.deepEqual(nodes(image, 'img').map(n => n.props.src).filter(src => /role|skin/.test(src)), ['https://web-static.kurobbs.com/skin.png'], 'no second copy of the picture')
  assert.equal(byClass(image, 'wuwa-skills')[0].props.style['--row-count'], 7)
  assert.equal(byClass(image, 'wuwa-chains')[0].props.style['--row-count'], 6)
  for (const name of ['basics', 'attrs', 'weapon', 'skills', 'chains', 'echoes']) assert.equal(byClass(image, `wuwa-detail-${name}`).length, 1, name)
  // The top-level level is on the portrait card; the trailing field list must not repeat it in images.
  const leveled = { ...data, level: 90 }
  assert.doesNotMatch(content(mount(t, Detail, { imageMode: true, data: leveled })).replace(/Lv\.\d+/g, ''), /等级\s*90/)
  assert.match(content(mount(t, Detail, { data: leveled })), /等级\s*90/)
  const noSkin = mount(t, Detail, { imageMode: true, data: { ...data, role_skin: {} } })
  assert.equal(nodes(nodes(noSkin, 'figure')[0], 'img')[0].props.src, 'https://web-static.kurobbs.com/role.png')
  const unknown = mount(t, Detail, { imageMode: true, data: { role: { role_name: '角色乙' } } })
  assert.match(content(nodes(unknown, 'figure')[0]), /^角 角色乙 Lv\.未知$/, 'initial stands in for a missing picture; unknown level stays unknown')
  const web = mount(t, Detail, { data })
  assert.equal(nodes(web, 'figure').length, 0)
  assert.ok(nodes(web, 'img').some(n => n.props.class === 'wuwa-skin'))
  assert.equal(byClass(web, 'wuwa-skills')[0].props.style, undefined)
})

test('real panel displays provided skill and chain icons and tolerates empty echo slots', async t => {
  const Detail = await loadVue(new URL('./WuwaRoleDetail.vue', import.meta.url))
  const root = mount(t, Detail, { data: {
    role: { role_name: '角色甲', role_icon_url: 'https://web-static.kurobbs.com/role.png' },
    skill_list: [{ level: 0, skill: { name: '技能甲', type: '共鸣回路', description: '完整技能条件', icon_url: 'https://web-static.kurobbs.com/skill.png' } }],
    chain_list: [{ name: '共鸣链甲', order: 1, unlocked: false, icon_url: 'https://web-static.kurobbs.com/chain.png' }],
    phantom_data: { equip_phantom_list: [null] },
  } })
  const urls = nodes(root, 'img').map(n=>n.props.src)
  assert.ok(urls.includes('https://web-static.kurobbs.com/skill.png'))
  assert.ok(urls.includes('https://web-static.kurobbs.com/chain.png'))
  assert.match(content(root), /技能甲.*共鸣回路.*Lv.0/)
  assert.doesNotMatch(content(root), /完整技能条件/)
  assert.match(content(root), /暂无装备声骸数据/)
})

test('broken icons fall back to a name marker and retry when the source changes', async t => {
  const Icon = await loadVue(new URL('./WuwaIcon.vue', import.meta.url))
  const props = reactive({ src: 'https://web-static.kurobbs.com/a.png', name: '武器甲' })
  const root = mount(t, Icon, props)
  nodes(root, 'img')[0].props.onError()
  await nextTick()
  assert.equal(nodes(root, 'img').length, 0)
  assert.match(content(root), /武/)
  props.src = 'https://web-static.kurobbs.com/b.png'
  await nextTick()
  assert.equal(nodes(root, 'img').length, 1)
})

// M8 (R1 slot): each scored echo shows its default score and grade; an unscorable echo shows none.
const scoredDetail = () => ({
  role: { role_id: 1205, role_name: '角色甲' },
  phantom_data: { cost: 11, equip_phantom_list: [
    { cost: 4, phantom_prop: { name: '声骸甲' } }, null, { cost: 3, phantom_prop: { name: '声骸乙' } }, { phantom_prop: { name: '声骸丙' } },
  ] },
})
const defaultAssessment = attribution => ({ status: 'unscorable', partial: true, partial_known_total: '70.10', origin: 'builtin_default', unofficial: true, attribution, max_value: 250, item_results: [
  { item_id: 'echo:0:unknown', status: 'scored', value: '38.52', grade: 'ss', max_value: 50, cost: 4 },
  { item_id: 'echo:2:unknown', status: 'scored', value: '31.58', grade: 'a', max_value: 50, cost: 3 },
  { item_id: 'echo:3:unknown', status: 'unscorable', value: null, grade: null, max_value: null, cost: null },
] })
const badgeTexts = root => nodes(root, 'p').filter(n => n.props.class === 'wuwa-echo-score').map(content)

test('image echoes carry their score and grade with the unofficial attribution; an unscorable echo has no badge', async t => {
  const Detail = await loadVue(new URL('./WuwaRoleDetail.vue', import.meta.url))
  const root = mount(t, Detail, { imageMode: true, data: { ...scoredDetail(), assessment: defaultAssessment('gpl_snapshot') } })
  assert.deepEqual(badgeTexts(root), ['38.52 SS', '31.58 A'])
  const tiles = nodes(root, 'article').filter(n => /声骸/.test(content(n)))
  assert.deepEqual(tiles.map(n => badgeTexts(n).length), [1, 1, 0])
  assert.match(content(root), /装备声骸 总 COST 11 非官方 · 权重改编自 WutheringWavesUID（GPL-3.0）/)
  assert.doesNotMatch(content(root), /默认评分/, 'the block itself stays hidden until the total is scored')
  assert.match(content(mount(t, Detail, { imageMode: true, data: { ...scoredDetail(), assessment: defaultAssessment('self_made') } })), /非官方 · 自制权重/)
  for (const assessment of [undefined, { ...defaultAssessment('gpl_snapshot'), origin: 'user_configured', attribution: null }]) {
    const plain = mount(t, Detail, { imageMode: true, data: { ...scoredDetail(), assessment } })
    assert.deepEqual(badgeTexts(plain), []); assert.doesNotMatch(content(plain), /非官方/)
  }
})

test('the live website detail badges its echoes from the equipped score it reads; a history entry reads nothing', async t => {
  const Detail = await loadVue(new URL('./WuwaRoleDetail.vue', import.meta.url))
  const fetch = t.mock.method(globalThis, 'fetch', async () => ({ ok: true, status: 200, json: async () => ({ configuration: { items: [] }, assessment: defaultAssessment('gpl_snapshot') }) }))
  const history = mount(t, Detail, { data: scoredDetail() })
  for (let i = 0; i < 4; i++) await nextTick()
  assert.equal(fetch.mock.callCount(), 0); assert.deepEqual(badgeTexts(history), [])
  const live = mount(t, Detail, { liveAssessment: true, data: scoredDetail() })
  for (let i = 0; i < 6; i++) await nextTick()
  assert.equal(fetch.mock.callCount(), 1)
  assert.match(fetch.mock.calls[0].arguments[0], /\/api\/assessment\/wuthering_waves\/1205\/equipped$/)
  assert.deepEqual(badgeTexts(live), ['38.52 SS', '31.58 A'])
})
