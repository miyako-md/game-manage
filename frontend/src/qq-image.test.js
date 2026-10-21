import test from 'node:test'
import {readFileSync} from 'node:fs'
import assert from 'node:assert/strict'
import {imageCalendarWindows} from './qq-image/image-calendar.js'
import {guideAtoms,guideLines} from './qq-image/guide-presentation.js'
import {configure,viewModel} from './qq-image/models.js'
import {prepareReuse} from './qq-image/reuse-model.js'
import {schemes} from './qq-image/designs.js'
import {upcomingSections,windowEndpoint} from './qq-image/upcoming.js'
import {loadVue,mount,nodes,content} from './test-utils/vue.js'

const CloudCalendar=await loadVue(new URL('./qq-image/CloudCalendar.vue',import.meta.url))

test('selected image layout only has A; 活动 windows are exactly fourteen Beijing days',()=>{
 assert.deepEqual(schemes.map(s=>s.id),['dossier'])
 const events=[{name:'长活动',start_at:'2026-08-01T10:00:00+08:00',end_at:'2027-03-01T10:00:00+08:00'}]
 for(const iso of ['2026-10-18T16:30:00+08:00','2026-11-01T00:01:00+08:00','2027-01-01T23:59:00+08:00']){
  const now=Date.parse(iso),windows=imageCalendarWindows(events,now)
  assert.equal(windows.length,1);assert.equal(windows[0].range.days.length,14)
  assert.equal(windows[0].range.end-windows[0].range.start,14*86400000)
  assert.equal(new Date(windows[0].range.days[2].timestamp+8*3600000).toISOString().slice(0,10),iso.slice(0,10))
 }
})

test('日历 windows span every dated activity of the version and fall back to fourteen days without dates',()=>{
 const now=Date.parse('2026-10-21T12:00:00+08:00')
 const events=[{name:'版本首日',start_date:'2026-09-30',start_precision:'relative',end_at:'2026-10-22T09:59:00+08:00'},
  {name:'版本末尾',start_at:'2026-10-29T04:00:00+08:00',end_at:'2026-11-11T03:59:00+08:00'}]
 const [full]=imageCalendarWindows(events,now,true)
 assert.equal(full.range.days.length,43);assert.equal(full.label,'2026-09-30 至 2026-11-11')
 assert.equal(imageCalendarWindows([{name:'未公布'}],now,true)[0].range.days.length,14)
})

const calendarInput=(payload,version)=>({command:'日历',snapshot:{kind:'calendar',game:'all',as_of:'2026-10-21T12:00:00+08:00',
 display_data:{games:[{game_id:'nte',display_name:'异环'}],snapshots:{nte:{events:{payload,...(version?{version}:{})}}}}}})
test('QQ 日历 uses the whole version when it is known and says when it shows fourteen days instead',()=>{
 configure([],{})
 const rows=[{name:'活动',start_at:'2026-10-01T10:00:00+08:00',end_at:'2026-11-20T10:00:00+08:00'}]
 const known=viewModel(calendarInput(rows,'1.4')).panels[0]
 assert.equal(known.type,'cloud_calendar');assert.equal(known.full,true);assert.match(known.caption,/完整排期/)
 const unknown=viewModel(calendarInput(rows)).panels[0]
 assert.equal(unknown.full,false);assert.match(unknown.caption,/未提供版本信息.*近 14 天/)
})

test('QQ activity calendars use the compact image mode of the shared timeline without artwork',t=>{
 const asOf=Date.parse('2026-10-21T12:00:00+08:00')
 const events=[{id:'a',gameId:'nte',gameName:'异环',name:'带配图活动',category:'限时活动',banner:'https://example.com/a.jpg',start_at:'2026-10-01T10:00:00+08:00',end_at:'2026-11-20T10:00:00+08:00'},
  {id:'b',gameId:'nte',gameName:'异环',name:'时间未公布',category:'限时活动'}]
 const snapshots={nte:{news:{payload:[{id:'p',images:['https://example.com/a.jpg']}]}}}
 for(const full of [false,true]){
  const root=mount(t,CloudCalendar,{events,snapshots,asOf,full})
  assert.ok(nodes(root,'div').some(n=>n.props.class?.includes('image-mode')))
  assert.ok(!nodes(root,'img').some(n=>n.props.src?.startsWith('https://example.com/')))
  assert.equal(nodes(root,'button').length,0)
  const bar=nodes(root,'article').find(n=>n.props.class?.includes('timeline-event'))
  assert.match(content(bar),/带配图活动.*限时活动.*进行中.*剩 30 天/)
  assert.match(content(root),full?/版本活动时间轴/:/14 天时间轴/)
  assert.match(content(root),/待确认的时间.*时间未公布/)
  assert.equal(nodes(root,'div').filter(n=>n.props.class?.split(' ').includes('date-cell')).length,full?51:14)
 }
})

test('近期活动 lists starts and ends within [now, now+72h] with Beijing day precision and inclusive boundaries',()=>{
 const now=Date.parse('2026-10-21T12:00:00+08:00'),h=3600000,iso=ms=>new Date(ms).toISOString()
 const rows=[{name:'此刻开始',start_at:iso(now),end_at:iso(now+10*24*h)},
  {name:'边界开始',start_at:iso(now+72*h),end_at:iso(now+90*24*h)},
  {name:'边界外开始',start_at:iso(now+72*h+1000)},
  {name:'刚刚开始',start_at:iso(now-1000),end_at:iso(now+30*24*h)},
  {name:'窗口内起止',start_at:'2026-10-21T15:00:00+08:00',end_at:'2026-10-22T14:30:00+08:00'},
  {name:'日期结束',start_date:'2026-10-01',start_precision:'day',end_date:'2026-10-23',end_precision:'day'},
  {name:'日期次日结束',end_date:'2026-10-24',end_precision:'day'},
  {name:'日期开始',start_at:'2026-10-22',start_precision:'day',end_at:'2026-11-30',end_precision:'day'},
  {name:'相对开始',start_date:'2026-10-22',start_precision:'relative',start_text:'更新后',end_at:'2026-12-01T10:00:00+08:00'},
  {name:'早已相对开始',start_date:'2026-09-30',start_precision:'relative',end_at:'2026-12-01T10:00:00+08:00'},
  {name:'未知',start_precision:'unknown',end_precision:'unknown'},
  {name:'已结束未知开始',start_precision:'unknown',end_at:iso(now-h)}]
 assert.equal(windowEndpoint(rows[5],'end'),Date.parse('2026-10-23T23:59:59+08:00'))
 assert.equal(windowEndpoint(rows[6],'end'),Date.parse('2026-10-24T23:59:59+08:00'),'beyond now+72h, so not listed')
 assert.equal(windowEndpoint(rows[7],'start'),Date.parse('2026-10-22T00:00:00+08:00'))
 const {starting,ending,pending}=upcomingSections(rows,now)
 assert.deepEqual(starting.map(e=>e.name),['此刻开始','窗口内起止','日期开始','边界开始'])
 assert.deepEqual(ending.map(e=>e.name),['窗口内起止','日期结束'])
 assert.equal(pending,2)
 const by=(list,name)=>list.find(e=>e.name===name)
 assert.equal(by(starting,'此刻开始').countdown,'即将开始')
 assert.equal(by(starting,'窗口内起止').time,'10-21 周三 15:00');assert.equal(by(starting,'窗口内起止').countdown,'3 小时后开始')
 assert.equal(by(ending,'窗口内起止').countdown,'还剩 1 天 2 小时')
 assert.equal(by(starting,'日期开始').time,'10-22 周四 当天');assert.equal(by(starting,'日期开始').countdown,'明天开始')
 assert.equal(by(ending,'日期结束').time,'10-23 周五 当天');assert.equal(by(ending,'日期结束').countdown,'后天结束')
 assert.equal(by(starting,'边界开始').countdown,'3 天后开始')
})

const recentInput=(game,panels)=>({command:'近期活动',snapshot:{kind:'game_snapshot',game,as_of:'2026-10-21T12:00:00+08:00',title:'近期活动 · 未来 72 小时',
 display_data:{panels:panels.map(([id,payload])=>({game:id,provider:'public',capability:'recent_events',snapshot:{payload}}))}}})
test('近期活动 renders two list panels, tags games only when several are shown, and states an empty window',t=>{
 configure([],{})
 const soon=[{name:'即将开始',category:'限时活动',start_at:'2026-10-22T10:00:00+08:00',end_at:'2026-11-22T10:00:00+08:00'},{name:'时间未知',start_precision:'unknown',end_precision:'unknown'}]
 const ending=[{name:'即将结束',category:'签到活动',start_at:'2026-10-01T10:00:00+08:00',end_at:'2026-10-22T09:59:00+08:00'}]
 const all=viewModel(recentInput('all',[['nte',soon],['wuthering_waves',ending]]))
 assert.deepEqual(all.panels.map(p=>[p.type,p.title,p.rows.length]),[['upcoming','72 小时内开始',1],['upcoming','72 小时内结束',1]])
 assert.deepEqual([all.panels[0].rows[0].game,all.panels[1].rows[0].game],['异环','鸣潮'])
 assert.equal(all.panels[1].note,'另有 1 项时间待确认')
 const single=viewModel(recentInput('nte',[['nte',soon]]))
 assert.equal(single.panels[0].rows[0].game,'');assert.equal(single.panels[1].empty,'未来 72 小时内没有结束的活动')
 const empty=viewModel(recentInput('nte',[['nte',[]]]))
 assert.deepEqual(empty.panels.map(p=>[p.type,p.rows.length,p.empty]),[['upcoming',0,'未来 72 小时内没有开始或结束的活动']])
})
test('guide presentation keeps every original character and punctuation attached to its entity',()=>{
 const tokens=[{text:'优先'},{text:'技能',entity:true},{text:'。其余稍后。'}],out=guideAtoms(tokens)
 assert.equal(out.map(t=>t.text+(t.trailing||'')).join(''),'优先技能。其余稍后。')
 assert.equal(out[1].trailing,'。')
 assert.equal(guideLines({sectionKey:'teams',text:'甲／乙；丙／丁。'}).join(''),'甲／乙；丙／丁。')
})
test('role details need no image-only description stripping; the input stays intact',()=>{
 const source={snapshot:{kind:'nte_role',display_data:{snapshot:{payload:{entries:[{skills:[{name:'战技',level:0,items:[{desc:'长段说明'}]}],city_skills:[{name:'城区技',level:1,items:[{desc:'说明'}]}]}]}}}}}
 const before=JSON.stringify(source)
 assert.deepEqual(prepareReuse(source),source.snapshot);assert.equal(JSON.stringify(source),before)
})

test('partial challenge modules remain renderable',()=>{
 const input={snapshot:{kind:'game_snapshot',display_data:{panels:[
  {game:'wuthering_waves',capability:'combat',snapshot:{payload:{hologram:{state:'unavailable'},slash:{state:'unavailable'}}}}
 ]}}}
 assert.doesNotThrow(()=>prepareReuse(input))
})
test('persistent browser configuration clears previous account context between renders',()=>{
 const input={command:'终末地 攻略',snapshot:{kind:'notice',game:'endfield',as_of:'2026-10-18T00:00:00+08:00',display_data:{sections:[]}}}
 configure([{snapshot:{kind:'game_snapshot',display_data:{panels:[{game:'endfield',snapshot:{payload:{report:{training:{items:[{name:'私人角色示例',avatar_url:'https://bbs.hycdn.cn/private.png'}]}}}}}]}}}],{})
 assert.equal(viewModel(input).panels[0].role.name,'私人角色示例')
 configure([],{});assert.notEqual(viewModel(input).panels[0].role?.name,'私人角色示例')
})
test('guide sources without a version say so instead of printing VNone',()=>{
 configure([],{})
 const guide={id:'1507',name:'示例角色',sources:[{id:'1',title:'甲',author:'作者甲',version:'3.2',url:'u1'},{id:'2',title:'乙',author:'作者乙',version:null,url:'u2'}],sections:[]}
 const model=viewModel({command:'鸣潮 攻略 示例角色',snapshot:{kind:'guide',game:'wuthering_waves',as_of:'2026-10-18T00:00:00+08:00',display_data:{guide}}})
 assert.ok(model.hero.meta.includes('V3.2 / 版本未确认'))
 const lines=model.panels.at(-1).lines.map(l=>l.text)
 assert.match(lines[0],/V3\.2/);assert.match(lines[1],/版本未确认/)
 assert.doesNotMatch(JSON.stringify(model),/VNone|Vnull|Vundefined/)
})
test('a bare guide reply is a plain notice, not an index image',()=>{
 const input={command:'鸣潮 攻略',snapshot:{kind:'notice',game:'wuthering_waves',as_of:'2026-10-18T00:00:00+08:00',display_data:{title:'鸣潮 角色攻略',sections:[],notices:['请发送「鸣潮 攻略 角色名」查看单个角色攻略；可用角色见网站攻略页。']}}}
 const model=viewModel(input)
 assert.deepEqual(model.panels.map(p=>p.type),['text'])
 assert.match(model.panels[0].text,/鸣潮 攻略 角色名.*网站攻略页/)
})

test('QQ skins: the sheet and each overview game block carry data-skin, and skinned images start from dark tokens',t=>{
 const read=name=>readFileSync(new URL('./qq-image/'+name,import.meta.url),'utf8')
 assert.match(read('LabRoot.vue'),/skinOf\(props\.input\?\.snapshot\?\.game\)\|\|\(isAccountOverview\.value\?'wuwa':null\)/)
 assert.match(read('LabRoot.vue'),/:data-skin="skin"/)
 assert.match(read('mount.js'),/dataset\.theme=skinOf\(snapshot\.game\)\?'dark':'light'/)
 assert.match(read('mount.js'),/import '\.\/reuse\.css'[\s\S]*import '\.\/skin\.css'/)
 assert.match(read('mount.js'),/import '\.\/skin\.css'\s+import '\.\/skin-wuwa\.css'\s+import '\.\/skin-nte\.css'\s+import '\.\/skin-endfield\.css'/)
 for(const key of ['wuwa','nte','endfield']){
  const skin=read(`skin-${key}.css`)
  assert.ok(skin.includes(`[data-skin="${key}"]`),key)
  for(const other of ['wuwa','nte','endfield'].filter(k=>k!==key))assert.ok(!skin.includes(`[data-skin="${other}"]`),`${key} file stays per game`)
 }
 for(const file of ['skin.css','skin-wuwa.css','skin-nte.css','skin-endfield.css'])assert.doesNotMatch(read(file),/url\(|@font-face/,file)
})

test('QQ overview blocks take their own game skin inside the obsidian shell (D3)',async t=>{
 const Sheet=await loadVue(new URL('./qq-image/AccountOverviewSheet.vue',import.meta.url))
 const panel=(game,provider,payload)=>({game,provider,capability:'account',snapshot:{payload,fetched_at:'2026-10-21T00:00:00Z'}})
 const input={snapshot:{kind:'game_snapshot',game:'all',title:'我的',display_data:{panels:[panel('wuthering_waves','kuro',{nickname:'甲'}),panel('nte','tajiduo',{nickname:'乙'}),panel('endfield','skland',{base:{name:'丙'}})]}},command:'总览',origin:''}
 configure([input],{})
 const root=mount(t,Sheet,{input})
 assert.deepEqual(nodes(root,'section').filter(n=>String(n.props.class).includes('ao-game-block')).map(n=>n.props['data-skin']),['wuwa','nte','endfield'])
})

test('D7: no QQ obsidian text is smaller than 17px',()=>{
 const lab=readFileSync(new URL('./qq-image/lab.css',import.meta.url),'utf8'),obsidian=lab.slice(lab.indexOf('.lab-sheet.is-account-overview {'))
 const sizes=[...obsidian.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map(m=>Number(m[1]))
 assert.ok(sizes.length&&sizes.every(size=>size>=17),String(sizes))
 assert.match(readFileSync(new URL('./qq-image/reuse.css',import.meta.url),'utf8'),/\.wuwa-role-sub \{\s+font-size: var\(--qq-small\) !important;/)
})
