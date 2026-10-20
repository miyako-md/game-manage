import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, nodes, content, flushAsyncComponents } from '../test-utils/vue.js'
import { configureHttpClient, setAccountScope, requestJson } from '../http-client.js'
import { favoritesKey, saveFavorites, loadFavorites } from '../nte-roles.js'
const Card = await loadVue(new URL('./CloudGameCard.vue', import.meta.url))
const tick = flushAsyncComponents
const btn = (root,text) => nodes(root,'button').find(n=>content(n)===text)
const account = provider => ({account_id:'a',provider,state:'active',capabilities:['account','roles','realestate','gacha'],roles:[{role_id:'r',display_name:'本人角色'}]})
test('owned mutations allow only exact local tools routes with CSRF',async t=>{
 configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
 const calls=[];t.mock.method(globalThis,'fetch',async(path,options)=>{calls.push([path,options]);return new Response(JSON.stringify(path.endsWith('/csrf')?{csrf_token:'fixture'}:{}))})
 for(const [provider,path,method] of [['kuro','/api/wuwa/gacha/import','POST'],['tajiduo','/api/nte/gacha/preview','POST'],['tajiduo','/api/nte/gacha/import','POST'],['tajiduo','/api/nte/gacha/rules','POST'],['skland','/api/endfield/blueprints','POST'],['skland','/api/endfield/blueprints/1','PUT'],['skland','/api/endfield/blueprints/1','DELETE']]){
  setAccountScope({user_id:'u',account_id:'a',role_id:'r',provider});await requestJson(path,{method,body:{}})
  const [actual,options]=calls.at(-1);assert.equal(actual,`/api/accounts/a/roles/r${path.slice(4)}`);assert.equal(options.headers['X-CSRF-Token'],'fixture')
 }
 for(const [provider,path,method] of [['kuro','/api/wuwa/gacha/remove','POST'],['tajiduo','/api/nte/gacha/admin','POST'],['skland','/api/endfield/skland/attendance','POST'],['skland','/api/endfield/blueprints/export','DELETE']]){
  setAccountScope({user_id:'u',account_id:'a',role_id:'r',provider});const before=calls.length;await assert.rejects(requestJson(path,{method,body:{}}),/云端/);assert.equal(calls.length,before)
 }
})
test('cloud favorites persist by user account and role and reject a shared uid',t=>{
 configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
 const values=new Map(),storage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v)}
 const a={user_id:'A',account_id:'a',role_id:'r'},b={...a,user_id:'B'},r={...a,role_id:'r2'}
 assert.ok(favoritesKey(a));saveFavorites(a,['character'],storage);assert.deepEqual(loadFavorites(a,storage).ids,['character']);assert.deepEqual(loadFavorites(b,storage).ids,[]);assert.deepEqual(loadFavorites(r,storage).ids,[]);assert.equal(favoritesKey('shared-uid'),null)
})
test('NTE restores guides and the original full ledger panel',async t=>{
 const root=mount(t,Card,{account:account('tajiduo'),role:'r',userId:'u'})
 btn(root,'角色').props.onClick();await tick();assert.ok(btn(root,'浏览全部攻略'));btn(root,'抽卡统计').props.onClick();await tick();btn(root,'查看抽卡统计').props.onClick();await tick();assert.match(content(root),/逐抽账本/);assert.doesNotMatch(content(root),/暂未开放/)
})
test('Endfield uses original dashboard without fetching another authorization identity',async t=>{
 configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}));setAccountScope({user_id:'u',account_id:'a',role_id:'r',provider:'hypergryph'})
 const calls=[];t.mock.method(globalThis,'fetch',async path=>{calls.push(path);return new Response(JSON.stringify({}))})
 const root=mount(t,Card,{account:{...account('hypergryph'),capabilities:['account','gacha']},role:'r',userId:'u',snapshots:{account:{account_id:'a',role_id:'r',payload:{nickname:'鹰角本人',role_id:'r'}}}});await tick()
 assert.ok(btn(root,'地图与图鉴'));assert.match(content(root),/鹰角本人/);assert.ok(calls.every(p=>!p.includes('/skland/')));assert.doesNotMatch(content(root),/填写 cred/)
})
test('NTE residence names and name search use selected role mapping',async t=>{
 const root=mount(t,Card,{account:account('tajiduo'),role:'r',userId:'u',snapshots:{roles:{payload:{schema_version:1,entries:[{id:'1019',name:'合成住户'}]}},realestate:{payload:{schema_version:1,entries:[{id:'h',name:'合成房产',owned:true,resident_ids:['1019']}]}}}})
 btn(root,'房产、载具与探索').props.onClick();await tick();btn(root,'查看房产详情').props.onClick();await tick()
 assert.match(content(root),/合成住户/)
 const search=nodes(root,'input').find(n=>n.props['aria-label']==='搜索房产');search.props.onInput({target:{value:'合成住户'}});await tick();assert.match(content(root),/合成房产/)
})
test('NTE full ledger preview and import stay in the current owner scope',async t=>{
 configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}));setAccountScope({user_id:'u',account_id:'a',role_id:'r',provider:'tajiduo'})
 const calls=[];t.mock.method(globalThis,'fetch',async(path,options)=>{calls.push([path,options]);return new Response(JSON.stringify(path.endsWith('/csrf')?{csrf_token:'fixture'}:path.endsWith('/preview')?{preview_id:'ticket',record_count:1,new_records:1,duplicates:0,warnings:[],missing_requirements:[]}:path.endsWith('/import')?{imported:1,duplicates:0}:path.endsWith('/summary')?{total_records:0,pools:[]}:path.endsWith('/rules')?{rules:[]}:{records:[],total:0}))})
 const root=mount(t,Card,{account:account('tajiduo'),role:'r',userId:'u'});btn(root,'抽卡统计').props.onClick();await tick();btn(root,'查看抽卡统计').props.onClick();await tick()
 const disclosure=nodes(root,'details').find(n=>content(n).includes('本人逐抽账本'));disclosure.props.onToggle({target:{open:true}});await tick()
 await nodes(root,'input').find(n=>n.props.type==='file').props.onChange({target:{files:[{name:'fixture.json',size:30,text:async()=>'{"format":"synthetic"}'}]}});await tick()
 await btn(root,'校验并预览').props.onClick();await tick();assert.match(content(root),/新增 1/)
 await btn(root,'确认导入到当前账号').props.onClick();await tick();assert.match(content(root),/导入完成/)
 const write=calls.find(([path])=>path.endsWith('/import'));assert.equal(write[0],'/api/accounts/a/roles/r/nte/gacha/import');assert.equal(JSON.parse(write[1].body).preview_id,'ticket');assert.equal(write[1].headers['X-CSRF-Token'],'fixture')
})
test('Endfield blueprint create edit delete and export use only the selected Skland identity',async t=>{
 const Dashboard=await loadVue(new URL('./EndfieldDashboard.vue',import.meta.url))
 configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}));setAccountScope({user_id:'u',account_id:'a',role_id:'r',provider:'skland'})
 const calls=[];let items=[],downloaded=false
 const oldDocument=globalThis.document,oldDocumentType=globalThis.Document,oldShadowRoot=globalThis.ShadowRoot;globalThis.Document=class Document{};globalThis.ShadowRoot=class ShadowRoot{};globalThis.document={createElement:()=>({click(){downloaded=true}})};t.after(()=>{globalThis.document=oldDocument;globalThis.Document=oldDocumentType;globalThis.ShadowRoot=oldShadowRoot})
 t.mock.method(globalThis,'fetch',async(path,options)=>{calls.push([path,options]);const body=options.body&&JSON.parse(options.body);if(options.method==='POST'&&path.endsWith('/blueprints'))items=[{id:1,...body}];if(options.method==='PUT')items=[{id:1,...body}];if(options.method==='DELETE')items=[];return new Response(JSON.stringify(path.endsWith('/csrf')?{csrf_token:'fixture'}:{items}))})
 const root=mount(t,Dashboard,{cloudAccount:account('skland'),cloudRole:'r',initialSection:'blueprints'});await tick()
 const fields=nodes(root,'input');fields[0].props['onUpdate:modelValue']('蓝图甲');fields[1].props['onUpdate:modelValue']('synthetic');await nodes(root,'form')[0].props.onSubmit({preventDefault(){}});await tick();assert.match(content(root),/蓝图甲/)
 btn(root,'编辑').props.onClick();await tick();nodes(root,'input')[0].props['onUpdate:modelValue']('蓝图乙');await nodes(root,'form')[0].props.onSubmit({preventDefault(){}});await tick();assert.match(content(root),/蓝图乙/)
 await btn(root,'导出备份').props.onClick();assert.equal(downloaded,true)
 await btn(root,'删除').props.onClick();await tick();assert.match(content(root),/还没有收藏蓝图/)
 for(const [path,options] of calls.filter(([p])=>!p.endsWith('/csrf'))){assert.ok(path.startsWith('/api/accounts/a/roles/r/endfield/blueprints'));if(options.method!=='GET')assert.equal(options.headers['X-CSRF-Token'],'fixture')}
})
test('public tools read routes are independent of selected private provider and management is explicit',async t=>{
 configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}));setAccountScope({user_id:'u',account_id:'a',role_id:'r',provider:'hypergryph'})
 const calls=[];t.mock.method(globalThis,'fetch',async(path,options)=>{calls.push([path,options]);return new Response(JSON.stringify(path.endsWith('/csrf')?{csrf_token:'fixture'}:{}))})
 for(const path of ['/api/nte/guides','/api/nte/guides/sources/fixture','/api/wuwa/guides/updates?name=fixture','/api/endfield/map?map_id=fixture','/api/endfield/map/marks/fixture?map_id=fixture']){await requestJson(path);assert.equal(calls.at(-1)[0],'/api/public/'+path.slice(5))}
 await requestJson('/api/nte/guides/sources/fixture/refresh',{method:'POST'});assert.equal(calls.at(-1)[0],'/api/admin/nte/guides/sources/fixture/refresh');assert.equal(calls.at(-1)[1].headers['X-CSRF-Token'],'fixture')
 for(const path of ['/api/nte/guides/admin','/api/endfield/map/write','/api/wuwa/guides/updates/remove'])await assert.rejects(requestJson(path,{method:'POST'}),/云端/)
})
