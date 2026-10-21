import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
const Roles=await loadVue(new URL('./WuwaRoles.vue',import.meta.url))
const Render=await loadVue(new URL('./RenderRoot.vue',import.meta.url))
const snap=payload=>({payload,fetched_at:'2026-10-15T04:00:00Z',state:'ok',complete:false,stale:false})
const panel=(game,capability,payload)=>({game,provider:game==='nte'?'tajiduo':game==='endfield'?'skland':'kuro',capability,snapshot:snap(payload)})
const input=panels=>({kind:'game_snapshot',game:'all',as_of:'2026-10-15T04:00:00Z',display_data:{panels,notices:[]}})

test('wuwa image roster is a read-only complete web roster with zero and unknown',t=>{
 const root=mount(t,Roles,{imageMode:true,snap:snap([{role_id:'first',name:'合成首角色',level:0,chain:null},{role_id:'last',name:'合成末角色',level:null,chain:0}])})
 assert.match(content(root),/合成首角色/);assert.match(content(root),/合成末角色/)
 assert.match(content(root),/Lv\.0/);assert.match(content(root),/未知/)
 assert.equal(nodes(root,'input').length,0)
 assert.equal(nodes(root,'button').filter(n=>String(n.props.class).includes('wuwa-role ')).length,0)
 assert.equal(nodes(root,'article').filter(n=>String(n.props.class).includes('wuwa-role ')).length,2)
})

test('wuwa website roster shows rarity as one tag on the picture while the image keeps stars beside the name',t=>{
 const rows=[{role_id:'a',name:'合成五星',level:2,star_level:5},{role_id:'b',name:'合成四星',level:1,star_level:4},{role_id:'c',name:'合成未知',level:0,star_level:null}]
 const tags=root=>nodes(root,'span').filter(n=>n.props.class==='role-rarity'), stars=root=>nodes(root,'span').filter(n=>String(n.props.class).split(' ').includes('stars'))
 const web=mount(t,Roles,{snap:snap(rows)})
 assert.deepEqual(tags(web).map(n=>[content(n),n.props['data-tier'],n.props['aria-label']]),[['★★★★★','top','5 星'],['★★★★',undefined,'4 星'],['未知 星',undefined,'未知 星']])
 assert.ok(tags(web).every(n=>n.parent.props.class==='wuwa-role-art'))
 assert.equal(stars(web).length,0)
 assert.equal(nodes(web,'section')[0].props['data-skin'],'wuwa')
 const image=mount(t,Roles,{imageMode:true,snap:snap(rows)})
 assert.equal(tags(image).length,0);assert.equal(stars(image).length,2);assert.match(content(image),/未知 星/)
 assert.equal(nodes(image,'section')[0].props['data-skin'],undefined)
})

test('dashboard uses actual web capability cards without replacing zero or omitting first and last rows',t=>{
 const root=mount(t,Render,{snapshot:input([
  panel('nte','stamina',{schema_version:1,current:0,maximum:null,city_current:null,city_maximum:100,daily_activity:0,weekly_remaining:null}),
  panel('wuthering_waves','exploration',{country_groups:[{name:'合成首地区',progress:0,areas:[]},{name:'合成末地区',progress:null,areas:[]}]}),
  panel('endfield','roles',{operators:[{id:'a',name:'合成首干员',level:0,potential:null},{id:'z',name:'合成末干员',level:null,potential:0}]})
 ])})
 for(const value of ['本性像素','0','未知','合成首地区','合成末地区','合成首干员','合成末干员'])assert.ok(content(root).includes(value),value)
 assert.equal(nodes(root,'button').filter(n=>/配装|详情/.test(content(n))).length,0)
})

test('notice uses webpage primitives and keeps actionable authorization text',t=>{
 const root=mount(t,Render,{snapshot:{kind:'notice',game:'all',display_data:{title:'账号状态',sections:[{title:'绑定状态',items:['合成首条','授权已过期，请到社区账号重新登录。','合成末条']}],notices:['查询仅使用已有数据。']}}})
 assert.match(content(root),/账号状态.*绑定状态.*合成首条.*重新登录.*合成末条.*已有数据/)
})

test('endfield native roster preserves selected cached loadout',t=>{
 const operator={id:'selected-operator',name:'精确选中干员',level:0,weapon:{name:'实际缓存武器',level:0,refine_level:null},equipment:[{name:'实际装备末条',level:null}],skills:[{name:'实际技能末条',level:0}]}
 const root=mount(t,Render,{snapshot:input([
  panel('endfield','roles',{operators:[operator]})
 ])})
 assert.match(content(root),/精确选中干员.*Lv\. 0/)
 assert.match(content(root),/终末地 角色 干员名.*按精确名称查看单干员配装/)
 assert.doesNotMatch(content(root),/实际缓存武器|实际装备末条|实际技能末条/)
 const detail=mount(t,Render,{snapshot:input([
  panel('endfield','operator_detail',{operators:[operator],operator_detail_id:operator.id,operator_detail:operator})
 ])})
 assert.match(content(detail),/精确选中干员.*实际缓存武器.*等级 LV\. 0.*精炼 未知.*实际装备末条.*等级 LV\. 未知/)
 const skills=nodes(detail,'section').find(node=>node.props['aria-label']==='干员技能')
 assert.ok(skills);assert.match(content(skills),/LV\. 0.*实际技能末条/)
})

test('filtered activity panels keep supplied first and last events without replacing them by full-version content',t=>{
 const root=mount(t,Render,{snapshot:input([panel('nte','events',[{name:'筛选首活动',start_at:'2026-10-14T04:00:00Z',end_at:'2026-10-16T04:00:00Z'},{name:'筛选末活动',start_at:null,end_at:null}])])})
 assert.match(content(root),/筛选首活动/);assert.match(content(root),/筛选末活动/)
 assert.doesNotMatch(content(root),/版本完整活动/)
})

test('panels of retired QQ commands are no longer routed to website components',t=>{
 const news=panel('nte','news',[{title:'下线公告标题',summary:'下线摘要'}]);news.provider='public'
 const root=mount(t,Render,{snapshot:input([news,panel('wuthering_waves','activities',{sections:{one:{title:'下线玩法',progress:0}}})])})
 assert.doesNotMatch(content(root),/下线公告标题|下线摘要|下线玩法/)
 assert.equal(content(root).split('当前数据暂不可用').length-1,2)
})

test('new image capability mounts and toggles stay offline; all challenge branches remain',async t=>{
 let requests=0
 const previous=globalThis.fetch
 globalThis.fetch=async()=>{requests++;throw Error('image mode must not fetch')}
 t.after(()=>{globalThis.fetch=previous})
 const root=mount(t,Render,{snapshot:input([
  panel('wuthering_waves','roles',[{role_id:'a',name:'只读角色',level:0}]),
  panel('wuthering_waves','resources',{current:{kind:'week',period:'合成周期',data:{total_coin:0,total_star:null}}}),
  panel('wuthering_waves','combat',{tower:{state:'ok',data:{difficulty_list:[]}},hologram:{state:'ok',data:{challenge_info:{a:[{boss_name:'合成首领末尾',difficulty:0,boss_level:null}]}}},slash:{state:'ok',data:{difficulty_list:[]}}}),
  panel('endfield','gacha',{schema_version:1,total:0,pools:[{key:'unknown',label:'未知计数卡池',total:null,six_star:null,five_star:0,since_last_six:{status:'unknown'},history:[]}]})
 ])})
 for(const node of nodes(root,'details'))node.props.onToggle?.({target:{open:true},currentTarget:{open:true}})
 for(const node of nodes(root,'article').filter(n=>String(n.props.class).includes('wuwa-role ')))await node.props.onClick?.()
 await new Promise(setImmediate);await nextTick()
 assert.equal(requests,0)
 for(const value of ['合成首领末尾','逆境深塔','战术全息','冥歌海墟','6★ 未知','5★ 0'])assert.ok(content(root).includes(value),value)
 assert.doesNotMatch(content(root),/UID|server_id|role_id|来源补充字段/)
})

test('QQ announcements keep real covers and text while webpage covers remain interactive',async t=>{
 const Announcement=await loadVue(new URL('./AnnouncementList.vue',import.meta.url))
 const cover='https://webstatic.tajiduo.com/bbs/pic/notice-fixture.png'
 const value=snap([{title:'有封面的公告',summary:'完整摘要内容',banner:cover},{title:'没有封面的公告',summary:'保留文字'}])
 const image=mount(t,Announcement,{snap:value,imageMode:true})
 assert.deepEqual(nodes(image,'img').map(n=>n.props.src),[cover])
 assert.equal(nodes(image,'button').length,0)
 assert.match(content(image),/摘要，全文请查看原文。.*有封面的公告.*完整摘要内容.*没有封面的公告.*保留文字/)
 const web=mount(t,Announcement,{snap:value})
 assert.equal(nodes(web,'button').filter(n=>n.props.class==='article-cover').length,1)
 assert.deepEqual(nodes(web,'img').map(n=>n.props.src),[cover])
})
