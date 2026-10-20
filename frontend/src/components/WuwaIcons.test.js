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
