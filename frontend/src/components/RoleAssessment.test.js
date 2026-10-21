import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes, choose } from '../test-utils/vue.js'
import { invalidateSession } from '../http-client.js'
const Assessment=await loadVue(new URL('./RoleAssessment.vue',import.meta.url))
const Details=await loadVue(new URL('./NteEquippedDetails.vue',import.meta.url))

test('rich equipped text is escaped, unknowns stay visible and no raw source dump is shown',t=>{
 const root=mount(t,Details,{role:{group_type:'unknown',awaken_effects:['<img src=x onerror=alert(1)>'],suit:{id:'set',core:[{id:'i1',main_properties:[{id:'m'}]}],pie:[]}}})
 assert.match(content(root),/未提供/)
 assert.equal(nodes(root,'img').length,0)
 assert.equal(nodes(root,'details').length,0)
 assert.doesNotMatch(content(root),/core|i1|命途来源值|未得到来源验证/)
})

test('image mode shows shared assessment content without input actions or requests',t=>{
 const root=mount(t,Assessment,{game:'nte',characterId:'c1',imageMode:true,initialAssessment:{status:'scored',value:'0.00',source:'user_configured',model_version:'v1',weight_version:'w1',formula:'nte-custom-weighting-v1',contributions:[{item_id:'i1',contribution_id:'sub:attack',weight:'0',value:'0'}]}})
 assert.match(content(root),/已评分.*0.00/)
 assert.doesNotMatch(content(root),/用户配置|sub:attack|nte-custom-weighting-v1/)
 assert.equal(nodes(root,'button').length,0);assert.equal(nodes(root,'textarea').length,0)
})

test('website configuration UI saves weights/config and compares scoped pairs',async t=>{
 const previous=globalThis.fetch;const calls=[]
 t.after(()=>{globalThis.fetch=previous})
 const cfg={id:'id1',revision:1,data:{name:'saved',items:[]}}
 globalThis.fetch=async(path,options)=>{calls.push({path,options});return {ok:true,status:200,json:async()=>path.endsWith('/compare')?{model_version:'v1',a:{status:'scored',value:'1'},b:{status:'scored',value:'2'},delta:'1',percent_delta:'100.00'}:options.method==='POST'?{id:'id2'}:{model:{version:'unconfigured'},configurations:[cfg,{...cfg,id:'id2'}]}}}
 const props=reactive({game:'wuthering_waves',characterId:'c1',scopeKey:'a'})
 const root=mount(t,Assessment,props)
 const click=async label=>{const button=nodes(root,'button').find(b=>content(b)===label);await button.props.onClick();await nextTick()}
 await click('配置权重与 A/B 对比')
 const select=async(label,value)=>{choose(root,label,value);await nextTick()}
 const input=async(label,value)=>{nodes(root,'input').find(n=>n.props['aria-label']===label).props.onInput({target:{value}});await nextTick()}
 await select('新增权重词条','attack_flat');await click('添加权重词条');await input('攻击平值权重','0.1')
 await click('添加装备');await click('添加词条')
 await select('装备1词条1','attack_flat');await input('装备1词条值1','100');await select('装备1词条单位1','flat')
 nodes(root,'input').find(n=>n.props.type==='checkbox').props.onChange({target:{checked:true}});await nextTick()
 for(const text of ['攻击平值','偏好权重','词条值','已核对完整主副词条'])assert.ok(content(root).includes(text))
 await click('保存权重模型');await click('保存配置');await click('同模型重新计算并对比')
 assert.match(content(root),/变化 100.00%/)
 assert.ok(calls.some(c=>c.path.endsWith('/model')&&c.options.method==='PUT'))
 assert.ok(calls.some(c=>c.path.endsWith('/configurations')&&c.options.method==='POST'))
 const body=JSON.parse(calls.find(c=>c.path.endsWith('/configurations')&&c.options.method==='POST').options.body)
 assert.equal(body.items[0].stats_complete,true);assert.equal(body.items[0].stats[0].canonical_id,'attack_flat');assert.equal(body.items[0].stats[0].value,'100')
 props.scopeKey='b';await nextTick();assert.equal(nodes(root,'textarea').length,0);assert.doesNotMatch(content(root),/变化 100.00%/)
})

test('persisted empty NTE model opens as unconfigured structured fields',async t=>{
 const previous=globalThis.fetch;t.after(()=>{globalThis.fetch=previous})
 globalThis.fetch=async()=>({ok:true,status:200,json:async()=>({model:{game:'nte',character_id:'c1',version:'empty-v1',source:'user_configured',nte_profile:null,nte_spec:null},configurations:[]})})
 const root=mount(t,Assessment,{game:'nte',characterId:'c1'})
 await nodes(root,'button').find(b=>content(b)==='配置权重与 A/B 对比').props.onClick();await nextTick()
 assert.match(content(root),/自定义品质因子.*卡带主属性参考值.*添加装备/)
})

const reply = body => ({ ok: true, status: 200, json: async () => body })
const defer = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
const equipment = value => ({ id: 'echo', kind: 'echo', stats_complete: true, stats: [{ canonical_id: 'attack_flat', observation_id: 'one', value, unit: 'flat', role: 'sub' }] })
const scored = value => ({ status: 'scored', value, model_version: 'v1', weight_version: 'v1', source: 'user_configured' })
const saved = id => ({ id, revision: 1, data: { name: id, items: [] } })
const comparison = { model_version: 'v1', a: { status: 'scored', value: '1' }, b: { status: 'scored', value: '2' }, delta: '1', percent_delta: '100.00' }
const open = '配置权重与 A/B 对比'
// The first request matching a key of `held` ("METHOD /path-after-the-character") stays pending until the test resolves it; all others answer at once.
function editor(t, { held = [], score = () => reply(scored('10.00')) } = {}) {
  let created = false
  const calls = [], pending = Object.fromEntries(held.map(key => [key, defer()])), armed = new Set(held)
  t.mock.method(globalThis, 'fetch', async (path, options = {}) => {
    const method = options.method || 'GET', key = `${method} ${path.replace(/^\/api\/assessment\/[^/]+\/[^/]+/, '')}`
    calls.push(path)
    if (armed.delete(key)) return pending[key].promise
    if (key === 'POST /score') return score(JSON.parse(options.body))
    if (key === 'GET /equipped') return reply({ configuration: { items: [equipment('100')], observed_at: null }, assessment: scored('7.00') })
    if (key === 'POST /compare') return reply(comparison)
    if (key === 'POST /configurations') { created = true; return reply({ id: 'new-id' }) }
    if (method === 'PUT' || method === 'DELETE') return reply({})
    return reply({ model: { game: 'wuthering_waves', character_id: 'x', version: `model-of-${path.split('/').at(-1)}`, wuwa_weights: { attack_flat: '0.1' } }, configurations: [saved('id1'), saved('id2'), ...(created ? [saved('new-id')] : [])] })
  })
  const props = reactive({ game: 'wuthering_waves', characterId: 'c1', scopeKey: 'a' }), root = mount(t, Assessment, props)
  const button = label => nodes(root, 'button').find(node => content(node) === label)
  const press = label => button(label).props.onClick()
  const click = async label => { await press(label); await nextTick() }
  const field = (type, label) => nodes(root, type).find(node => node.props['aria-label'] === label)
  const settle = async () => { for (let i = 0; i < 4; i++) await nextTick() }
  const answer = async (key, body) => { pending[key].resolve(reply(body)); await settle() }
  return { root, props, calls, button, press, click, field, settle, answer }
}

test('a score is shown for the input it was computed from', async t => {
  const { root, click } = editor(t)
  await click(open); await click('导入已同步装备'); await click('评价当前输入')
  assert.match(content(root), /已评分.*10.00/)
})

test('a score still pending when the input changes never appears next to the new input', async t => {
  const late = defer(), { root, press, click, field, settle } = editor(t, { score: body => body.configuration.items[0].stats[0].value === '100' ? late.promise : reply(scored('20.00')) })
  await click(open); await click('导入已同步装备')
  const pending = press('评价当前输入'); await settle()
  field('input', '装备1词条值1').props.onInput({ target: { value: '200' } }); await settle()
  late.resolve(reply(scored('10.00'))); await pending; await settle()
  assert.doesNotMatch(content(root), /已评分/)
  assert.equal(field('input', '装备1词条值1').props.value, '200')
  await click('评价当前输入')
  assert.match(content(root), /已评分.*20.00/); assert.doesNotMatch(content(root), /10.00/)
})

test('a comparison still pending when the weights change is dropped', async t => {
  const { root, press, click, field, settle, answer } = editor(t, { held: ['POST /compare'] })
  await click(open)
  const pending = press('同模型重新计算并对比'); await settle()
  field('input', '攻击平值权重').props.onInput({ target: { value: '0.2' } })
  await answer('POST /compare', comparison); await pending; await settle()
  assert.doesNotMatch(content(root), /变化 100.00%/)
  await click('同模型重新计算并对比')
  assert.match(content(root), /变化 100.00%/)
})

test('picking another A or B removes the comparison, and both picks are locked while one runs', async t => {
  const { root, press, click, field, settle, answer } = editor(t, { held: ['POST /compare'] })
  await click(open)
  const pending = press('同模型重新计算并对比'); await settle()
  assert.equal(field('button', '配置 A').props.disabled, true); assert.equal(field('button', '配置 B').props.disabled, true)
  await answer('POST /compare', comparison); await pending; await settle()
  assert.match(content(root), /变化 100.00%/)
  choose(root, '配置 B', 'id1'); await settle()
  assert.doesNotMatch(content(root), /变化 100.00%/)
})

test('saving a configuration moves B to it and removes the comparison of the previous pair', async t => {
  const { root, click, field } = editor(t)
  await click(open); await click('同模型重新计算并对比')
  assert.match(content(root), /变化 100.00%/)
  await click('保存配置')
  assert.equal(nodes(nodes(root,'ul').find(n=>n.props['aria-label']==='配置 B'),'li').find(n=>n.props['aria-selected']).props['data-value'], 'new-id')
  assert.doesNotMatch(content(root), /变化 100.00%/)
})

test('deleting a configuration removes the comparison even when the list cannot be read again', async t => {
  let deleted = false
  t.mock.method(globalThis, 'fetch', async (path, options = {}) => {
    const method = options.method || 'GET'
    if (path.endsWith('/compare')) return reply(comparison)
    if (method === 'DELETE') { deleted = true; return reply({ deleted: true }) }
    if (deleted) return { ok: false, status: 503, json: async () => ({ detail: 'unavailable' }) }
    return reply({ model: { game: 'wuthering_waves', character_id: 'c1', version: 'v1', wuwa_weights: { attack_flat: '0.1' } }, configurations: [saved('id1'), saved('id2')] })
  })
  const root = mount(t, Assessment, reactive({ game: 'wuthering_waves', characterId: 'c1', scopeKey: 'a' }))
  const click = async label => { await nodes(root, 'button').find(node => content(node) === label).props.onClick(); for (let i = 0; i < 4; i++) await nextTick() }
  await click(open); await click('同模型重新计算并对比')
  assert.match(content(root), /变化 100.00%/)
  await click('删除配置')
  assert.doesNotMatch(content(root), /变化 100.00%/)
})

test('editing the advanced JSON removes the score and the comparison computed from the old input', async t => {
  const { root, click, field, settle } = editor(t)
  await click(open); await click('导入已同步装备'); await click('评价当前输入'); await click('同模型重新计算并对比')
  assert.match(content(root), /已评分.*10.00/); assert.match(content(root), /变化 100.00%/)
  field('textarea', '装备输入 JSON').props.onInput({ target: { value: JSON.stringify([equipment('200')]) } }); await settle()
  assert.doesNotMatch(content(root), /已评分|变化 100.00%/)
  assert.equal(field('input', '装备1词条值1').props.value, '200')
  await click('评价当前输入'); await click('同模型重新计算并对比')
  assert.match(content(root), /已评分.*10.00/); assert.match(content(root), /变化 100.00%/)
  field('textarea', '权重及公式配置 JSON').props.onInput({ target: { value: '{"wuwa_weights":{"attack_flat":"0.5"}}' } }); await settle()
  assert.doesNotMatch(content(root), /已评分|变化 100.00%/)
})

test('saving or deleting a configuration keeps the score of the input in the editor', async t => {
  const { root, click } = editor(t)
  await click(open); await click('导入已同步装备'); await click('评价当前输入')
  await click('保存配置'); assert.match(content(root), /已评分.*10.00/)
  await click('删除配置'); assert.match(content(root), /已评分.*10.00/)
})

const scenarios = [
  ['reading the equipped copy', '导入已同步装备', 'GET /equipped', { configuration: { items: [equipment('100')], observed_at: null }, assessment: scored('7.00') }],
  ['scoring', '评价当前输入', 'POST /score', scored('10.00')],
  ['comparing', '同模型重新计算并对比', 'POST /compare', comparison],
  ['saving a configuration', '保存配置', 'POST /configurations', { id: 'new-id' }],
  ['saving the model', '保存权重模型', 'PUT /model', {}],
  ['deleting a configuration', '删除配置', 'DELETE /configurations/id1', {}],
]
for (const [name, label, key, body] of scenarios) test(`${name} still pending when the character changes writes nothing for the new character`, async t => {
  const { root, props, calls, button, press, click, field, settle, answer } = editor(t, { held: [key] })
  await click(open)
  const pending = press(label); await settle()
  props.characterId = 'c2'; await settle()
  assert.ok(button(open), 'the editor closes with the switch')
  const before = calls.length
  await answer(key, body); await pending; await settle()
  assert.deepEqual(calls.slice(before), [], 'the late response must not start further requests')
  assert.doesNotMatch(content(root), /已评分|会话或角色已变化/)
  await click(open)
  assert.doesNotMatch(content(root), /已评分|变化|装备 1/)
  assert.equal(field('input', '模型版本').props.value, 'model-of-c2')
  assert.equal(nodes(nodes(root,'ul').find(n=>n.props['aria-label']==='配置 B'),'li').find(n=>n.props['aria-selected']).props['data-value'], 'id2')
  assert.equal(field('input', '配置名称').props.value, '配置 A')
})

test('a read of the old character neither fills the new character nor frees the busy state of its pending action', async t => {
  const { root, props, button, press, click, field, settle, answer } = editor(t, { held: ['GET ', 'POST /score'] })
  const oldRead = press(open); await settle()
  props.characterId = 'c2'; await settle()
  await click(open)
  const newScore = press('评价当前输入'); await settle()
  assert.equal(button('保存配置').props.disabled, true)
  await answer('GET ', { model: { version: 'model-of-c1', wuwa_weights: {} }, configurations: [saved('stale')] }); await oldRead; await settle()
  assert.equal(field('input', '模型版本').props.value, 'model-of-c2')
  assert.doesNotMatch(content(root), /stale/)
  assert.equal(button('保存配置').props.disabled, true, 'the old read finished and freed the new action')
  await answer('POST /score', scored('9.00')); await newScore; await settle()
  assert.match(content(root), /已评分.*9.00/); assert.equal(button('保存配置').props.disabled, false)
})

test('a request cut off by the session ending neither shows its error nor frees the action that follows', async t => {
  const { root, button, press, click, settle, answer } = editor(t, { held: ['POST /score', 'GET /equipped'] })
  await click(open)
  const cutOff = press('评价当前输入'); await settle()
  invalidateSession(); await settle()
  assert.ok(button(open), 'the editor closes with the session')
  await click(open)
  const next = press('导入已同步装备'); await settle()
  assert.equal(button('保存配置').props.disabled, true)
  await answer('POST /score', scored('10.00')); await cutOff; await settle()
  assert.doesNotMatch(content(root), /会话或角色已变化|已评分/)
  assert.equal(button('保存配置').props.disabled, true, 'the cut-off request finished and freed the action that follows')
  await answer('GET /equipped', { configuration: { items: [equipment('100')], observed_at: null }, assessment: scored('7.00') }); await next; await settle()
  assert.match(content(root), /已评分.*7.00/); assert.equal(button('保存配置').props.disabled, false)
})


test('NTE web menus retain unknown source stats, disabled quality and explicit units', async t => {
  t.mock.method(globalThis, 'fetch', async () => reply({ model: { version: 'unconfigured' }, configurations: [] }))
  const root = mount(t, Assessment, { game: 'nte', characterId: 'c1' })
  const click = async label => { await nodes(root,'button').find(n=>content(n)===label).props.onClick(); await nextTick() }
  const field = label => nodes(root,'button').find(n=>n.props['aria-label']===label)
  await click(open); await click('添加装备')
  assert.equal(nodes(root,'select').length, 0)
  assert.equal(field('装备品质').props.disabled, true)
  choose(root,'装备类型','cartridge'); await nextTick()
  assert.equal(field('装备品质').props.disabled, false)
  assert.ok(field('卡带主词条'))
  choose(root,'卡带主词条单位','percent_points'); await nextTick()
  const input = nodes(root,'textarea').find(n=>n.props['aria-label']==='装备输入 JSON')
  let items = JSON.parse(input.props.value)
  assert.equal(items[0].nte.mainstat.unit, 'percent_points')
  items[0].nte.substats = [{ canonical_id: 'source-only', observation_id: 's1', value: '10', unit: 'flat' }]
  input.props.onInput({ target: { value: JSON.stringify(items) } }); await nextTick()
  assert.match(content(field('装备1词条1')), /source-only（来源词条，待声明）/)
  choose(root,'装备1词条单位1','ratio'); await nextTick()
  items = JSON.parse(nodes(root,'textarea').find(n=>n.props['aria-label']==='装备输入 JSON').props.value)
  assert.equal(items[0].nte.substats[0].canonical_id, 'source-only')
  assert.equal(items[0].nte.substats[0].unit, 'ratio')
})
