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
import {sheetSkin} from './qq-image/sheet-skin.js'

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
test('guide freshness leads the page and an automatic draft carries its mark instead of the reviewed label',()=>{
 configure([],{})
 const sections=[{key:'weapons',title:'武器推荐',text:'示例武器',sourceId:'9'}]
 const base={id:'1311',name:'示例新角色',sources:[{id:'9',title:'示例帖',author:'作者',version:'3.7',url:'u'}],sections}
 const draft={...base,freshness:{mark:'自动提炼·待校对',lines:['攻略检查于 2026-10-22 05:31','原帖共 6 张图，可在网站攻略页「查看原帖」查看']}}
 const model=viewModel({command:'鸣潮 攻略 示例新角色',snapshot:{kind:'guide',game:'wuthering_waves',as_of:'2026-10-22T08:00:00+08:00',display_data:{guide:draft}}})
 assert.ok(model.hero.meta.includes('自动提炼·待校对'));assert.ok(!model.hero.meta.includes('已整理的社区建议'))
 assert.equal(model.panels[0].title,'攻略状态')
 assert.deepEqual(model.panels[0].lines.map(l=>l.text),draft.freshness.lines)
 assert.equal(model.panels.at(-1).title,'攻略来源')
 const plain=viewModel({command:'鸣潮 攻略 示例',snapshot:{kind:'guide',game:'wuthering_waves',as_of:'2026-10-22T08:00:00+08:00',display_data:{guide:base}}})
 assert.ok(plain.hero.meta.includes('已整理的社区建议'));assert.ok(!plain.panels.some(p=>p.title==='攻略状态'))
 // Without icon hints (a live extraction) the sections read as text instead of placeholder chips.
 assert.ok(plain.panels.filter(p=>p.type==='guide_visual').every(p=>p.plain===true))
 const hinted=viewModel({command:'鸣潮 攻略 示例',snapshot:{kind:'guide',game:'wuthering_waves',as_of:'2026-10-22T08:00:00+08:00',display_data:{guide:{...base,asset_hints:['https://example.invalid/i.png']}}}})
 assert.ok(hinted.panels.filter(p=>p.type==='guide_visual').every(p=>p.plain===false))
})
test('the Endfield guide notice shows the snapshot text with the source name and no link',()=>{
 configure([],{})
 const text='暂未收录可核验的终末地角色攻略；可在 B 站搜索 猫冬MT「终末地攻略合集」。'
 const model=viewModel({command:'终末地 攻略',snapshot:{kind:'notice',game:'endfield',as_of:'2026-10-22T08:00:00+08:00',display_data:{title:'终末地 角色攻略',sections:[],notices:[text]}}})
 assert.equal(model.panels[0].text,text)
 assert.doesNotMatch(model.panels[0].text+model.panels[0].caption,/bilibili\.com|https?:/)
})
test('a bare guide reply is a plain notice, not an index image',()=>{
 const input={command:'鸣潮 攻略',snapshot:{kind:'notice',game:'wuthering_waves',as_of:'2026-10-18T00:00:00+08:00',display_data:{title:'鸣潮 角色攻略',sections:[],notices:['请发送「鸣潮 攻略 角色名」查看单个角色攻略；可用角色见网站攻略页。']}}}
 const model=viewModel(input)
 assert.deepEqual(model.panels.map(p=>p.type),['text'])
 assert.match(model.panels[0].text,/鸣潮 攻略 角色名.*网站攻略页/)
})

test('QQ skins: the sheet and each overview game block carry data-skin, and skinned images start from dark tokens',t=>{
 const read=name=>readFileSync(new URL('./qq-image/'+name,import.meta.url),'utf8')
 assert.match(read('LabRoot.vue'),/skin=computed\(\(\)=>sheetSkin\(props\.input\?\.snapshot\?\.game\)\)/)
 assert.match(read('LabRoot.vue'),/:data-skin="skin"/)
 assert.match(read('mount.js'),/dataset\.theme=sheetSkin\(snapshot\.game\)\?'dark':'light'/)
 assert.match(read('mount.js'),/import '\.\/reuse\.css'[\s\S]*import '\.\/skin\.css'/)
 assert.match(read('mount.js'),/import '\.\/skin\.css'\s+import '\.\/skin-wuwa\.css'\s+import '\.\/skin-nte\.css'\s+import '\.\/skin-endfield\.css'/)
 for(const key of ['wuwa','nte','endfield']){
  const skin=read(`skin-${key}.css`)
  assert.ok(skin.includes(`[data-skin="${key}"]`),key)
  for(const other of ['wuwa','nte','endfield'].filter(k=>k!==key))assert.ok(!skin.includes(`[data-skin="${other}"]`),`${key} file stays per game`)
 }
 for(const file of ['skin.css','skin-wuwa.css','skin-nte.css','skin-endfield.css'])assert.doesNotMatch(read(file),/url\(|@font-face/,file)
})

test('role sheets: every rule outranks the image type reset and no text is set below 17px',()=>{
 for(const name of ['WuwaRoleSheet','NteRoleSheet','RoleScoreHero']){
  const source=readFileSync(new URL(`./components/${name}.vue`,import.meta.url),'utf8')
  const css=source.slice(source.indexOf('<style scoped>')+14,source.indexOf('</style>')).replace(/\/\*[\s\S]*?\*\//g,'')
  // `.reuse.lab-sheet #render-content *` forces size, line height and spacing: each rule needs an id and !important.
  for(const rule of css.match(/[^{}]+\{[^{}]*\}/g))for(const selector of rule.slice(0,rule.indexOf('{')).split(/,(?![^(]*\))/))assert.match(selector.trim(),/^\.lab-sheet #render-content /,`${name}: ${selector}`)
  for(const [,prop,value] of css.matchAll(/(font-size|line-height|letter-spacing):([^;}]+)/g))assert.match(value,/!important$/,`${name}: ${prop}:${value}`)
  const sizes=[...css.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map(m=>Number(m[1]))
  assert.ok(sizes.every(size=>size>=17),`${name}: ${sizes}`)
 }
 // The old R1 grid is gone from the Wuwa skin; the sheet carries its own layout.
 assert.doesNotMatch(readFileSync(new URL('./qq-image/skin-wuwa.css',import.meta.url),'utf8'),/wuwa-role-detail|wuwa-portrait/)
})

test('C1.1: Wuwa sub-images keep unearned stars visible and lift the shared sub-17px labels',()=>{
 const skin=readFileSync(new URL('./qq-image/skin-wuwa.css',import.meta.url),'utf8')
 assert.match(skin,/\[data-skin="wuwa"\] #render-content \.stars \.off \{ color: rgba\(var\(--skin-tint-rgb\), \.3\); \}/)
 assert.match(skin,/\[data-skin="wuwa"\] #render-content \.ring-cap \{ font-size: var\(--qq-small\) !important; \}/)
 assert.match(skin,/\[data-skin="wuwa"\] #render-content \.wuwa-item-icon:not\(\.icon-large\) \.icon-fallback,\s*\.reuse\.lab-sheet\[data-skin="wuwa"\] \.guide-visual \.icon-fallback \{ font-size: var\(--qq-min-text, 17px\) !important; \}/)
 assert.match(skin,/\[data-skin="wuwa"\] \.source-line \{ font-size: var\(--qq-min-text, 17px\); \}/)
})

test('QQ overview blocks take their own game skin inside the obsidian shell (D3)',async t=>{
 const Sheet=await loadVue(new URL('./qq-image/AccountOverviewSheet.vue',import.meta.url))
 const panel=(game,provider,payload)=>({game,provider,capability:'account',snapshot:{payload,fetched_at:'2026-10-21T00:00:00Z'}})
 const input={snapshot:{kind:'game_snapshot',game:'all',title:'我的',display_data:{panels:[panel('wuthering_waves','kuro',{nickname:'甲'}),panel('nte','tajiduo',{nickname:'乙'}),panel('endfield','skland',{base:{name:'丙'}})]}},command:'总览',origin:''}
 configure([input],{})
 const root=mount(t,Sheet,{input})
 assert.deepEqual(nodes(root,'section').filter(n=>String(n.props.class).includes('ao-game-block')).map(n=>n.props['data-skin']),['wuwa','nte','endfield'])
})

test('C1.3: the obsidian sheet keeps its star trail but drops the dithered glow, gradient and blurred shadows',()=>{
 const lab=readFileSync(new URL('./qq-image/lab.css',import.meta.url),'utf8'),obsidian=lab.slice(lab.indexOf('.lab-sheet.is-account-overview {'))
 const sheet=obsidian.slice(0,obsidian.indexOf('}'))
 assert.match(sheet,/data:image\/svg\+xml/)
 assert.doesNotMatch(sheet,/gradient/)
 assert.doesNotMatch(obsidian,/box-shadow/)
 assert.doesNotMatch(obsidian.slice(obsidian.indexOf('.ao-capsule-banner {')),/^\.ao-(?:capsule-banner|identity-pill) \{[^}]*linear-gradient/m)
})
test('D7: no QQ obsidian text is smaller than 17px',()=>{
 const lab=readFileSync(new URL('./qq-image/lab.css',import.meta.url),'utf8'),obsidian=lab.slice(lab.indexOf('.lab-sheet.is-account-overview {'))
 const sizes=[...obsidian.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map(m=>Number(m[1]))
 assert.ok(sizes.length&&sizes.every(size=>size>=17),String(sizes))
 assert.match(readFileSync(new URL('./qq-image/reuse.css',import.meta.url),'utf8'),/\.wuwa-role-sub \{\s+font-size: var\(--qq-small\) !important;/)
})

test('cross-game QQ pages keep the obsidian shell; a game page keeps its own skin',()=>{
 assert.deepEqual(['all',undefined,'wuthering_waves','nte','endfield'].map(sheetSkin),['wuwa','wuwa','wuwa','nte','endfield'])
})

const HelpSheet=await loadVue(new URL('./qq-image/HelpSheet.vue',import.meta.url))
const cls=(n,name)=>String(n.props.class||'').split(' ').includes(name)

test('帮助 groups list registry lines as command cards; game groups carry their skin and placeholders are marked',t=>{
 const data={title:'帮助 · 游戏管家',notices:['先登录网站生成绑定码。'],sections:[
  {title:'绑定与账号',items:['绑定网站账号：绑定 实际绑定码','授权状态：我的账号']},
  {title:'总览与角色',items:['角色详情：游戏 角色 精确名称']},
  {title:'鸣潮专项',game:'wuthering_waves',items:['挑战记录：鸣潮 挑战']},
  {title:'终末地专项',game:'endfield',items:['帝江号：终末地 帝江号']}]}
 const root=mount(t,HelpSheet,{data,variant:'help'})
 const groups=nodes(root,'section').filter(n=>cls(n,'hs-group'))
 assert.deepEqual(groups.map(n=>[content(nodes(n,'h2')[0]),n.props['data-skin']]),[['绑定与账号',undefined],['总览与角色',undefined],['鸣潮专项','wuwa'],['终末地专项','endfield']])
 // Every registry line survives as command + description, in order.
 assert.deepEqual(nodes(root,'code').map(content),['绑定 实际绑定码','我的账号','游戏 角色 精确名称','鸣潮 挑战','终末地 帝江号'])
 assert.deepEqual(nodes(root,'span').filter(n=>cls(n,'hs-desc')).map(content),['绑定网站账号','授权状态','角色详情','挑战记录','帝江号'])
 const slots=nodes(root,'code').flatMap(n=>nodes(n,'span')).filter(n=>cls(n,'hs-slot')).map(content)
 assert.deepEqual(slots,['实际绑定码','游戏','精确名称'])
 assert.ok(nodes(root,'div').some(n=>cls(n,'hs-games')&&cls(n,'count-2')))
 assert.match(content(nodes(root,'aside')[0]),/使用说明 先登录网站生成绑定码/)
})

test('我的账号 shows one card per account, tinted by its game, and flags accounts that need re-authorization',t=>{
 const data={title:'QQ 网站绑定已确认。我的账号',notices:[],sections:[{title:'授权状态',items:[
  '鸣潮','授权：已授权','默认账号：是','终末地 · 鹰角寻访','授权：需重新授权','默认账号：否','未知来源','授权：已授权']}]}
 const root=mount(t,HelpSheet,{data,variant:'account'})
 const cards=nodes(root,'article').filter(n=>cls(n,'hs-account'))
 assert.deepEqual(cards.map(n=>[content(nodes(n,'h3')[0]),n.props['data-skin']]),[['鸣潮','wuwa'],['终末地 · 鹰角寻访','endfield'],['未知来源',undefined]])
 const rows=cards.map(card=>nodes(card,'div').filter(n=>nodes(n,'dt').length).map(n=>[content(n),n.props.class||'']))
 assert.deepEqual(rows[0],[['授权 已授权','is-ok'],['默认账号 是','']])
 assert.deepEqual(rows[1][0],['授权 需重新授权','is-warn'])
})

test('QQ 帮助 and 我的账号 notices use the command-card sheet; other notices use NoticeSheet',()=>{
 const lab=readFileSync(new URL('./qq-image/LabRoot.vue',import.meta.url),'utf8')
 assert.match(lab,/<HelpSheet v-(?:else-)?if="helpVariant"[^>]*\/>\s*<NoticeSheet v-else-if="isNotice"[^>]*\/>\s*<ReuseBody v-else/)
 assert.match(lab,/\/帮助\/\.test\(s\.display_data\?\.title\)\?'help':\/我的账号\/\.test\(s\.display_data\?\.title\)\?'account':null/)
})

test('Stage 1 overview system: all non-overview sheets use OverviewShell, min text >= 17px, and rosters/role details use dedicated sheets',async t=>{
 const read=name=>readFileSync(new URL('./qq-image/'+name,import.meta.url),'utf8')
 const lab=read('LabRoot.vue')
 assert.match(lab,/<OverviewShell/)
 assert.match(lab,/<RoleRosterSheet v-if="isRoleRoster"/)
 assert.match(lab,/<EndfieldOperatorSheet v-else-if="isEndfieldOperatorDetail"/)
 assert.match(lab,/<WuwaRoleDetailSheet v-else-if="isWuwaRoleDetail"/)
 assert.match(lab,/<NteRoleDetailSheet v-else-if="isNteRoleDetail/)
 const rawOvCss=read('overview-system.css')
 assert.doesNotMatch(rawOvCss,/radial-gradient/)
 const ovCss=rawOvCss.replace(/\/\*[\s\S]*?\*\//g,'')
 const sizes=[...ovCss.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map(m=>Number(m[1]))
 assert.ok(sizes.length&&sizes.every(size=>size>=17),'overview-system.css sizes: '+sizes)

 const RosterSheet=await loadVue(new URL('./qq-image/RoleRosterSheet.vue',import.meta.url))
 const wuwaInput={command:'鸣潮 角色',origin:'',snapshot:{kind:'game_snapshot',game:'wuthering_waves',as_of:'2026-10-21T12:00:00+08:00',title:'鸣潮 · 角色',
  display_data:{panels:[{game:'wuthering_waves',provider:'kuro',capability:'roles',snapshot:{fetched_at:'2026-10-21T12:00:00+08:00',state:'ok',complete:true,stale:false,
   payload:[{role_id:1108,name:'绯雪',star_level:5,level:90,chain:2,attribute:'冷凝',weapon:'迅刀',extra:{total_skill_level:55}},
            {role_id:1102,name:'散华',star_level:4,level:80,chain:6,attribute:'冷凝',weapon:'迅刀',extra:{total_skill_level:42}}]}}],notices:[]}}}
 configure([wuwaInput],{})
 const wuwaRoot=mount(t,RosterSheet,{input:wuwaInput})
 const wuwaText=content(wuwaRoot)
 for(const expected of ['练度总览','角色档案','绯雪','散华','二链','六链','LV.90','技能 55'])assert.ok(wuwaText.includes(expected),expected)

 const EfOpSheet=await loadVue(new URL('./qq-image/EndfieldOperatorSheet.vue',import.meta.url))
 const efInput={command:'终末地 干员 佩丽卡',origin:'',snapshot:{kind:'game_snapshot',game:'endfield',as_of:'2026-10-21T12:00:00+08:00',title:'终末地 · 佩丽卡',
  display_data:{panels:[{game:'endfield',provider:'skland',capability:'operator_detail',snapshot:{fetched_at:'2026-10-21T12:00:00+08:00',state:'ok',complete:true,stale:false,
   payload:{operator_detail:{id:'c1',name:'佩丽卡',level:90,rarity:6,potential:2,evolve_phase:4,profession:'术师',property:'电磁',
    weapon:{name:'孤舟',level:90,refine_level:5,breakthrough_level:4,gem:{name:'无瑕基质',terms:[{name:'意志提升',cost:6}]}},
    equipment:[{slot:'bodyEquip',name:'壤流轻甲',level:70}],
    skills:[{id:'s1',name:'疾电法',level:12}],
    tactical_item:{name:'优质芽针剂',rarity:'紫色品质'}}}}}],notices:[]}}}
 configure([efInput],{})
 const efRoot=mount(t,EfOpSheet,{input:efInput})
 const efText=content(efRoot)
 for(const expected of ['佩丽卡','孤舟','无瑕基质','意志提升','壤流轻甲','疾电法','LV. 12','优质芽针剂'])assert.ok(efText.includes(expected),expected)

 const WuwaDetail=await loadVue(new URL('./qq-image/WuwaRoleDetailSheet.vue',import.meta.url))
 const wuwaDetailData={
  role:{role_id:1205,role_name:'长离',level:90,breach:6,star_level:5,attribute_name:'热熔',weapon_type_name:'迅刀'},
  role_attribute_list:[{attribute_name:'生命',attribute_value:'15840'},{attribute_name:'暴击',attribute_value:'76.4%'}],
  weapon_data:{level:90,breach:6,reson_level:1,weapon:{weapon_name:'赫奕流明',weapon_star_level:5},main_prop_list:[{attribute_name:'攻击',attribute_value:'587'}]},
  skill_list:[{level:10,skill:{name:'赫羽三相',type:'常态攻击'}}],
  chain_list:[{order:1,name:'隐我之所藏',unlocked:true},{order:2,name:'循理之所往',unlocked:false}],
  equip_phantom_add_prop_list:[{attribute_name:'暴击',attribute_value:'43.4%'}],
  phantom_data:{cost:12,equip_phantom_list:[{level:25,cost:4,phantom_prop:{phantom_id:6000045,name:'燎照之骑'},fetter_detail:{name:'熔山裂谷'},main_props:[{attribute_name:'暴击',attribute_value:'22.0%'}],sub_props:[{attribute_name:'暴击伤害',attribute_value:'17.4%'},{attribute_name:'防御',attribute_value:'50'}]}]},
  assessment:{status:'scored',value:'168.16',max_value:'250',grade:'a',origin:'builtin_default',attribution:'xwuid_snapshot',item_results:[{item_id:'echo:0:6000045',status:'scored',value:'35.40',max_value:'50',grade:'ss',contributions:[{observation_id:'main_props:0',effective:true},{observation_id:'sub_props:0',effective:true},{observation_id:'sub_props:1',effective:false}]}]},
 }
 configure([],{})
 const wuwaDetailRoot=mount(t,WuwaDetail,{data:wuwaDetailData})
 const wuwaDetailText=content(wuwaDetailRoot)
 for(const expected of ['长离','Lv.90','15840','76.4%','赫奕流明','赫羽三相','隐我之所藏','168.16','35.40分','燎照之骑','熔山裂谷'])assert.ok(wuwaDetailText.includes(expected),expected)
 assert.equal(nodes(wuwaDetailRoot,'div').filter(n=>cls(n,'rd-stat-row')&&cls(n,'stat-effective')).length,2)
 assert.equal(nodes(wuwaDetailRoot,'div').filter(n=>cls(n,'rd-stat-row')&&cls(n,'stat-ineffective')).length,1)

 const NteDetail=await loadVue(new URL('./qq-image/NteRoleDetailSheet.vue',import.meta.url))
 const nteDetailRole={
  id:'1039',name:'法帝娅',quality:'S',element:'魂',level:80,awaken_level:1,mix_level:1,
  weapon:{name:'永恒圆舞曲',quality:'S',level:80,mix_level:1,breakthrough_level:4,properties:[{name:'基础攻击力',value:'512'}]},
  properties:[{name:'生命值',value:'28410'},{name:'暴击率',value:'46.5%'},{name:'治疗加成',value:'0%'}],
  skills:[{id:'s1',name:'话语中断的否定',level:8}],
  city_skills:[{id:'c1',name:'城区测试技',level:2}],
  suit:{name:'「小小大冒险」',activation_count:4,
   core:[{id:'core_orange_1',name:'「小小大冒险」',level:15,main_properties:[{id:'hpmaxup',name:'生命值百分比',value:'35.0%'}],properties:[{id:'critbase',name:'暴击率',value:'6.5%'},{id:'defadd',name:'防御力',value:'80'}]}],
   pie:[{id:'cell4_style1_1_orange',name:'Ⅳ型驱动',level:15,main_properties:[{id:'atkadd',name:'攻击力',value:'112'}],properties:[{id:'hpmaxup',name:'生命值百分比',value:'8.5%'}]}]},
  assessment:{status:'scored',value:'159.44',max_value:'310',grade:'s',origin:'builtin_default',attribution:'nte_workshop',item_results:[
   {item_id:'core:0:core_orange_1',status:'scored',value:'71.11',max_value:'150',grade:'a',contributions:[{contribution_id:'main:hpmaxup',effective:true},{contribution_id:'sub:critbase',effective:true},{contribution_id:'sub:defadd',effective:false}]},
   {item_id:'pie:0:cell4_style1_1_orange',status:'scored',value:'25.40',max_value:'40',grade:'ss',contributions:[{contribution_id:'sub:hpmaxup',effective:true}]}]},
 }
 const nteDetailRoot=mount(t,NteDetail,{role:nteDetailRole})
 const nteDetailText=content(nteDetailRoot)
 for(const expected of ['法帝娅','Lv80','28410','46.5%','永恒圆舞曲','话语中断的否定','159.44','71.11','25.40'])assert.ok(nteDetailText.includes(expected),expected)
 assert.doesNotMatch(nteDetailText,/治疗加成|城区测试技/)
 assert.equal(nodes(nteDetailRoot,'div').filter(n=>cls(n,'sheet-pieces')).length,1)
 assert.equal(nodes(nteDetailRoot,'article').filter(n=>cls(n,'sheet-piece')).length,2)
 assert.equal(nodes(nteDetailRoot,'div').filter(n=>cls(n,'piece-title')).length,2)
 assert.equal(nodes(nteDetailRoot,'div').filter(n=>cls(n,'rd-stat-row')&&cls(n,'stat-effective')).length,3)
 assert.equal(nodes(nteDetailRoot,'div').filter(n=>cls(n,'rd-stat-row')&&cls(n,'stat-ineffective')).length,1)
})

test('QQ cross-game pages: calendar, upcoming, guide and help text is never smaller than 17px',()=>{
 const read=name=>readFileSync(new URL('./qq-image/'+name,import.meta.url),'utf8')
 const charts=read('shared-charts.css'),calendar=charts.slice(charts.indexOf('/* Cloud Calendar Timeline'),charts.indexOf('/* NTE Teams'))
 for(const [name,css] of [['calendar',calendar],['guide-image.css',read('guide-image.css')],['HelpSheet.vue',read('HelpSheet.vue')]]){
  const sizes=[...css.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map(m=>Number(m[1]))
  assert.ok(sizes.length&&sizes.every(size=>size>=17),name+' '+sizes)
  assert.doesNotMatch(css,/font-size:\s*min\(/,name)
 }
 // A whole version is too narrow per day for 17px labels: only weekly ticks, the month start and today stay labelled.
 assert.match(calendar,/\.date-track:has\(> \.date-cell:nth-child\(22\)\) > \.date-cell:not\(:nth-child\(7n\+1\), \.is-month-start, \.is-today\) > :is\(small, strong\)/)
})

test('QQ dark skins: calendar bars, chips and nested game groups read on the dark base',()=>{
 const skin=readFileSync(new URL('./qq-image/skin.css',import.meta.url),'utf8')
 // No white bar start, white-on-accent chips or light remaining-days pills on a dark sheet.
 assert.match(skin,/\.cloud-calendar \.timeline-event:not\(\.is-point\) \{\s+background: linear-gradient\(rgba\(var\(--skin-tint-rgb\), \.12\), rgba\(var\(--skin-tint-rgb\), \.12\)\), var\(--shell-bg\) !important;/)
 assert.match(skin,/\.cloud-calendar :is\(\.event-status, \.day-today\) \{\s+background: var\(--skin-accent\) !important;\s+color: var\(--skin-on-accent\) !important;/)
 assert.match(skin,/\.cloud-calendar \.event-remaining \{\s+background: transparent !important;\s+color: var\(--skin-ink\) !important;/)
 // A nested game skin keeps the shell surfaces and only swaps accent and lines (D3).
 const nested=skin.slice(skin.indexOf('.reuse.lab-sheet[data-skin]:not(.is-account-overview) [data-skin] {'))
 for(const token of ['--skin-surface: var(--shell-surface)','--skin-ink: var(--shell-ink)','--game-accent: var(--skin-accent) !important'])assert.ok(nested.includes(token),token)
})

test('QQ panels and multi-game upcoming rows carry their game skin',t=>{
 const panel=readFileSync(new URL('./qq-image/Panel.vue',import.meta.url),'utf8')
 assert.match(panel,/:data-skin="skinOf\(panel\.gameId\|\|panel\.game\)\|\|undefined"/)
 assert.match(panel,/class="upcoming-row"[^>]*:data-skin="r\.game&&skinOf\(r\.gameId\)\|\|undefined"/)
})

test('the Wuwa overview reads the profile counters Kuro nests under extra.profile',async t=>{
 const Sheet=await loadVue(new URL('./qq-image/AccountOverviewSheet.vue',import.meta.url))
 const profile={world_level:8,active_days:553,achievement_count:640,achievement_star:831,small_count:243,big_count:53,
  box_list:[{box_name:'朴素奇藏箱',num:598},{box_name:'基准奇藏箱',num:271},{box_name:'精密奇藏箱',num:88},{box_name:'辉光奇藏箱',num:41}]}
 const input={snapshot:{kind:'game_snapshot',game:'wuthering_waves',title:'鸣潮',display_data:{panels:[{game:'wuthering_waves',provider:'kuro',capability:'account',
  snapshot:{payload:{nickname:'甲',level:80,extra:{active_day:534,profile}},fetched_at:'2026-10-21T00:00:00Z'}}]}},command:'总览',origin:''}
 configure([input],{})
 const text=content(mount(t,Sheet,{input}))
 for(const value of ['553','640','831','243','53','598','271','88','41','Lv.8','Lv.80'])assert.ok(text.includes(value),value)
 assert.doesNotMatch(text,/534/)
})

test('Stage 2 data sheets: LabRoot routes all 13 capabilities and preserves DOM/selector contracts',async t=>{
 const read=name=>readFileSync(new URL('./qq-image/'+name,import.meta.url),'utf8')
 const lab=read('LabRoot.vue')
 assert.match(lab,/<WuwaDataSheet v-else-if="isWuwaData"/)
 assert.match(lab,/<NteDataSheet v-else-if="isNteData"/)
 assert.match(lab,/<EndfieldDataSheet v-else-if="isEndfieldData"/)
 const rawOvCss=read('overview-system.css')
 assert.doesNotMatch(rawOvCss,/radial-gradient/)
 const ovCss=rawOvCss.replace(/\/\*[\s\S]*?\*\//g,'')
 const sizes=[...ovCss.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map(m=>Number(m[1]))
 assert.ok(sizes.length&&sizes.every(size=>size>=17),'overview-system.css sizes >= 17px: '+sizes)

 const wrap=(game,provider,capability,payload,command)=>({
  command,origin:'',
  snapshot:{kind:'game_snapshot',game,as_of:'2026-10-21T12:00:00+08:00',title:command,
   display_data:{panels:[{game,provider,capability,snapshot:{fetched_at:'2026-10-21T12:00:00+08:00',state:'ok',complete:true,stale:false,payload}}],notices:['阶段二示例提示']}}
 })

 // WuWa 4 caps
 const WuwaData=await loadVue(new URL('./qq-image/WuwaDataSheet.vue',import.meta.url))
 configure([],{})
 const wExplore=mount(t,WuwaData,{input:wrap('wuthering_waves','kuro','exploration',{
  country_groups:[{name:'瑝珑',progress:96.5,areas:[{name:'今州城',progress:100},{name:'怨鸟泽',progress:92}]}],
  detections:{total:240,by_level:{轻波级:90,巨浪级:80,怒涛级:50,海啸级:20}}
 },'鸣潮 探索')})
 for(const s of ['瑝珑','96.5%','今州城','240 只','轻波级'])assert.ok(content(wExplore).includes(s),s)

 const wProgress=mount(t,WuwaData,{input:wrap('wuthering_waves','kuro','progress',[
  {name:'活跃度',cur:100,total:100,refresh_at:'2026-10-22T04:00:00+08:00'},
  {name:'千道门扉',cur:3200,total:6000}
 ],'鸣潮 进度')})
 for(const s of ['活跃度','已完成','千道门扉','3,200'])assert.ok(content(wProgress).includes(s),s)

 const wRes=mount(t,WuwaData,{input:wrap('wuthering_waves','kuro','resources',{
  current:{kind:'month',period:'202610',data:{total_star:5840,total_coin:1850000,star_inc:'+18%',coin_inc:'-6%',
   star_list:[{type:'活动奖励',num:2600}],coin_list:[{type:'索拉里斯探索',num:900000}],copy_writing:'当期稳步增长'}},
  periods:{month:[{period:'202610',title:'2026 年 10 月'}]}
 },'鸣潮 资源')})
 for(const s of ['2026 年 10 月','5,840','环比 +18%','活动奖励','当期稳步增长'])assert.ok(content(wRes).includes(s),s)

 const wCombat=mount(t,WuwaData,{input:wrap('wuthering_waves','kuro','combat',{
  tower:{data:{is_unlock:true,season_end_at:'2026-11-01T04:00:00+08:00',difficulty_list:[
   {difficulty:3,difficulty_name:'深境区',tower_area_list:[{area_name:'残响之塔',star:12,max_star:12,floor_list:[{floor:1,star:3,max_star:3,role_list:[{role_id:1205,role_level:90}]}]}]}
  ]}},
  hologram:{data:{is_unlock:true,challenge_info:{b1:[{boss_name:'朔雷之鳞',difficulty:6,boss_level:100,pass_time:48,roles:[{role_id:1205}]}]}}},
  slash:{data:{is_unlock:true,difficulty_list:[{difficulty:2,difficulty_name:'再生海域',all_score:6800,max_score:10000,challenge_list:[{challenge_name:'第一海渊',score:6800,rank:'SS',half_list:[{half_name:'上半场',score:3600,role_list:[{role_id:1205}]}]}]}]}}
 },'鸣潮 挑战')})
 const wcText=content(wCombat)
 for(const s of ['深境区','残响之塔','长离','朔雷之鳞','48 秒','再生海域','6,800','SS'])assert.ok(wcText.includes(s),s)
 assert.doesNotMatch(wcText,/角色\s*1205/)

 // NTE 5 caps
 const NteData=await loadVue(new URL('./qq-image/NteDataSheet.vue',import.meta.url))
 const nProg=mount(t,NteData,{input:wrap('nte','tajiduo','progress',{
  schema_version:1,completed:269,total:480,gold:53,silver:96,bronze:120,
  categories:[{id:'1',name:'城市漫游',current:88,total:140},{id:'2',name:'引力Type IV',current:61,total:53},{id:'3',name:'未知分类',current:null,total:30}]
 },'异环 进度')})
 assert.equal(nodes(nProg,'div').filter(n=>cls(n,'nte-card')).length,1)
 assert.equal(nodes(nProg,'ul').filter(n=>cls(n,'categories')).length,1)
 assert.equal(nodes(nProg,'progress').length,2)
 assert.equal(nodes(nProg,'span').filter(n=>cls(n,'target-met')).length,1)

 const nHouse=mount(t,NteData,{input:wrap('nte','tajiduo','realestate',{
  schema_version:1,owned_count:1,total:3,entries:[
   {id:'bigword_house_1',name:'合成公寓',owned:true,resident_ids:['1019'],furniture:[{id:'f1',name:'椅子',owned:true}]},
   {id:'bigword_house_2',name:'未拥有公馆',owned:false,resident_ids:[],furniture:[]},
   {id:'bigword_house_3',name:'合成空馆',owned:null,resident_ids:[],furniture:[]}
  ]
 },'异环 房产')})
 assert.equal(nodes(nHouse,'div').filter(n=>cls(n,'asset-grid')).length,1)
 assert.equal(nodes(nHouse,'article').filter(n=>cls(n,'asset')).length,2)
 assert.equal(nodes(nHouse,'span').filter(n=>cls(n,'asset-cover')).length,2)
 assert.equal(nodes(nHouse,'strong').filter(n=>cls(n,'asset-name')).length,2)
 assert.ok(!content(nHouse).includes('未拥有公馆'))
 assert.ok(content(nHouse).includes('薄荷'))

 const nVeh=mount(t,NteData,{input:wrap('nte','tajiduo','vehicles',{
  schema_version:1,owned_count:1,total:2,show_id:'vehicle001',
  entries:[{id:'vehicle001',name:'极光超跑',owned:true,base:[{name:'极速',value:'267 km/h'}],advanced:[{name:'耐久',value:80,maximum:100}],models:[{type:'evmt_tyre'}]}]
 },'异环 车辆')})
 for(const s of ['极光超跑','展示载具','267 km/h','80 / 100','轮胎'])assert.ok(content(nVeh).includes(s),s)

 const nTeams=mount(t,NteData,{input:wrap('nte','public','teams',{
  schema_version:1,entries:[
   {name:'主角·零',description:'推荐阵容说明',image_urls:['https://webstatic.tajiduo.com/peidui-1.png']},
   {name:'主角·零',description:'重复名称跳过',image_urls:['https://webstatic.tajiduo.com/peidui-2.png']}
  ]
 },'异环 队伍')})
 assert.ok(content(nTeams).includes('推荐阵容说明'))
 assert.ok(!content(nTeams).includes('重复名称跳过'))

 // Endfield 4 caps
 const EfData=await loadVue(new URL('./qq-image/EndfieldDataSheet.vue',import.meta.url))
 const efExplore=mount(t,EfData,{input:wrap('endfield','skland','exploration',{report:{schema_version:1,regions:{summary:{region_count:2,settlement_count:1},items:[
  {id:'r1',name:'四号谷地',level:12,money:{count:500,total:1000},settlements:[{name:'枢纽区据点',level:4}],areas:[{id:'a1',name:'谷地通道',collections:[
   {key:'chests',label:'宝箱',current:10,total:20},{key:'puzzles',label:'醚质',current:0,total:8},{key:'blackboxes',label:'协议采录桩',current:null,total:null},
   {key:'equipment_chests',label:'装备制造模板',current:4,total:4},{key:'pieces',label:'维修灵感点',current:2,total:2}]}]},
  {id:'r2',name:'武陵',level:5,areas:[]}
 ]}}},'终末地 探索')})
 const regNodes=nodes(efExplore,'section').filter(n=>cls(n,'ef-region'))
 assert.equal(regNodes.length,2)
 assert.deepEqual(regNodes.map(r=>nodes(r,'li').length),[5,0])
 assert.equal(nodes(efExplore,'section').filter(n=>cls(n,'ef-settlement')).length,0)
 for(const s of ['四号谷地','武陵','地区数 2','宝箱','醚质'])assert.ok(content(efExplore).includes(s),s)
 assert.ok(!content(efExplore).includes('枢纽区据点')&&!content(efExplore).includes('剩余'))

 const efShip=mount(t,EfData,{input:wrap('endfield','skland','ship',{report:{schema_version:1,ship:{summary:{room_count:1,staffed_rooms:1,operator_slots:2},rooms:[
  {id:'rm1',name:'制造舱',level:3,operators:[{id:'c1',name:'佩丽卡',mood_percent:0,trust_percent:120,trust_level_name:'亲近'},{id:'c2',name:'陈千语',mood_percent:null,trust_percent:null}]}
 ]}}},'终末地 帝江号')})
 assert.ok(content(efShip).includes('0%')&&content(efShip).includes('未知'))
 assert.ok(nodes(efShip,'span').filter(n=>cls(n,'unknown-meter')).length>=2)

 const efHonor=mount(t,EfData,{input:wrap('endfield','skland','honor',{report:{schema_version:1,honor:{available:true,summary:{declared_count:34,listed_count:34},items:
  Array.from({length:34},(_,i)=>({id:`m${i}`,name:`奖章${i}`,category:`类别${Math.floor(i/2)}`,is_plated:i===0}))
 }}},'终末地 光荣之路')})
 assert.ok(content(efHonor).includes('奖章0')&&content(efHonor).includes('奖章33')&&!content(efHonor).includes('类别16'))

 const efCombat=mount(t,EfData,{input:wrap('endfield','skland','combat',{reports:[
  {schema_version:1,kind:'war',available:true,supported:true,stale:false,fetched_at:'2026-10-14T01:30:00Z',summary:{listed_count:1},records:[{id:'s1',name:'合成赛季',stars:9,weeks:[{name:'第一周',stars:9,groups:[]}]}],honors:[{name:'合成荣誉',stars:9,first_pass_at:'2026-10-14T02:00:00Z'}]},
  {schema_version:1,kind:'monument',available:true,supported:true,stale:true,fetched_at:'2026-10-14T02:30:00Z',summary:{listed_count:1},records:[{id:'m1',name:'合成丰碑',groups:[]}]},
  {schema_version:1,kind:'crisis',available:true,supported:true,stale:false,fetched_at:'2026-10-14T03:30:00Z',summary:{listed_count:1,highest:0,challenge_count:null},records:[{id:'c1',result:0,passed:false}]}
 ]},'终末地 挑战')})
 const efCombatText=content(efCombat)
 for(const s of ['战争观测时间','丰碑观测时间','危机观测时间','2026-10-14 09:30','2026-10-14 10:30','2026-10-14 11:30','已有资料待更新','战争 · 挑战记录','合成赛季','已有荣誉'])assert.ok(efCombatText.includes(s),s)
})

test('Stage 3 overview system: gacha (3 games), events/calendar, guide and notice sheets preserve all contracts',async t=>{
 const {shellMeta}=await import('./qq-image/shell-meta.js')
 const read=name=>readFileSync(new URL('./qq-image/'+name,import.meta.url),'utf8')
 const lab=read('LabRoot.vue')
 for(const tag of ['WuwaGachaSheet','NteGachaSheet','EndfieldGachaSheet','EventCalendarSheet','GuideSheet','NoticeSheet']){
  assert.match(lab,new RegExp(`<${tag} v-else-if=`))
 }
 const rawOvCss=read('overview-system.css')
 assert.doesNotMatch(rawOvCss,/radial-gradient/)
 const ovCss=rawOvCss.replace(/\/\*[\s\S]*?\*\//g,'')
 const sizes=[...ovCss.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map(m=>Number(m[1]))
 assert.ok(sizes.length&&sizes.every(size=>size>=17),'overview-system.css sizes >= 17px: '+sizes)

 // 1. WuWa Gacha
 const WuwaGachaSheet=await loadVue(new URL('./qq-image/WuwaGachaSheet.vue',import.meta.url))
 configure([],{})
 const wuwaGachaInput={command:'鸣潮 抽卡',origin:'',snapshot:{kind:'wuwa_gacha',game:'wuthering_waves',as_of:'2026-10-21T12:00:00+08:00',title:'鸣潮 · 抽卡档案',
  display_data:{archive:{state:'ok',total:155,gold_total:2,coverage:{complete:true,source:'official_query',earliest:'2026-09-01T10:00:00+08:00',latest:'2026-10-20T22:00:00+08:00',imported_at:'2026-10-21T11:30:00+08:00'},
   pools:[{pool:'1',name:'角色活动唤取',total:125,pity:{count:25,status:'exact',hard_pity_remaining:55},rarity_distribution:{5:2,4:15,3:108}},{pool:'2',name:'武器活动唤取',total:30,pity:{count:30,status:'lower_bound'},rarity_distribution:{4:4,3:26}}],
   aggregates:{total:1,items:[{name:'今汐',pool:'1',kind:'gold_period',period_count:68}]},
   gold:[{draw_id:'d1',time:'2026-10-12T20:10:00+08:00',pool:'1',name:'长离',rarity:5,resource_type:'角色',count:1}],
   items:[{draw_id:'d1',time:'2026-10-12T20:10:00+08:00',pool:'1',name:'长离',rarity:5,resource_type:'角色',count:1}]}}}}
 const wuwaGachaRoot=mount(t,WuwaGachaSheet,{input:wuwaGachaInput})
 const wgText=content(wuwaGachaRoot)
 for(const s of ['155','角色活动唤取','当前垫抽 25','距上限 55 抽','今汐','68 抽','长离'])assert.ok(wgText.includes(s),s)

 // 2. NTE Gacha (+ .cloud-gacha .bar-track / .bar-values contract + Ledger)
 const NteGachaSheet=await loadVue(new URL('./qq-image/NteGachaSheet.vue',import.meta.url))
 const nteGachaInput={command:'异环 抽卡',origin:'',snapshot:{kind:'nte_gacha',game:'nte',as_of:'2026-10-21T12:00:00+08:00',title:'异环 · 抽卡统计与账本',
  display_data:{snapshot:{fetched_at:'2026-10-21T11:50:00+08:00',state:'ok',stale:false,payload:{schema_version:1,luck_title:'欧气满满',luck_type:2,pools:[{name:'限定角色',total_draws:120,s_count:2,average:60.0,guarantee:90,details:[{item_id:'9001',name:'合成角色甲',pity:32,lucky_type:1,obtained_at:'2026-10-12T20:01:00+08:00'}]}]}},
   ledger:{total_records:12,pools:[{pool_id:'Lottery_LimitedCharacter',total_pulls:12,pity:{status:'exact',count:12,hard_pity_remaining:78,rule_basis:'user_configured'}}],records:[{uid:'u1',pool_group_id:'Lottery_LimitedCharacter',reward_name:'早雾',reward_rank:'S',quantity:1,result_type:'single_pull',timestamp:'2026-10-12T20:01:00+08:00'}]},roles:[]}}}
 const nteGachaRoot=mount(t,NteGachaSheet,{input:nteGachaInput})
 assert.equal(nodes(nteGachaRoot,'div').filter(n=>cls(n,'cloud-gacha')).length,1)
 assert.equal(nodes(nteGachaRoot,'div').filter(n=>cls(n,'bar-track')).length,1)
 assert.equal(nodes(nteGachaRoot,'div').filter(n=>cls(n,'bar-values')).length,1)
 const ngText=content(nteGachaRoot)
 for(const s of ['欧气满满','限定角色','合成角色甲','32','超欧','本人逐抽账本','12 抽','早雾'])assert.ok(ngText.includes(s),s)

 // 3. Endfield Gacha (preserves .endfield-gacha / .pool-detail .detail-head h3 / .pull-row / .pull-value + separate kinds)
 const EndfieldGachaSheet=await loadVue(new URL('./qq-image/EndfieldGachaSheet.vue',import.meta.url))
 const efGachaInput={command:'终末地 寻访战报',origin:'',snapshot:{kind:'game_snapshot',game:'endfield',as_of:'2026-10-21T12:00:00+08:00',title:'终末地 · 寻访战报',
  display_data:{panels:[{game:'endfield',provider:'hypergryph',capability:'gacha',snapshot:{fetched_at:'2026-10-21T11:45:00+08:00',state:'ok',complete:true,stale:false,
   payload:{schema_version:1,complete:true,report:{schema_version:1,pools:[
    {key:'pool-0',label:'合成池0',kind:'character',total:150,six_star:3,five_star:15,four_star:132,unknown_rarity:0,since_last_six:{status:'exact',count:12},
     history:[{name:'伊冯',pulls:58,status:'exact',obtained_at:1760300000000},{name:'佩丽卡',pulls:61,status:'lower_bound',obtained_at:1760200000000},{name:'余烬',pulls:0,status:'lower_bound',obtained_at:1760100000000}]},
    {key:'pool-w',label:'兵器库甲',kind:'weapon',total:40,six_star:1,five_star:6,four_star:33,unknown_rarity:0,since_last_six:{status:'exact',count:5},history:[{name:'熔铸剑',pulls:35,status:'exact',obtained_at:1760250000000}]}
   ]}}}}]}}}
 const efGachaRoot=mount(t,EndfieldGachaSheet,{input:efGachaInput})
 assert.equal(nodes(efGachaRoot,'section').filter(n=>cls(n,'endfield-gacha')).length,1)
 const h3Texts=nodes(efGachaRoot,'article').filter(n=>cls(n,'pool-detail')).map(card=>content(nodes(card,'h3')[0]))
 assert.deepEqual(h3Texts,['合成池0','武器申领'])
 const pullVals=nodes(efGachaRoot,'span').filter(n=>cls(n,'pull-value')).map(n=>content(n).replace(/\s+/g,''))
 assert.deepEqual(pullVals,['58抽','≥61抽','抽数未知','35抽'])
 const efMeta=shellMeta(efGachaInput,viewModel(efGachaInput))
 // Operator headhunting (150) and weapon requisition (40) are never summed into 190.
 assert.deepEqual(efMeta.heroStats.map(s=>[s.label,s.value]),[['干员寻访','150'],['武器申领','40'],['统计卡池','2']])
 assert.doesNotMatch(content(efGachaRoot),/本图卡池|内容已省略/)

 // 4. EventCalendarSheet (calendar + recent_events)
 const EventCalendarSheet=await loadVue(new URL('./qq-image/EventCalendarSheet.vue',import.meta.url))
 const calInput=calendarInput([{name:'版本大活动',category:'限时活动',start_at:'2026-10-01T10:00:00+08:00',end_at:'2026-11-20T10:00:00+08:00'}],'1.4')
 const calModel=viewModel(calInput)
 const calRoot=mount(t,EventCalendarSheet,{input:calInput,model:calModel})
 assert.ok(content(calRoot).includes('异环 · 1.4 版本'))
 assert.ok(nodes(calRoot,'section').some(n=>cls(n,'ov-cal-group')&&n.props['data-skin']==='nte'))
 const upInput=recentInput('all',[['nte',[{name:'新版本开启',category:'版本活动',start_at:'2026-10-22T10:00:00+08:00',end_at:'2026-11-22T10:00:00+08:00'}]],['endfield',[]]])
 const upRoot=mount(t,EventCalendarSheet,{input:upInput,model:viewModel(upInput)})
 assert.ok(content(upRoot).includes('新版本开启')&&content(upRoot).includes('异环'))

 // 5. GuideSheet (.guide-role-context > div without portrait)
 const GuideSheet=await loadVue(new URL('./qq-image/GuideSheet.vue',import.meta.url))
 const guideInput={command:'异环 攻略 主角·零',origin:'',snapshot:{kind:'guide',game:'nte',as_of:'2026-10-21T12:00:00+08:00',title:'异环 · 主角·零攻略',
  display_data:{guide:{id:'1001',name:'主角·零',element:'光',role:'主C',freshness:{mark:null,lines:['攻略检查于 2026-10-21 12:00']},sections:[{key:'weapons',title:'弧盘推荐',text:'推荐弧盘示例'}],sources:[{id:'1',title:'攻略来源帖',author:'作者A',version:'1.0',url:'https://www.tajiduo.com/bbs/index.html#/post?postId=1'}]}}}}
 const guideRoot=mount(t,GuideSheet,{input:guideInput,model:viewModel(guideInput)})
 const roleCtx=nodes(guideRoot,'div').find(n=>cls(n,'guide-role-context'))
 assert.ok(roleCtx&&!cls(roleCtx,'has-portrait'))
 assert.equal(nodes(roleCtx,'img').length,0)
 assert.ok(content(guideRoot).includes('主角·零')&&content(guideRoot).includes('攻略状态')&&content(guideRoot).includes('攻略来源帖'))

 // 6. NoticeSheet (Endfield guide context + retired command + unbound notice)
 const NoticeSheet=await loadVue(new URL('./qq-image/NoticeSheet.vue',import.meta.url))
 const efNoticeInput={command:'终末地 攻略',origin:'',snapshot:{kind:'notice',game:'endfield',as_of:'2026-10-22T08:00:00+08:00',title:'终末地 角色攻略',display_data:{title:'终末地 角色攻略',sections:[],notices:['暂未收录可核验的终末地角色攻略；可在 B 站搜索 猫冬MT「终末地攻略合集」。']}}}
 const efNoticeRoot=mount(t,NoticeSheet,{input:efNoticeInput,model:viewModel(efNoticeInput)})
 assert.ok(content(efNoticeRoot).includes('猫冬MT')&&content(efNoticeRoot).includes('角色资料已收录'))
 assert.doesNotMatch(content(efNoticeRoot),/https?:/)
 const genNoticeInput={command:'绑定',origin:'',snapshot:{kind:'notice',game:'all',as_of:'2026-10-22T08:00:00+08:00',title:'当前群尚未绑定',display_data:{title:'当前群尚未绑定',sections:[{title:'绑定步骤',items:['登录看板：前往云端网站生成绑定码']}],notices:['请在当前群发送 绑定 你的绑定码。']}}}
 const genNoticeRoot=mount(t,NoticeSheet,{input:genNoticeInput,model:viewModel(genNoticeInput)})
 assert.ok(content(genNoticeRoot).includes('前往云端网站生成绑定码')&&content(genNoticeRoot).includes('绑定 你的绑定码'))
})

test('Polish upgrade: PosterCalendar, shellMeta deduplication, Endfield SVG fallbacks, and HelpSheet grid balance',async t=>{
 const {shellMeta}=await import('./qq-image/shell-meta.js')
 const HelpSheetCss=readFileSync(new URL('./qq-image/HelpSheet.vue',import.meta.url),'utf8')
 assert.doesNotMatch(HelpSheetCss,/radial-gradient/)
 const helpStyle=HelpSheetCss.split('<style>')[1]?.replace(/\/\*[\s\S]*?\*\//g,'')||''
 const helpSizes=[...helpStyle.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map(m=>Number(m[1]))
 assert.ok(helpSizes.length&&helpSizes.every(sz=>sz>=17),'HelpSheet sizes >= 17px: '+helpSizes)

 // 1. PosterCalendar single-game categories + unified multi-game ruler
 const EventCalendarSheet=await loadVue(new URL('./qq-image/EventCalendarSheet.vue',import.meta.url))
 const singleCalInput={command:'异环 日历',origin:'',snapshot:{kind:'calendar',game:'nte',as_of:'2026-11-10T12:00:00+08:00',
  display_data:{games:[{game_id:'nte',display_name:'异环'}],snapshots:{nte:{events:{version:'1.5',payload:[
   {name:'角色卡池上半',category:'角色卡池',version:'1.5',start_at:'2026-11-05T10:00:00+08:00',end_at:'2026-11-26T04:00:00+08:00'},
   {name:'弧盘研募上半',category:'弧盘研募',version:'1.5',start_at:'2026-11-05T10:00:00+08:00',end_at:'2026-11-26T04:00:00+08:00'},
   {name:'七日签到补给',category:'限时活动',version:'1.5',start_at:'2026-11-05T10:00:00+08:00',end_at:'2026-12-17T04:00:00+08:00'},
   {name:'待定预告',category:'限时活动',version:'1.5'}
  ]}}}}}}
 const singleCalRoot=mount(t,EventCalendarSheet,{input:singleCalInput,model:viewModel(singleCalInput)})
 const scText=content(singleCalRoot)
 for(const s of ['寻访与角色','01','武器与弧盘','02','限时签到','03','今天 11.10','时间待定 · 1 项','待定预告'])assert.ok(scText.includes(s),s)
 assert.equal(nodes(singleCalRoot,'img').length,0)

 const multiCalInput={command:'日历',origin:'',snapshot:{kind:'calendar',game:'all',as_of:'2026-11-10T12:00:00+08:00',
  display_data:{games:[{game_id:'wuthering_waves',display_name:'鸣潮'},{game_id:'nte',display_name:'异环'},{game_id:'endfield',display_name:'终末地'}],
   snapshots:{
    wuthering_waves:{events:{version:'2.3',payload:[{name:'鸣潮活动',category:'版本活动',version:'2.3',start_at:'2026-11-01T10:00:00+08:00',end_at:'2026-11-20T04:00:00+08:00'}]}},
    nte:{events:{version:'1.5',payload:[{name:'异环活动',category:'限时活动',version:'1.5',start_at:'2026-11-05T10:00:00+08:00',end_at:'2026-11-25T04:00:00+08:00'}]}},
    endfield:{events:{version:'1.1',payload:[{name:'终末地活动',category:'限时活动',version:'1.1',start_at:'2026-11-08T10:00:00+08:00',end_at:'2026-11-28T04:00:00+08:00'}]}}
   }}}}
 const multiCalRoot=mount(t,EventCalendarSheet,{input:multiCalInput,model:viewModel(multiCalInput)})
 assert.equal(nodes(multiCalRoot,'div').filter(n=>cls(n,'ov-pcal-ruler-row')).length,1)
 const bandSkins=nodes(multiCalRoot,'section').filter(n=>cls(n,'ov-cal-group')).map(n=>n.props['data-skin'])
 assert.deepEqual(bandSkins,['wuwa','nte','endfield'])

 // 2. shellMeta heroRing, heroBadge, ambient element
 const nteProgInput={command:'异环 进度',origin:'',snapshot:{kind:'game_snapshot',game:'nte',as_of:'2026-10-21T12:00:00+08:00',
  display_data:{panels:[{game:'nte',capability:'progress',snapshot:{fetched_at:'2026-10-21T12:00:00+08:00',state:'ok',payload:{schema_version:1,completed:122,total:200,gold:40,silver:50,bronze:32,categories:[]}}}]}}}
 const nteProgMeta=shellMeta(nteProgInput,viewModel(nteProgInput))
 assert.deepEqual(nteProgMeta.heroRing,{pct:61,sub:'122/200',label:'总达成率'})
 assert.equal(nteProgMeta.heroStats.length,0)

 const nteGachaMeta=shellMeta({command:'异环 抽卡',origin:'',snapshot:{kind:'nte_gacha',game:'nte',as_of:'2026-10-21T12:00:00+08:00',
  display_data:{snapshot:{payload:{luck_title:'天选之人',luck_type:1,pools:[{total_draws:90,s_count:2}]}}}}},{title:'异环 · 抽卡统计',asOf:'2026-10-21 12:00',panels:[]})
 assert.equal(nteGachaMeta.heroBadge?.title,'天选之人')
 assert.equal(nteGachaMeta.heroStats.length,0)

 // 3. EndfieldOperatorSheet inline SVG fallbacks & 0 images inside uncached .skill-art
 const EndfieldOperatorSheet=await loadVue(new URL('./qq-image/EndfieldOperatorSheet.vue',import.meta.url))
 const efOpInput={command:'终末地 干员 佩丽卡',origin:'',snapshot:{kind:'game_snapshot',game:'endfield',as_of:'2026-10-21T12:00:00+08:00',
  display_data:{panels:[{game:'endfield',capability:'operator_detail',snapshot:{state:'ok',payload:{operator_detail:{id:'c1',name:'佩丽卡',level:80,rarity:6,profession:'术师',property:'电磁',
   weapon:{name:'武器甲',level:70,refine_level:1,breakthrough_level:3,gem:{name:'基质甲',terms:[{name:'攻击',cost:3}]}},
   equipment:[{slot:'bodyEquip',name:'护甲甲',level:50}],skills:[{id:'s1',name:'技能一',level:8}],tactical_item:{name:'道具甲',rarity:'5'}}}}}]}}}
 const efOpRoot=mount(t,EndfieldOperatorSheet,{input:efOpInput})
 const skillArt=nodes(efOpRoot,'div').find(n=>cls(n,'skill-art'))
 assert.ok(skillArt&&nodes(skillArt,'img').length===0&&nodes(skillArt,'svg').length>=1)
 assert.ok(nodes(efOpRoot,'svg').some(n=>cls(n,'ef-op-slot-svg')))

 // 4. HelpSheet balanced item grids
 const helpBalRoot=mount(t,HelpSheet,{variant:'help',data:{title:'帮助',notices:[],sections:[
  {title:'四项组',items:['A：cmd a','B：cmd b','C：cmd c','D：cmd d']},
  {title:'五项组',items:['A：cmd 1','B：cmd 2','C：cmd 3','D：cmd 4','E：cmd 5']}
 ]}})
 const lists=nodes(helpBalRoot,'ul').filter(n=>cls(n,'hs-items'))
 assert.ok(cls(lists[0],'cols-2')&&cls(lists[1],'cols-6-balanced')&&cls(lists[1],'tail-2'))
})

test('Poster calendar keeps short-bar labels beside their bars and rail labels whole; Endfield combat numbers cards under their section',async t=>{
 const EventCalendarSheet=await loadVue(new URL('./qq-image/EventCalendarSheet.vue',import.meta.url))
 const input={command:'日历',origin:'',snapshot:{kind:'calendar',game:'all',as_of:'2026-10-21T12:00:00+08:00',
  display_data:{games:[{game_id:'wuthering_waves',display_name:'鸣潮'},{game_id:'nte',display_name:'异环'}],snapshots:{
   wuthering_waves:{events:{version:'3.7',payload:[
    {name:'千岛寻珍',category:'限时活动',version:'3.7',start_at:'2026-10-08T10:00:00+08:00',end_at:'2026-11-18T04:00:00+08:00'},
    {name:'声骸双倍掉落 · 无音清剿',category:'限时活动',version:'3.7',start_at:'2026-10-21T10:00:00+08:00',end_at:'2026-10-28T04:00:00+08:00'}]}},
   nte:{events:{version:'1.2',payload:[
    {name:'海特洛霓虹节庆典',category:'版本主题',version:'1.2',start_at:'2026-10-10T10:00:00+08:00',end_at:'2026-11-10T04:00:00+08:00'},
    {name:'尾声补给',category:'限时活动',version:'1.2',start_at:'2026-11-12T10:00:00+08:00',end_at:'2026-11-17T04:00:00+08:00'}]}}}}}}
 const root=mount(t,EventCalendarSheet,{input,model:viewModel(input)})
 const pct=v=>Number.parseFloat(String(v))
 const bars=nodes(root,'article').filter(n=>cls(n,'ov-pcal-bar')&&cls(n,'is-short'))
 const labels=nodes(root,'div').filter(n=>cls(n,'ov-pcal-short-lbl'))
 assert.equal(bars.length,2);assert.equal(labels.length,2)
 bars.forEach((bar,i)=>{
  const {left,width}=bar.props.style,style=labels[i].props.style
  if(style.left!=null)assert.ok(pct(style.left)>=pct(left)+pct(width),`label ${i} starts after its bar`)
  else assert.ok(pct(style.right)>=100-pct(left),`label ${i} ends before its bar`)
 })
 assert.ok(labels.some(n=>n.props.style.left!=null)&&labels.some(n=>n.props.style.right!=null))

 const css=readFileSync(new URL('./qq-image/overview-system.css',import.meta.url),'utf8')
 assert.match(css,/\.ov-pcal-root \{\s*--pcal-rail: 112px;/)
 assert.match(css,/\.ov-pcal-rail-title \{[^}]*word-break: keep-all;/)
 assert.match(css,/\.ov-ef-combat \.ef-cb-title::before \{\s*counter-increment: ef-block;/)
 assert.match(css,/\.ov-ef-combat :is\(\.ef-cb-rec-title, \.ef-cb-honor-title\)::before \{\s*counter-increment: ef-card;\s*content: counter\(ef-block, decimal-leading-zero\) '\.' counter\(ef-card\)/)
 assert.doesNotMatch(css,/radial-gradient/)
})

test('Poster calendar moves names that do not fit their bar beside it and never truncates side labels',async t=>{
 const EventCalendarSheet=await loadVue(new URL('./qq-image/EventCalendarSheet.vue',import.meta.url))
 const input={command:'鸣潮 日历',origin:'',snapshot:{kind:'calendar',game:'wuthering_waves',as_of:'2026-11-22T01:00:00+08:00',
  display_data:{games:[{game_id:'wuthering_waves',display_name:'鸣潮'}],snapshots:{wuthering_waves:{events:{version:'3.8',payload:[
   {name:'「浮声沉兵」角色活动唤取 · 共鸣者「卡提希娅」限时登场',category:'角色卡池',version:'3.8',start_at:'2026-11-13T10:00:00+08:00',end_at:'2026-12-03T11:59:00+08:00'},
   {name:'千岛寻珍',category:'限时活动',version:'3.8',start_at:'2026-11-13T10:00:00+08:00',end_at:'2026-12-24T03:59:00+08:00'}]}}}}}}
 const root=mount(t,EventCalendarSheet,{input,model:viewModel(input)})
 const inside=nodes(root,'strong').filter(n=>cls(n,'ov-pcal-bar-name')).map(n=>content(n))
 const beside=nodes(root,'div').filter(n=>cls(n,'ov-pcal-short-lbl')).map(n=>content(n))
 assert.deepEqual(inside,['千岛寻珍'])
 assert.ok(beside.some(text=>text.includes('卡提希娅')),beside)
 const css=readFileSync(new URL('./qq-image/overview-system.css',import.meta.url),'utf8')
 const label=css.match(/\.ov-pcal-short-lbl strong \{[^}]*\}/)?.[0]||''
 assert.ok(label&&!/text-overflow|white-space: nowrap|overflow: hidden/.test(label),label)
})
