import test from 'node:test'
import assert from 'node:assert/strict'
import { h, nextTick, provide } from 'vue'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
import { configureHttpClient, setAccountScope } from '../http-client.js'
import { createQqRenderContext, QQ_RENDER_CONTEXT } from '../qq-render-context.js'
import { selectOverviewAccount, cloudOverviewView } from '../cloud-view-model.js'

const App = await loadVue(new URL('../QqRenderApp.vue', import.meta.url))
const CloudCard = await loadVue(new URL('./CloudGameCard.vue', import.meta.url))
const Overview = await loadVue(new URL('./OverviewPage.vue', import.meta.url))
const now = Date.parse('2026-10-15T04:00:00Z')
const snap = payload => ({ payload, state:'ok', fetched_at:'2026-10-15T03:00:00Z' })
const account = (game, provider, capabilities) => ({ account_id:'a', game, provider, state:'active', capabilities, roles:[{role_id:'private-role',display_name:'本人角色',is_default:true}] })
const inputFor = (game, provider, command, snapshots, extra={}) => ({version:1,command,game,roleName:null,now,entries:[{account:account(game,provider,Object.keys(snapshots)),role:'private-role',snapshots}],publicSnapshots:{},...extra})
const tick = async () => { await nextTick(); await new Promise(resolve=>setImmediate(resolve)); await nextTick() }
function capture(t, input) {
  configureHttpClient({mode:'cloud'})
  t.after(()=>configureHttpClient({mode:'local'}))
  const row=input.entries[0]
  if(row) setAccountScope({user_id:'qq-render',account_id:row.account.account_id,role_id:row.role,provider:row.account.provider})
  const context=createQqRenderContext(input)
  const root=mount(t,{setup(){provide(QQ_RENDER_CONTEXT,context);return()=>h(App,{input})}},{})
  return {root,async settled(){await tick();await context.settled();await tick()}}
}
const classes = (root,name) => nodes(root,'section').filter(node=>String(node.props.class).includes(name))

test('QQ overview uses the website cards and its Skland owner preference',t=>{
  const eagle=account('endfield','hypergryph',['account','gacha']),skland={...account('endfield','skland',['account']),account_id:'b'}
  assert.equal(selectOverviewAccount([eagle,skland]),skland)
  const {root}=capture(t,{version:1,command:'overview',game:null,now,entries:[{account:eagle,role:'private-role',snapshots:{account:snap({schema_version:1,nickname:'鹰角账号'})}},{account:skland,role:'private-role',snapshots:{account:snap({base:{name:'森空岛账号',level:0},stamina:{current:0,maximum:240}})}}],publicSnapshots:{}})
  const cards=nodes(root,'button').filter(node=>String(node.props.class).includes('game-summary'))
  assert.equal(cards.length,1)
  assert.match(content(cards[0]),/森空岛账号/)
  assert.doesNotMatch(content(cards[0]),/鹰角账号/)
  assert.match(content(cards[0]),/0 \/ 240/)
})

test('QQ redacted failures and website raw failures keep the same overview card state',t=>{
  const original={state:'source_error',payload:{schema_version:1,nickname:'旧数据',level:0},error:'已知安全来源说明'}
  const owner=account('nte','tajiduo',['account'])
  const websiteView=cloudOverviewView({accounts:[owner],snapshotsByAccount:{a:{account:original}}})
  const website=mount(t,Overview,{games:websiteView.games,snapshots:websiteView.snapshots,accounts:websiteView.accounts,collection:websiteView.collection,readErrors:websiteView.readErrors,now})
  const {root}=capture(t,{version:1,command:'overview',game:null,now,entries:[{account:owner,role:'private-role',snapshots:{account:{...original,error:undefined}}}],publicSnapshots:{}})
  const labels=tree=>nodes(tree,'span').filter(node=>String(node.props.class).includes('summary-state')).map(content)
  assert.deepEqual(labels(root),labels(website))
  assert.deepEqual(labels(root),['读取异常'])
  assert.match(content(root),/来源读取异常/)
  assert.doesNotMatch(content(root),/已知安全来源说明/)
})

test('QQ NTE roles expands the original full list and details without a dialog or identity fields',t=>{
  const entries=Array.from({length:13},(_,i)=>({id:String(i),name:`角色${i}`,level:i,weapon:{name:`弧盘${i}`,level:0}}))
  const {root}=capture(t,inputFor('nte','tajiduo','roles',{roles:snap({schema_version:1,entries})}))
  assert.equal(classes(root,'nte-roles-panel').length,1)
  assert.equal(nodes(root,'details').filter(node=>node.props.class==='role-more').length,13)
  assert.ok(nodes(root,'details').filter(node=>node.props.class==='role-more').every(node=>node.props.open))
  assert.match(content(root),/角色12/)
  assert.match(content(root),/弧盘12/)
  assert.doesNotMatch(content(root),/仅收藏|角色对比|已选 0 \/ 4/)
  assert.doesNotMatch(content(root),/项尚未采集|采集状态/)
  assert.match(content(root),/角色总数 13/)
  assert.equal(nodes(root,'dialog').length,0)
  assert.doesNotMatch(content(root),/private-role/)
})

test('QQ NTE summary keeps the normal cloud wrapper and its default summary content',t=>{
  const input=inputFor('nte','tajiduo','summary',{account:snap({schema_version:1,nickname:'唯一账号名',level:70,tycoon_level:30,achievement_count:0,achievement_total:300}),stamina:snap({schema_version:1,current:120,maximum:240,city_current:40,city_maximum:100,daily_activity:80,weekly_remaining:0})})
  const website=mount(t,CloudCard,{account:input.entries[0].account,role:input.entries[0].role,snapshots:input.entries[0].snapshots})
  const {root}=capture(t,input)
  const summaryTiles=tree=>nodes(tree,'div').filter(node=>String(node.props.class).includes('summary-metric') && !String(node.props.class).includes('summary-metrics')).map(content)
  assert.deepEqual(summaryTiles(root),summaryTiles(website))
  assert.equal(summaryTiles(root).length,6)
  assert.equal(classes(root,'nte-card').length,0)
  assert.equal(classes(website,'nte-card').length,0)
  assert.match(content(root),/周本剩余 · 0/)
  assert.doesNotMatch(content(root),/大亨等级/)
})

test('QQ Wuwa summary keeps the normal cloud profile previews without opening details',t=>{
  const input=inputFor('wuthering_waves','kuro','summary',{
    account:snap({nickname:'本人档案',level:70,extra:{role_id:'private-role',server_id:'server',profile:{world_level:0,achievement_count:0}}}),
    stamina:snap({current:0,maximum:240}),progress:snap([{name:'周期事项',cur:0,total:10}]),
    exploration:snap({detections:{total:0},country_groups:[{name:'合成地区',progress:0}]}),calabash:snap({level:0}),
  })
  const website=mount(t,CloudCard,{account:input.entries[0].account,role:input.entries[0].role,snapshots:input.entries[0].snapshots})
  const {root}=capture(t,input)
  const metrics=tree=>nodes(tree,'div').filter(node=>String(node.props.class).includes('summary-metric') && !String(node.props.class).includes('summary-metrics')).map(content)
  assert.deepEqual(metrics(root),metrics(website))
  assert.ok(metrics(root).some(text=>text.includes('世界等级 0')))
  assert.ok(metrics(root).some(text=>text.includes('已收录残象 0')))
  assert.ok(!nodes(root,'h2').some(node=>node.props.class==='wuwa-name'))
  assert.equal(nodes(root,'dialog').length,0)
})

test('QQ named NTE role filters exactly and keeps real zero values',t=>{
  const {root}=capture(t,inputFor('nte','tajiduo','roles',{roles:snap({schema_version:1,entries:[{id:'1',name:'目标',level:0},{id:'2',name:'目标之外',level:10}]})},{roleName:'目标'}))
  assert.match(content(root),/目标/)
  assert.doesNotMatch(content(root),/目标之外/)
  assert.equal(nodes(root,'li').filter(node=>String(node.props.class).includes('role-card')).length,1)
})

test('QQ NTE gacha renders every original pool history and cached ledger GETs only',async t=>{
  const calls=[]
  t.mock.method(globalThis,'fetch',async(path,options)=>{calls.push([path,options]);return new Response(JSON.stringify({detail:'尚无账本缓存'}),{status:404})})
  const pools=[{name:'卡池甲',total_draws:0,s_count:1,guarantee:90,details:[{item_id:'a',name:'奖励甲',pity:0}]},{name:'卡池乙',total_draws:10,s_count:1,guarantee:80,details:[{item_id:'b',name:'奖励乙',pity:10}]}]
  const {root,settled}=capture(t,inputFor('nte','tajiduo','gacha',{gacha:snap({schema_version:1,pools})}))
  await settled()
  assert.equal(classes(root,'history-panel').length,2)
  assert.match(content(root),/奖励甲/)
  assert.match(content(root),/奖励乙/)
  assert.match(content(root),/尚无账本缓存/)
  assert.ok(calls.length>0)
  assert.ok(calls.every(([path,options])=>path.startsWith('/api/accounts/a/roles/private-role/nte/gacha/') && options.method==='GET'))
})

test('QQ named Wuwa role uses the original detail component and frozen scoped GET',async t=>{
  const calls=[]
  t.mock.method(globalThis,'fetch',async(path,options)=>{calls.push([path,options]);return new Response(JSON.stringify({state:'ok',payload:{character_id:'1',data:{role:{role_name:'目标'},weapon_data:{weapon:{weapon_name:'冻结武器'},level:0}}}}))})
  const {root,settled}=capture(t,inputFor('wuthering_waves','kuro','roles',{account:snap({nickname:'本人',extra:{role_id:'private-role',server_id:'server'}}),roles:snap([{role_id:'1',name:'目标',level:0},{role_id:'2',name:'其他角色',level:1}])},{roleName:'目标'}))
  await settled()
  assert.ok(nodes(root,'div').some(node=>node.props.class==='wuwa-role-detail'))
  assert.match(content(root),/冻结武器/)
  assert.doesNotMatch(content(root),/其他角色/)
  assert.equal(nodes(root,'dialog').length,0)
  assert.equal(calls[0][0],'/api/accounts/a/roles/private-role/wuwa/roles/1')
  assert.ok(calls.every(([,options])=>options.method==='GET'))
})

test('QQ CalendarPage uses frozen time and the website rolling range',t=>{
  const events=[{name:'冻结进行中',start_at:'2026-10-14T00:00:00+08:00',end_at:'2026-10-16T00:00:00+08:00'},{name:'远期超出滚动范围',start_at:'2026-12-01T00:00:00+08:00',end_at:'2026-12-02T00:00:00+08:00'}]
  const {root}=capture(t,{version:1,command:'calendar',game:'nte',now,entries:[],publicSnapshots:{nte:{events:snap(events)}}})
  assert.match(content(root),/10-12 — 11-10/)
  assert.match(content(root),/冻结进行中/)
  assert.doesNotMatch(content(root),/远期超出滚动范围/)
})

test('QQ progress reset labels use the same frozen clock as the calendar',t=>{
  const {root}=capture(t,inputFor('wuthering_waves','kuro','progress',{progress:snap([{name:'冻结周期',cur:0,total:10,refresh_at:'2000-01-02T12:00:00+08:00'}])},{now:Date.parse('2000-01-01T12:00:00+08:00')}))
  assert.match(content(root),/明日重置/)
  assert.doesNotMatch(content(root),/已可重置/)
})

test('QQ recent activities keep imprecise dates below the original timeline and expand phases',t=>{
  const events=[{name:'不确定活动',start_at:'2026-12-01',start_precision:'day',end_precision:'unknown',end_text:'后续通知'},{name:'分阶段活动',phases:[{start_at:'2026-10-14T00:00:00+08:00',end_at:'2026-10-16T00:00:00+08:00'},{start_at:'2026-10-18T00:00:00+08:00',end_at:'2026-10-19T00:00:00+08:00'}]}]
  const {root}=capture(t,{version:1,command:'recent_events',game:'nte',now,entries:[],publicSnapshots:{nte:{events:snap(events)}}})
  const unplaced=nodes(root,'button').filter(node=>node.props.class==='unplaced-event')
  assert.equal(unplaced.length,1)
  assert.match(content(unplaced[0]),/不确定活动/)
  assert.match(content(unplaced[0]),/2026-12-01 · 时刻未确认/)
  assert.match(content(unplaced[0]),/后续通知/)
  assert.match(content(root),/分阶段活动 · 阶段 1/)
  assert.match(content(root),/分阶段活动 · 阶段 2/)
  assert.equal(nodes(root,'button').filter(node=>String(node.props.class).includes('timeline-event')).length,2)
})

test('QQ named Endfield operator reads the original scoped equipment view',async t=>{
  const operators=[{id:'one',name:'目标干员',level:0},{id:'two',name:'别的干员',level:10}]
  const card={base:{name:'本人',level:0},operators,regions:[],ship:[]}
  const calls=[]
  t.mock.method(globalThis,'fetch',async(path,options)=>{
    calls.push([path,options])
    return new Response(JSON.stringify(path.endsWith('/operators/one') ? {operator:{weapon:{name:'冻结鹰角武器',level:0},equipment:[],skills:[]}} : {payload:card}))
  })
  const {root,settled}=capture(t,inputFor('endfield','skland','roles',{account:snap(card)},{roleName:'目标干员'}))
  await settled()
  assert.match(content(root),/目标干员/)
  assert.match(content(root),/冻结鹰角武器/)
  assert.doesNotMatch(content(root),/别的干员|private-role/)
  assert.ok(calls.some(([path])=>path==='/api/accounts/a/roles/private-role/endfield/skland/operators/one'))
  assert.ok(calls.every(([,options])=>options.method==='GET'))
})

test('QQ Wuwa detail cache miss keeps the original missing-data message',async t=>{
  t.mock.method(globalThis,'fetch',async()=>new Response('{}',{status:404}))
  const {root,settled}=capture(t,inputFor('wuthering_waves','kuro','roles',{account:snap({nickname:'本人',extra:{role_id:'private-role',server_id:'server'}}),roles:snap([{role_id:'1',name:'目标',level:0}])},{roleName:'目标'}))
  await settled()
  assert.match(content(root),/当前账号没有这项数据/)
  assert.ok(!nodes(root,'div').some(node=>node.props.class==='wuwa-role-detail'))
})

test('QQ Endfield records are explicitly the original first page, never a fabricated full history',async t=>{
  const calls=[]
  t.mock.method(globalThis,'fetch',async(path,options)=>{calls.push([path,options]);return new Response(JSON.stringify({records:[{pool_key:'pool',seq_id:'1',name:'冻结寻访记录',rarity:6,gacha_ts:now}],total:70}))})
  const {root,settled}=capture(t,inputFor('endfield','hypergryph','gacha',{account:snap({schema_version:1,nickname:'本人'}),gacha:snap({schema_version:1,pools:[],total:70})}))
  await settled()
  assert.match(content(root),/冻结寻访记录/)
  assert.match(content(root),/1–50 \/ 70/)
  assert.ok(nodes(root,'details').some(node=>String(node.props.class).includes('record-list') && node.props.open))
  assert.equal(calls[0][0],'/api/accounts/a/roles/private-role/endfield/gacha/records?pool_key=&offset=0&limit=50')
  assert.ok(calls.every(([,options])=>options.method==='GET'))
})

test('ordinary website module still keeps its existing details behind its button',t=>{
  const input=inputFor('nte','tajiduo','roles',{roles:snap({schema_version:1,entries:[{id:'1',name:'网站角色'}]})})
  const root=mount(t,App,{input})
  assert.equal(classes(root,'nte-roles-panel').length,0)
  assert.equal(nodes(root,'dialog').length,0)
})
