import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue,mount,nodes,content,choose } from '../test-utils/vue.js'
const Nte=await loadVue(new URL('./NteRolesPanel.vue',import.meta.url))
const Wuwa=await loadVue(new URL('./WuwaRoles.vue',import.meta.url))
const Browser=await loadVue(new URL('./WuwaGuideBrowser.vue',import.meta.url))
const NteGuides=await loadVue(new URL('./NteGuides.vue',import.meta.url))
test('NTE runtime search executes phonetic match and opens a guide for the stable ID on explicit click',async t=>{
  const selected=[]
  const root=mount(t,Nte,{snap:{payload:{schema_version:1,entries:[{id:'1020',name:'哈尼娅'},{id:'1019',name:'薄荷'}]}},onGuide:id=>selected.push(id)})
  nodes(root,'input').find(n=>n.props.type==='search').props.onInput({target:{value:' HNY '}})
  await nextTick()
  assert.equal(nodes(root,'li').filter(n=>n.props.class?.includes('role-card')).length,1)
  nodes(root,'button').find(n=>n.props['aria-label']==='查看哈尼娅攻略').props.onClick()
  await nextTick();assert.equal(nodes(root,'dialog').length,1);assert.match(content(nodes(root,'dialog')[0]),/哈尼娅/)
})
test('Wuwa search has no detail request until explicit role selection and uses canonical ID',async t=>{
  const urls=[]
  t.mock.method(globalThis,'fetch',async url=>{urls.push(url);return {ok:true,json:async()=>({payload:{character_id:'1205',data:{}}})}})
  const root=mount(t,Wuwa,{snap:{payload:[{role_id:'1205',name:'长离'},{role_id:'1508',name:'千咲'}]},accountKey:'a'})
  nodes(root,'input').find(n=>n.props['aria-label']==='搜索角色').props.onInput({target:{value:'CL'}})
  await nextTick();assert.equal(urls.length,0)
  const role=nodes(root,'button').find(n=>n.props.class?.includes('wuwa-role t-item'))
  assert.match(content(role),/长离/)
  await role.props.onClick();await nextTick()
  assert.match(String(urls[0]),/roles\/1205/)
})
test('Wuwa roster defaults to newest first, keeps the level sort as an option, and search ranking still wins',async t=>{
  const roles=[{role_id:'1304',name:'今汐',level:90},{role_id:'9999',name:'未收录角色',level:80},{role_id:'1210',name:'心',level:1},{role_id:'1409',name:'卡提希娅',level:70}]
  const names=root=>nodes(root,'strong').map(content).filter(n=>roles.some(r=>r.name===n))
  const root=mount(t,Wuwa,{snap:{payload:roles},accountKey:'a'})
  assert.deepEqual(names(root),['心','卡提希娅','今汐','未收录角色'])
  assert.match(content(nodes(root,'ul').find(n=>n.props['aria-label']==='排序')),/从新到旧.*等级优先/)
  choose(root,'排序','level');await nextTick()
  assert.deepEqual(names(root),['今汐','未收录角色','卡提希娅','心'])
  choose(root,'排序','newest');await nextTick()
  nodes(root,'input').find(n=>n.props['aria-label']==='搜索角色').props.onInput({target:{value:'今汐'}})
  await nextTick();assert.equal(names(root)[0],'今汐')
  const image=mount(t,Wuwa,{snap:{payload:roles},imageMode:true})
  assert.deepEqual(names(image),['心','卡提希娅','今汐','未收录角色'])
})
test('public guide search requires click and authorized personal links pass the exact form',async t=>{
  const roles=[{role_id:'1408',name:'漂泊者',attribute:'气动'},{role_id:'unknown',name:'漂泊者',attribute:'湮灭'}], selected=[]
  const root=mount(t,Browser,{roles,onRole:role=>selected.push(role)})
  nodes(root,'input').find(n=>n.props.type==='search').props.onInput({target:{value:'风主'}})
  await nextTick()
  assert.equal(nodes(root,'section').filter(n=>n.props['aria-label']==='角色培养攻略').length,0)
  nodes(root,'button').find(n=>n.props['aria-label']==='查看漂泊者·气动攻略').props.onClick();await nextTick()
  nodes(root,'button').find(n=>n.props['aria-label']==='查看本人漂泊者·气动').props.onClick();await nextTick()
  assert.deepEqual(selected,[roles[0]])
})
test('NTE form-specific missing guide remains missing; authorized reverse link uses role ID',async t=>{
  const requests=[],selected=[]
  const catalog={sources:[{id:1,version:'1.3',author:'作者'}],guides:[{id:'哈尼娅',name:'哈尼娅',source_id:1,pages:[1],status:'original_only',sections:[]}]}
  t.mock.method(globalThis,'fetch',async url=>{requests.push(url);return {ok:true,json:async()=>url.endsWith('/guides')?catalog:{images:[]}}})
  const missing=mount(t,NteGuides,{characterId:'1046'})
  await new Promise(setImmediate);await nextTick()
  assert.match(content(missing),/未找到该角色形态/)
  assert.equal(requests.length,1)
  const linked=mount(t,NteGuides,{characterId:'1020',roles:[{id:'1020',name:'哈妮娅'}],onRole:id=>selected.push(id)})
  await new Promise(setImmediate);await nextTick()
  nodes(linked,'button').find(n=>n.props['aria-label']==='查看本人哈尼娅').props.onClick()
  assert.deepEqual(selected,['1020'])
})
