import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'

const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }

test('guides remain accessible when the private character panel cannot be fetched', async t => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, status: 502 }))
  const Roles = await loadVue(new URL('./WuwaRoles.vue', import.meta.url))
  const root = mount(t, Roles, { accountKey: 'test:server', snap: { payload: [{ role_id: '1304', name: '今汐' }] } })
  nodes(root, 'button').find(n => content(n).includes('今汐')).props.onClick()
  await tick()
  assert.equal(nodes(root, 'dialog').length, 1, '角色详情应在弹出式窗口内')
  const guideTab = nodes(root, 'button').find(n => content(n) === '培养攻略')
  assert.ok(guideTab, '角色详情提供独立的培养攻略入口')
  guideTab.props.onClick()
  await tick()
  assert.match(content(root), /武器推荐/)
  assert.match(content(root), /时和岁稔/)
  assert.match(content(root), /3\.5/)
  assert.doesNotMatch(content(root), /来源暂时不可用/)
})

test('closing the role dialog removes both tabs and ignores a late private response', async t => {
  let finish
  t.mock.method(globalThis, 'fetch', () => new Promise(resolve => { finish = resolve }))
  const Roles = await loadVue(new URL('./WuwaRoles.vue', import.meta.url))
  const root = mount(t, Roles, { accountKey: 'test:server', snap: { payload: [{ role_id: '1304', name: '今汐' }] } })
  nodes(root, 'button').find(n => content(n).includes('今汐')).props.onClick()
  await tick()
  assert.equal(nodes(root, 'dialog').length, 1)
  nodes(root, 'button').find(n => content(n) === '关闭详情').props.onClick()
  await tick()
  finish({ ok: true, json: async () => ({ payload: { character_id: '1304', data: { role: { role_name: 'LATE_PRIVATE' } } } }) })
  await tick()
  assert.equal(nodes(root, 'dialog').length, 0)
  assert.doesNotMatch(content(root), /LATE_PRIVATE/)
})

test('switching character forms replaces all recommendations and unknown IDs show an empty state', async t => {
  const Guide = await loadVue(new URL('./WuwaGuide.vue', import.meta.url))
  const props = reactive({ characterId: '1402' })
  const root = mount(t, Guide, props)
  assert.match(content(root), /标签有冲突/)
  props.characterId = '1610'
  await nextTick()
  assert.match(content(root), /秧秧·玄翎/)
  assert.match(content(root), /羽落空尘之歌/)
  assert.doesNotMatch(content(root), /标签有冲突/)
  props.characterId = '9999'
  await nextTick()
  assert.match(content(root), /此角色形态暂未收录攻略/)
  assert.doesNotMatch(content(root), /羽落空尘之歌/)
})

test('pending fields are visible, and every recommendation exposes its own version and source', async t => {
  const Guide = await loadVue(new URL('./WuwaGuide.vue', import.meta.url))
  const root = mount(t, Guide, { characterId: '1202' })
  assert.match(content(root), /待核验/)
  assert.match(content(root), /没有明确的技能加点顺序/)
  assert.match(content(root), /V2\.0/)
  for (const link of nodes(root, 'a')) {
    assert.match(link.props.href, /^https:\/\/www\.kurobbs\.com\/forum\/post\/\d+$/)
    assert.equal(link.props.rel, 'noopener noreferrer')
  }
})
