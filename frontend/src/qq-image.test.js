import test from 'node:test'
import assert from 'node:assert/strict'
import {imageCalendarWindows} from './qq-image/image-calendar.js'
import {guideAtoms,guideLines} from './qq-image/guide-presentation.js'
import {configure,viewModel} from './qq-image/models.js'
import {prepareReuse} from './qq-image/reuse-model.js'
import {schemes} from './qq-image/designs.js'

test('selected image layout only has A; all calendar windows are exactly fourteen Beijing days',()=>{
 assert.deepEqual(schemes.map(s=>s.id),['dossier'])
 for(const iso of ['2026-10-18T16:30:00+08:00','2026-11-01T00:01:00+08:00','2027-01-01T23:59:00+08:00']){
  const now=Date.parse(iso),windows=imageCalendarWindows([],now)
  assert.equal(windows.length,1);assert.equal(windows[0].range.days.length,14)
  assert.equal(windows[0].range.end-windows[0].range.start,14*86400000)
  assert.equal(new Date(windows[0].range.days[2].timestamp+8*3600000).toISOString().slice(0,10),iso.slice(0,10))
 }
})
test('guide presentation keeps every original character and punctuation attached to its entity',()=>{
 const tokens=[{text:'优先'},{text:'技能',entity:true},{text:'。其余稍后。'}],out=guideAtoms(tokens)
 assert.equal(out.map(t=>t.text+(t.trailing||'')).join(''),'优先技能。其余稍后。')
 assert.equal(out[1].trailing,'。')
 assert.equal(guideLines({sectionKey:'teams',text:'甲／乙；丙／丁。'}).join(''),'甲／乙；丙／丁。')
})
test('image-only NTE skills keep names and levels; original details remain intact',()=>{
 const source={snapshot:{kind:'nte_role',display_data:{snapshot:{payload:{entries:[{skills:[{name:'战技',level:0,items:[{desc:'长段说明'}]}],city_skills:[{name:'城区技',level:1,items:[{desc:'说明'}]}]}]}}}}}
 const before=JSON.stringify(source),role=prepareReuse(source).display_data.snapshot.payload.entries[0]
 assert.deepEqual(role.skills,[{name:'战技',level:0}]);assert.deepEqual(role.city_skills,[{name:'城区技',level:1}]);assert.equal(JSON.stringify(source),before)
})

test('partial challenge modules and missing activities remain renderable',()=>{
 const input={snapshot:{kind:'game_snapshot',display_data:{panels:[
  {game:'wuthering_waves',capability:'combat',snapshot:{payload:{hologram:{state:'unavailable'},slash:{state:'unavailable'}}}},
  {game:'wuthering_waves',capability:'activities',snapshot:{payload:{sections:{empty:{title:'无数据',progress:null}}}}}
 ]}}}
 assert.doesNotThrow(()=>prepareReuse(input))
 assert.deepEqual(prepareReuse(input).display_data.panels[1].snapshot.payload.sections,{})
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
