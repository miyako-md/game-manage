import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, content } from '../test-utils/vue.js'

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
  assert.match(content(root), /合成套装 · 激活数 4.*合成驱动 · Lv20.*主 · 攻击力.*63.*副 · 暴击率.*3%/)
  assert.doesNotMatch(content(root), DETAILS)
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
