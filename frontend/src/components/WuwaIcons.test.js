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

// M8: the score is part of the echo section (header total and source, a badge per echo), never a block of its own.
const scoredDetail = () => ({
  role: { role_id: 1205, role_name: '角色甲' },
  phantom_data: { cost: 11, equip_phantom_list: [
    { cost: 4, phantom_prop: { name: '声骸甲' } }, null, { cost: 3, phantom_prop: { name: '声骸乙' } }, { phantom_prop: { name: '声骸丙' } },
  ] },
})
const echoItems = () => [
  { item_id: 'echo:0:unknown', status: 'scored', value: '38.52', grade: 'ss', max_value: 50, cost: 4 },
  { item_id: 'echo:2:unknown', status: 'scored', value: '31.58', grade: 'a', max_value: 50, cost: 3 },
  { item_id: 'echo:3:unknown', status: 'unscorable', reason: 'UNKNOWN_COST', value: null, grade: null, max_value: null, cost: null },
]
const defaultAssessment = (attribution, scored = true) => ({ status: scored ? 'scored' : 'unscorable', value: scored ? '146.82' : null, grade: scored ? 'b' : null, max_value: 250,
  partial: !scored, partial_known_total: scored ? null : '70.10', origin: 'builtin_default', unofficial: true, attribution, source: 'builtin_default', model_version: 'builtin-1', item_results: echoItems() })
const noDefault = { status: 'unconfigured', value: null, reason: 'NO_WEIGHTS', model_version: 'unconfigured', source: 'user_configured', origin: null, item_results: [], partial: null }
const badgeTexts = root => nodes(root, 'p').filter(n => n.props.class === 'wuwa-echo-score').map(content)
const echoHeader = root => content(nodes(nodes(root, 'section').find(n => String(n.props.class).includes('wuwa-detail-echoes')), 'h3')[0]).trim()
const blocks = root => nodes(root, 'section').filter(n => String(n.props.class ?? '').includes('personal-assessment'))
const ok = body => ({ ok: true, status: 200, json: async () => body })
const reply = assessment => ok({ configuration: { items: [] }, assessment })
const settle = async () => { for (let i = 0; i < 6; i++) await nextTick() }

test('image: the total, grade and unofficial source sit in the echo header, each scored echo has a badge, and no score block exists', async t => {
  const Detail = await loadVue(new URL('./WuwaRoleDetail.vue', import.meta.url))
  const fetch = t.mock.method(globalThis, 'fetch', async () => { throw new Error('no request in images') })
  const image = data => mount(t, Detail, { imageMode: true, data: { ...scoredDetail(), ...data } })
  const scored = image({ assessment: defaultAssessment('gpl_snapshot') })
  assert.equal(echoHeader(scored), '装备声骸 总 COST 11 总分 146.82 / 250 · B 非官方 · 权重改编自 WutheringWavesUID（GPL-3.0）')
  assert.deepEqual(badgeTexts(scored), ['38.52 SS', '31.58 A'])
  const tiles = nodes(scored, 'article').filter(n => /声骸/.test(content(n)))
  assert.deepEqual(tiles.map(n => badgeTexts(n).length), [1, 1, 0], 'the unscorable echo has no badge')
  assert.deepEqual(blocks(scored), []); assert.doesNotMatch(content(scored), /默认评分|装备 1：|权重设置/)
  assert.match(echoHeader(image({ assessment: defaultAssessment('self_made') })), /总分 146.82 \/ 250 · B 非官方 · 自制权重$/)
  const partial = image({ assessment: defaultAssessment('gpl_snapshot', false) })
  assert.equal(echoHeader(partial), '装备声骸 总 COST 11 非官方 · 权重改编自 WutheringWavesUID（GPL-3.0）')
  assert.deepEqual(badgeTexts(partial), ['38.52 SS', '31.58 A'])
  for (const assessment of [undefined, noDefault, { ...noDefault, status: 'unscorable', reason: 'NO_EQUIPMENT', model_version: 'builtin-1', origin: 'builtin_default' }]) {
    const plain = image({ assessment })
    assert.equal(echoHeader(plain), '装备声骸 总 COST 11'); assert.deepEqual(badgeTexts(plain), []); assert.deepEqual(blocks(plain), [])
  }
  // A personal model replaces the default wholly: its score is shown as personal, never as unofficial.
  const own = image({ assessment: { ...defaultAssessment(null), origin: 'user_configured', unofficial: null, source: 'user_configured' } })
  assert.equal(echoHeader(own), '装备声骸 总 COST 11 总分 146.82 / 250 · B 个人权重')
  const weights = image({ assessment: { status: 'scored', value: '3.00', origin: 'user_configured', source: 'user_configured', max_value: null, grade: null, item_results: [] } })
  assert.equal(echoHeader(weights), '装备声骸 总 COST 11 评分 3.00 个人权重')
  await settle(); assert.equal(fetch.mock.callCount(), 0)
})

function liveDetail(t, { equipped = () => reply(defaultAssessment('gpl_snapshot')), model = { game: 'wuthering_waves', character_id: '1205', version: 'mine', source: 'user_configured', wuwa_weights: { attack_flat: '1' } } } = {}) {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options = {}) => {
    const key = `${options.method || 'GET'} ${path.replace(/^\/api\/assessment\/[^/]+\/[^/]+/, '')}`
    calls.push(key)
    if (key === 'GET /equipped') return equipped()
    if (key === 'DELETE /model') return ok({ deleted: true })
    return ok({ model, configurations: [] })
  })
  return { calls, root: null }
}
const press = async (root, label) => { await nodes(root, 'button').find(n => content(n) === label).props.onClick(); await settle() }

test('website: the live detail reads the equipped score on mount and shows it in the echo header, with no result panel', async t => {
  const Detail = await loadVue(new URL('./WuwaRoleDetail.vue', import.meta.url))
  const { calls } = liveDetail(t)
  const root = mount(t, Detail, { liveAssessment: true, data: scoredDetail() })
  await settle()
  assert.deepEqual(calls, ['GET /equipped'])
  assert.equal(echoHeader(root), '装备声骸 总 COST 11 总分 146.82 / 250 · B 非官方 · 权重改编自 WutheringWavesUID（GPL-3.0） 权重设置')
  assert.deepEqual(badgeTexts(root), ['38.52 SS', '31.58 A'])
  assert.deepEqual(blocks(root), []); assert.doesNotMatch(content(root), /默认评分|个人权重评分|装备 1：/)
})

test('website: 权重设置 opens the editor below the echoes; 恢复默认 deletes the personal model, closes it and reads the score again', async t => {
  const Detail = await loadVue(new URL('./WuwaRoleDetail.vue', import.meta.url))
  const { calls } = liveDetail(t)
  const root = mount(t, Detail, { liveAssessment: true, data: scoredDetail() })
  await settle(); await press(root, '权重设置')
  const [editor] = blocks(root)
  assert.ok(nodes(nodes(root, 'section').find(n => String(n.props.class).includes('wuwa-detail-echoes')), 'section').includes(editor), 'the editor opens inside the echo section')
  assert.match(content(editor), /个人权重设置.*保存权重模型.*恢复默认/)
  assert.ok(nodes(root, 'button').some(n => content(n) === '收起权重设置' && n.props['aria-expanded'] === true))
  assert.match(echoHeader(root), /总分 146.82/, 'the header keeps the equipped score while the editor is open')
  await press(root, '恢复默认')
  assert.deepEqual(calls, ['GET /equipped', 'GET ', 'DELETE /model', 'GET /equipped'])
  assert.deepEqual(blocks(root), []); assert.match(echoHeader(root), /总分 146.82 \/ 250 · B 非官方/)
  await press(root, '权重设置'); await press(root, '收起'); assert.deepEqual(blocks(root), [])
})

test('website: loading, a read failure and a character without default weights show compactly in the echo header', async t => {
  const Detail = await loadVue(new URL('./WuwaRoleDetail.vue', import.meta.url))
  let answer = null
  liveDetail(t, { equipped: () => answer ? answer() : new Promise(() => {}) })
  const loading = mount(t, Detail, { liveAssessment: true, data: scoredDetail() })
  await settle(); assert.match(echoHeader(loading), /正在读取评分… 权重设置$/)
  answer = () => ({ ok: false, status: 503, json: async () => ({ detail: 'unavailable' }) })
  const failed = mount(t, Detail, { liveAssessment: true, data: scoredDetail() })
  await settle(); assert.match(echoHeader(failed), /评分读取失败：/)
  assert.ok(nodes(failed, 'span').some(n => n.props.role === 'alert'))
  answer = () => reply(noDefault)
  const none = mount(t, Detail, { liveAssessment: true, data: scoredDetail() })
  await settle(); assert.equal(echoHeader(none), '装备声骸 总 COST 11 暂无默认权重 权重设置')
})

test('history entries keep the stand-alone editor block and request nothing', async t => {
  const Detail = await loadVue(new URL('./WuwaRoleDetail.vue', import.meta.url))
  const { calls } = liveDetail(t)
  const root = mount(t, Detail, { data: scoredDetail() })
  await settle()
  assert.deepEqual(calls, []); assert.deepEqual(badgeTexts(root), [])
  assert.equal(echoHeader(root), '装备声骸 总 COST 11')
  assert.match(content(blocks(root)[0]), /个人权重评分 配置权重与 A\/B 对比/)
})
