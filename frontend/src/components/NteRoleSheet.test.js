import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'

const Sheet = await loadVue(new URL('./NteRoleSheet.vue', import.meta.url))
const stat = (id, name, value) => ({ id, name, value })
const role = (extra = {}) => ({
  id: '1003', name: '早雾', quality: 'S', element: '灵', level: 80, awaken_level: 3, mix_level: 1,
  icon_url: 'https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/character/detail/1003.png',
  weapon: { name: '合成弧盘', quality: 'S', level: 80, mix_level: 1, breakthrough_level: 4, properties: [stat('atk', '基础攻击力', '570')] },
  properties: [stat('hp', '生命值', '22400'), stat('crit', '暴击率', '88.2%'), stat('heal', '治疗加成', '0%'), stat('light', '光属性异能伤害增强', '0%'), stat('general', '通用伤害增强', '10.2%')],
  skills: [{ name: '普通攻击', level: 9 }], city_skills: [{ name: '城区一', level: 2 }],
  suit: { name: '「街头拳王」', activation_count: 4,
    core: [{ id: 'Street_orange', name: '「街头拳王」', level: 20, main_properties: [stat('CritBase', '暴击率', '30%')], properties: [stat('critdamagebase', '暴击伤害', '20%'), stat('defadd', '防御力', '80')] }],
    pie: [{ id: 'cell3_style3_1_purple', name: 'Ⅲ型驱动', level: 20, main_properties: [stat('atkadd', '攻击力', '63')], properties: [stat('critbase', '暴击率', '3%')] },
      { id: 'cell4_style9_1_blue', name: 'Ⅳ型驱动', level: 20, main_properties: [], properties: [] }] },
  ...extra,
})
const assessment = { status: 'scored', value: '159.44', max_value: '310', grade: 's', origin: 'builtin_default', attribution: 'nte_workshop', item_results: [
  { item_id: 'core:0:Street_orange', status: 'scored', value: '71.11', max_value: '150', grade: 'a',
    contributions: [{ contribution_id: 'main:critbase', effective: true }, { contribution_id: 'sub:critdamagebase', effective: true }, { contribution_id: 'sub:defadd', effective: false }] },
  { item_id: 'pie:0:cell3_style3_1_purple', status: 'scored', value: '8.33', max_value: '30', grade: 'ss', contributions: [{ contribution_id: 'sub:critbase', effective: true }] },
] }
const byClass = (root, name) => ['div', 'p', 'span', 'article', 'section'].flatMap(tag => nodes(root, tag)).filter(n => String(n.props.class ?? '').split(' ').includes(name))

test('the sheet leads with the official art and facts, lists non-zero attributes and leaves city skills out', t => {
  const root = mount(t, Sheet, { role: role() })
  assert.equal(nodes(root, 'img')[0].props.src, 'https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/character/detail/1003.png')
  assert.match(content(root), /早雾 Lv80 S 元素 灵 觉醒 3 混频 1 .*合成弧盘 S Lv80 混频 1 突破 4 基础攻击力 570/)
  assert.match(content(root), /属性 其余 2 项为 0，未列出 生命值 22400 暴击率 88.2% 通用伤害增强 10.2%/)
  assert.doesNotMatch(content(root), /治疗加成|光属性|城区一/)
  // A zero core attribute still shows: only the others are dropped.
  assert.match(content(mount(t, Sheet, { role: role({ properties: [stat('crit', '暴击率', '0%')] }) })), /暴击率 0%/)
})

test('pieces show the card label, shape, badge and coloured stats; unknown shapes fall back to the cell count', t => {
  const root = mount(t, Sheet, { role: { ...role(), assessment } })
  assert.match(content(byClass(root, 'role-score-hero')[0]), /^S 装备评分 159.44 \/ 310 非官方 · 权重配置来自：异环工坊$/)
  assert.deepEqual(byClass(root, 'piece-score').map(content), ['71.11 A', '8.33 SS'])
  assert.deepEqual(byClass(root, 'piece-title').map(content), ['「街头拳王」 卡带 · Lv20', 'Ⅲ型驱动 驱动 · Lv20', 'Ⅳ型驱动 驱动 · Lv20'])
  const shapes = byClass(root, 'piece-shape')
  assert.deepEqual(shapes.map(n => n.props['aria-label']), ['Ⅲ型驱动 形状', '4 格'])
  assert.deepEqual(byClass(shapes[0], 'shape-row').map(row => nodes(row, 'i').map(i => String(i.props.class).includes('filled') ? '#' : '.').join('')), ['#.', '##'])
  const tones = nodes(root, 'div').filter(n => /stat-(in)?effective/.test(String(n.props.class ?? ''))).map(n => `${content(n)}:${n.props.class}`)
  assert.deepEqual(tones, ['暴击率 30%:stat-effective', '暴击伤害 20%:stat-effective', '防御力 80:stat-ineffective', '暴击率 3%:stat-effective'],
    'the main stat id matches case-insensitively; the unscored drive main stat stays plain')
})

test('no assessment draws no score card; nothing equipped says so', t => {
  assert.equal(byClass(mount(t, Sheet, { role: role() }), 'role-score-hero').length, 0)
  const bare = mount(t, Sheet, { role: role({ suit: null, assessment }) })
  assert.equal(byClass(bare, 'role-score-hero').length, 0)
  assert.match(content(bare), /卡带与驱动 未装备/)
})

test('art that fails to load is dropped instead of leaving its alt text over the name', async t => {
  const { nextTick } = await import('vue')
  const root = mount(t, Sheet, { role: role({ id: '9999', name: '合成角色' }) })
  nodes(root, 'img')[0].props.onError(); await nextTick()
  assert.ok(nodes(root, 'img').every(n => !String(n.props.src).includes('character/detail')))
})
