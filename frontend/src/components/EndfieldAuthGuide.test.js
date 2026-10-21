import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
const Guide = await loadVue(new URL('./EndfieldAuthGuide.vue', import.meta.url))
const choice = (provider, id, channel, name) => ({ key: `${id}:r`, account: { account_id: id, provider, channel, roles: [{ role_id: 'r', display_name: name }] }, role: 'r', sources: {} })
const link = root => nodes(root, 'a')[0]

test('a missing Skland authorization says what it unlocks and stresses the one-click connection when a Hypergryph one exists', t => {
  const root = mount(t, Guide, { need: 'skland', passport: true })
  assert.match(content(root), /需要补授权：森空岛档案/)
  assert.match(content(root), /概览档案、全员练度、地区建设、帝江号、光荣之路、挑战记录和蓝图收藏/)
  assert.equal(link(root).props.href, '#/accounts?focus=skland')
  assert.match(content(link(root)), /一键连接森空岛档案/); assert.match(link(root).props.class, /primary/)
  const manual = mount(t, Guide, { need: 'skland' })
  assert.equal(link(manual).props.href, '#/accounts?focus=skland')
  assert.match(content(link(manual)), /前往账号与授权/); assert.doesNotMatch(String(link(manual).props.class), /primary/)
  assert.doesNotMatch(content(manual), /一键连接/)
})

test('a missing Hypergryph authorization unlocks gacha and links to the authorization page', t => {
  const root = mount(t, Guide, { need: 'hypergryph', passport: false, candidates: [choice('hypergryph', 'h', 'official', '单一')] })
  assert.match(content(root), /需要补授权：鹰角寻访/); assert.match(content(root), /寻访抽卡统计/)
  assert.equal(link(root).props.href, '#/accounts')
  assert.doesNotMatch(content(root), /查看角色/, 'a single candidate is the automatic fallback, not a choice')
})

test('several unpaired candidates ask for a choice in 查看角色 and list each by name, channel and source', t => {
  const root = mount(t, Guide, { need: 'skland', passport: true, candidates: [choice('skland', 'a', 'unknown', '甲'), choice('skland', 'b', 'official', '乙')] })
  assert.match(content(root), /请在“查看角色”中选择对应角色/)
  assert.deepEqual(nodes(root, 'li').map(content), ['甲 · 渠道未提供 · 森空岛档案', '乙 · 官服 · 森空岛档案'])
  assert.equal(nodes(root, 'a').length, 0)
  assert.doesNotMatch(content(root), /需要补授权/)
})
