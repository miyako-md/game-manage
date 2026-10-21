import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
const Reports=await loadVue(new URL('./EndfieldReports.vue',import.meta.url))
const Render=await loadVue(new URL('./RenderRoot.vue',import.meta.url))
const Gacha=await loadVue(new URL('./EndfieldGachaPanel.vue',import.meta.url))
const NteGacha=await loadVue(new URL('./NteCommunityGacha.vue',import.meta.url))
const snap=payload=>({payload,fetched_at:'2026-10-15T04:00:00Z',state:'ok',complete:false,stale:true})
const input=(capability,payload)=>({kind:'game_snapshot',game:'endfield',as_of:'2026-10-15T04:00:00Z',display_data:{panels:[{game:'endfield',provider:'skland',capability,snapshot:snap(payload)}],notices:[]}})
const profile={report:{schema_version:1,overview:{base:{name:'共享管理员',role_id:'100123456',level:0},stamina:{current:0,maximum:null},progress:[{id:'daily',name:'每日业务进度',cur:0,total:100,remaining:100}],todos:[{name:'每日业务进度',remaining:100}]},training:{items:[{id:'first',name:'共享首干员',level:0},{id:'last',name:'共享末干员',level:null}],summary:{listed_count:2}},regions:{items:[{name:'共享首地区'},{name:'共享末地区'}]},ship:{rooms:[{name:'共享首房间',operators:[]},{name:'共享末房间',operators:[]}],summary:{room_count:2}},honor:{available:true,items:[{name:'共享首奖章',level:0},{name:'共享末奖章',level:null}],summary:{listed_count:2}}}}

test('roles image shares the complete web roster overview and directs loadouts to a single operator card',t=>{
 // Template ids count down so the default newest-first order is the source order.
 const items=Array.from({length:35},(_,i)=>({id:`operator-${i}`,char_id:`chr_${String(100-i).padStart(4,"0")}_synthetic`,name:`全配装干员${i}`,level:i===0?0:null,potential:i===0?0:null,evolve_phase:3,rarity:6,profession:'近卫',property:'物理',weapon:{name:'保留详情武器',level:80},equipment:[{slot:'bodyEquip',name:'保留详情护甲',level:70}],skills:[{name:'保留详情技能',level:9}]}))
 const payload={report:{schema_version:1,training:{items,summary:{listed_count:35,declared_count:35}}}}
 for(const root of [mount(t,Reports,{payload,view:'operators'}),mount(t,Render,{snapshot:input('roles',payload)})]) {
  assert.deepEqual(nodes(root,'h3').map(content),items.map(item=>item.name))
  assert.match(content(root),/显示 35 \/ 35 名/)
  assert.match(content(root),/Lv\. 0 潜能 0.*精英阶段 3.*近卫 · 物理/)
  assert.match(content(root),/Lv\. 未知 潜能 未知/)
  assert.doesNotMatch(content(root),/保留详情武器|保留详情技能|保留详情护甲/)
 }
 const image=mount(t,Render,{snapshot:input('roles',payload)})
 assert.match(content(image),/武器、装备、技能与战术道具详情.*终末地 角色 干员名/)
 const detail=mount(t,Render,{snapshot:input('operator_detail',{...payload,operator_detail_id:items[0].id,operator_detail:items[0]})})
 for(const label of ['保留详情武器','保留详情护甲','保留详情技能','LV. 9'])assert.ok(content(detail).includes(label),label)
})

test('web, image component and frozen render root share all Endfield business report branches without image controls',async t=>{
 let requests=0;t.mock.method(globalThis,'fetch',async()=>{requests++;throw Error('must stay offline')})
 for(const [cap,view,tokens] of [['account','overview',['共享管理员','每日业务进度','理智 0 / 未知']],['roles','operators',['共享首干员','共享末干员']],['exploration','regions',['共享首地区','共享末地区']],['ship','ship',['共享首房间','共享末房间']],['honor','honor',['共享首奖章','共享末奖章']]]) {
  const roots=[mount(t,Reports,{payload:profile,view}),mount(t,Reports,{payload:profile,view,imageMode:true}),mount(t,Render,{snapshot:input(cap,profile)})]
  for(const root of roots)for(const token of tokens)assert.ok(content(root).includes(token),`${cap}: ${token}`)
  for(const root of roots.slice(1)) {
   for(const type of ['button','input','select'])assert.equal(nodes(root,type).length,0,`${cap}: ${type}`)
   assert.doesNotMatch(content(root),/UID|100123456|档案来源|观测于|抓取于|同步于|查看换算依据/)
  }
 }
 await nextTick();assert.equal(requests,0)
})

test('frozen Endfield detail and all challenge kinds preserve their independent business data offline',t=>{
 let requests=0;t.mock.method(globalThis,'fetch',async()=>{requests++;throw Error('must stay offline')})
 const detail=mount(t,Render,{snapshot:input('operator_detail',{...profile,operator_detail_id:'last',operator_detail:{name:'共享详情末干员',level:0,weapon:{name:'共享详情武器',level:0}},operator_fetched_at:'2026-10-15T01:00:00Z',operator_stale:true})})
 assert.match(content(detail),/共享详情末干员.*共享详情武器/)
 assert.equal(nodes(detail,'button').length,0)
 const challenge=mount(t,Render,{snapshot:input('combat',{reports:[{schema_version:1,fetched_at:'2026-10-15T01:00:00Z',kind:'war',available:true,summary:{listed_count:1},records:[{name:'共享蚀像末记录',stars:0}]},{schema_version:1,fetched_at:'2026-10-15T02:00:00Z',kind:'monument',available:true,stale:true,summary:{listed_count:1},records:[{name:'共享映像末记录',groups:[]}]},{schema_version:1,fetched_at:'2026-10-15T03:00:00Z',kind:'crisis',available:true,summary:{listed_count:0,highest:0,challenge_count:0},records:[]}]})})
 for(const token of ['战争','丰碑','危机','共享蚀像末记录','共享映像末记录'])assert.ok(content(challenge).includes(token),token)
 assert.equal(nodes(challenge,'button').length,0);assert.equal(requests,0)
 for(const token of ['战争观测时间 2026-10-15 09:00','丰碑观测时间 2026-10-15 10:00','危机观测时间 2026-10-15 11:00','历史最高值 0','挑战次数 0'])assert.ok(content(challenge).includes(token),token)
 assert.equal(nodes(challenge,'span').filter(node=>String(node.props.class).includes('badge-stale')).length,1)
 assert.doesNotMatch(content(challenge),/本次接口返回|没有来源上限|2026-10-15 12:00/)
})

test('all supplied Endfield and NTE pools remain complete and interactive image toggles never fetch',async t=>{
 let requests=0;t.mock.method(globalThis,'fetch',async()=>{requests++;throw Error('must stay offline')})
 const payload={schema_version:1,total:2,pools:[{key:'first',label:'共享首卡池',history:[{name:'首池首条',pulls:0,status:'exact'}]},{key:'last',label:'共享末卡池',history:[{name:'末池末条',pulls:null,status:'unknown'}]}]}
 const root=mount(t,Gacha,{snap:snap(payload),imageMode:true})
 for(const token of ['共享首卡池','首池首条','共享末卡池','末池末条'])assert.ok(content(root).includes(token),token)
 assert.equal(nodes(root,'button').length,0);assert.equal(nodes(root,'select').length,0)
 for(const node of nodes(root,'details'))node.props.onToggle?.({target:{open:true}})
 const nte={schema_version:1,pools:[{name:'异环首卡池',details:[{name:'异环首条',pity:0}]},{name:'异环末卡池',details:[{name:'异环末条',pity:null}]}]}
 const direct=mount(t,NteGacha,{snap:snap(nte),imageMode:true})
 const shared=mount(t,Render,{snapshot:{...input('gacha',nte),game:'nte',display_data:{panels:[{game:'nte',provider:'tajiduo',capability:'gacha',snapshot:snap(nte)}],notices:[]}}})
 for(const value of ['异环首卡池','异环首条','异环末卡池','异环末条'])for(const node of [direct,shared])assert.ok(content(node).includes(value),value)
 await nextTick();assert.equal(requests,0)
})
