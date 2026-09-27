import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'

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
  assert.match(content(root), /Lv.0/)
  assert.match(content(root), /完整技能条件/)
  assert.match(content(root), /未提供装备声骸/)
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
