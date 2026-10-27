import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'

const Equipped = await loadVue(new URL('./NteEquippedDetails.vue', import.meta.url))
const RoleDetail = await loadVue(new URL('./NteRoleDetail.vue', import.meta.url))
const completeRole = () => ({
  id: '1003', name: '早雾', awaken_effects: ['Effect1', '觉醒名称：完整觉醒描述末尾', '没有标题的一整段很长的觉醒效果描述末尾'],
  weapon: { name: '合成弧盘', breakthrough_level: 2, description: '弧盘故事末尾', buff_name: '弧盘效果名', buff_description: '弧盘效果描述末尾', properties: [{ name: '攻击', value: '570' }] },
  skills: [{ name: '战技名称', level: 0, items: [{ title: '战技效果', desc: '完整战技描述末尾' }] }],
  city_skills: [{ name: '城区技能名称', level: null, items: [{ title: '城区效果', desc: '完整城区描述末尾' }] }],
  suit: { name: '合成套装', activation_count: 4, description_two: '二件效果末尾', description_four: '四件效果末尾', core: [{ name: '合成驱动', level: 20, main_properties: [{ name: '攻击力', value: '63' }], properties: [{ name: '暴击率', value: '3%' }] }], pie: [] },
})
const DETAILS = /完整觉醒描述末尾|觉醒效果描述末尾|弧盘故事末尾|弧盘效果|战技说明|城区技能说明|完整战技描述末尾|完整城区描述末尾|二件|四件|补充资料与原文|Effect1|待核验/

for (const imageMode of [false, true]) test(`${imageMode ? 'image' : 'web'} equipped details keep names, levels and stats without effect text`, t => {
  const root = mount(t, Equipped, { role: completeRole(), imageMode })
  assert.match(content(root), /觉醒 觉醒 1 · 觉醒名称 · 觉醒 3/)
  assert.match(content(root), /弧盘资料 合成弧盘 · 突破 2 攻击 570/)
  assert.match(content(root), /已装备套装 合 合成套装 激活数 4 空幕 1 件 合成驱动 · Lv20 主属性 攻击力 63 副属性 暴击率 3%/)
  assert.doesNotMatch(content(root), DETAILS)
})

const classOf = n => String(n.props.class || '')
const byClass = (root, name) => nodes(root, 'article').concat(nodes(root, 'p'), nodes(root, 'div'), nodes(root, 'header'), nodes(root, 'h5')).filter(n => classOf(n).split(' ').includes(name))
const fullSuit = () => ({ ...completeRole(), suit: { name: '迪亚波罗斯', activation_count: 4,
  core: [1, 2, 3, 4].map(i => ({ name: `合成空幕${i}`, level: 20, main_properties: [{ name: '攻击力', value: '63' }], properties: [{ name: '暴击率', value: '3%' }] })),
  pie: [{ name: '合成驱动A', level: null, main_properties: [], properties: [{ name: '暴击伤害', value: '6%' }] }, { name: '合成驱动B', level: 15 }] } })

test('drives get one cell per piece under 空幕 and 驱动 with the set icon from the catalog', t => {
  const root = mount(t, Equipped, { role: fullSuit() })
  assert.equal(byClass(root, 'nte-drive').length, 6)
  assert.deepEqual(byClass(root, 'nte-drive-group-title').map(content), ['空幕 4 件', '驱动 2 件'])
  const icon = nodes(byClass(root, 'nte-suit-head')[0], 'img')[0]
  assert.match(icon.props.src, /^https:\/\/webstatic\.tajiduo\.com\/.*suit1\.png$/)
  // Unknown stays unknown: a missing level or stat list is 未提供, never 0 or an empty cell.
  assert.match(content(root), /合成驱动A · Lv未提供 主属性 未提供 副属性 暴击伤害 6%/)
  assert.match(content(root), /合成驱动B · Lv15 主属性 未提供 副属性 未提供/)
})

test('each scored piece shows value / maximum and grade; unscorable pieces show nothing', t => {
  const role = fullSuit()
  role.suit.core[0].id = 'nature_orange'; role.suit.pie[0].id = 'cell2_style1_1_purple'; role.suit.pie[1].id = 'cell2_style1_9_orange'
  const assessment = { item_results: [
    { item_id: 'core:0:nature_orange', status: 'scored', value: '116.05', max_value: '150', grade: 'SSS' },
    { item_id: 'pie:0:cell2_style1_1_purple', status: 'scored', value: '11.37', max_value: '20', grade: 's' },
    { item_id: 'core:1:unknown', status: 'unscorable', value: null, max_value: null, reason: 'UNKNOWN_MAIN_REFERENCE' },
    // A different piece at that position (the list changed since scoring) gets no badge.
    { item_id: 'pie:1:cell3_style1_1_orange', status: 'scored', value: '20.00', max_value: '30', grade: 'SS' },
  ] }
  for (const imageMode of [false, true]) {
    const scores = byClass(mount(t, Equipped, { role, imageMode, assessment }), 'nte-drive-score')
    assert.deepEqual(scores.map(content), ['116.05 / 150 SSS', '11.37 / 20 S'])
    assert.equal(scores[0].props['aria-label'], '单件评分 116.05 / 150 等级 SSS')
  }
  assert.equal(byClass(mount(t, Equipped, { role }), 'nte-drive-score').length, 0)
  assert.doesNotMatch(content(mount(t, Equipped, { role })), /评分待接入/)
})

test('a set without pieces says so instead of showing empty groups', t => {
  const root = mount(t, Equipped, { role: { ...completeRole(), suit: { name: '合成套装', activation_count: null, core: [], pie: null } } })
  assert.equal(byClass(root, 'nte-drive-group').length, 0)
  assert.match(content(root), /合成套装 激活数 未提供 驱动件 未提供/)
})

const piece = (kind, i) => ({ name: `合成${kind}${i}`, level: 20, main_properties: [{ name: '攻击力', value: '63' }], properties: [{ name: '暴击率', value: '3%' }] })
const suitWith = (core, pie) => ({ ...completeRole(), suit: { name: '迪亚波罗斯', activation_count: 2, core, pie } })

test('any real piece count gets one cell per piece and empty groups lose their heading', t => {
  const range = (kind, n) => Array.from({ length: n }, (_, i) => piece(kind, i + 1))
  for (const imageMode of [false, true]) for (const [core, pie] of [[0, 1], [1, 0], [3, 0], [5, 1], [4, 3], [0, 5], [7, 2]]) {
    const root = mount(t, Equipped, { role: suitWith(range('空幕', core), range('驱动', pie)), imageMode })
    assert.equal(byClass(root, 'nte-drive').length, core + pie)
    assert.deepEqual(byClass(root, 'nte-drive-group-title').map(content), [...(core ? [`空幕 ${core} 件`] : []), ...(pie ? [`驱动 ${pie} 件`] : [])])
    assert.doesNotMatch(content(root), /未提供/)
  }
})

test('a missing group or malformed pieces are skipped; no pieces at all stays 未提供, never 0 件', t => {
  const root = mount(t, Equipped, { role: suitWith(undefined, [null, 'x', piece('驱动', 1), 7]), imageMode: true })
  assert.equal(byClass(root, 'nte-drive').length, 1)
  assert.deepEqual(byClass(root, 'nte-drive-group-title').map(content), ['驱动 1 件'])
  const none = mount(t, Equipped, { role: suitWith([null], {}) })
  assert.equal(byClass(none, 'nte-drive-group').length, 0)
  assert.match(content(none), /驱动件 未提供/)
  assert.doesNotMatch(content(none), /0 件/)
})

test('the full role detail shows skill names and levels only, in both modes', t => {
  for (const imageMode of [false, true]) {
    const root = mount(t, RoleDetail, { role: completeRole(), imageMode })
    assert.match(content(root), /战技名称.*Lv0.*城区技能名称.*未提供/)
    assert.doesNotMatch(content(root), DETAILS)
  }
})

test('missing awakening data stays unknown rather than empty', t => {
  const root = mount(t, Equipped, { role: { awaken_effects: [] } })
  assert.match(content(root), /觉醒 未提供/)
})
