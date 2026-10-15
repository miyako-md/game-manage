import test from 'node:test'
import assert from 'node:assert/strict'
import { calendarRange, collectCalendarEvents, eventBoundaryText, eventEndpoint, eventGeometry, eventStatus, normalizeCalendarEvents } from './calendar.js'
import { selectQqEvents } from './qq-event-selection.js'

const now=Date.parse('2026-10-15T12:00:00+08:00')
const event=(name,extra={})=>({name,start_at:'2026-10-14T12:00:00+08:00',end_at:'2026-10-16T12:00:00+08:00',...extra})
const names=rows=>rows.map(row=>row.name)

test('QQ event instants require time and source precision, including resolved version end',()=>{
  for (const precision of ['day','relative','dependent','unknown','second']) assert.equal(eventEndpoint(event('x',{start_precision:precision}),'start'),null)
  assert.equal(eventEndpoint({start_at:'2026-10-15'},'start'),null)
  assert.equal(eventEndpoint({start_date:'2026-10-15'},'start'),null)
  assert.equal(eventEndpoint(event('x',{start_precision:'minute'}),'start'),Date.parse('2026-10-14T12:00:00+08:00'))
  assert.equal(eventEndpoint(event('x',{end_precision:'version_end'}),'end'),Date.parse('2026-10-16T12:00:00+08:00'))
})

test('current selection retains uncertain dates unless an explicit instant disproves current status',()=>{
  const rows=[event('确认进行'),event('日精度',{start_precision:'day'}),event('相对时间',{start_precision:'relative',start_text:'维护后'}),event('未知时间',{start_precision:'unknown'}),event('已结束',{end_at:'2026-10-15T12:00:00+08:00'}),event('尚未开始',{start_at:'2026-10-15T12:01:00+08:00'}),event('日期失序',{start_at:'2026-10-16T12:00:00+08:00',end_at:'2026-10-14T12:00:00+08:00'})]
  assert.deepEqual(names(selectQqEvents(rows,'events',now)),['确认进行','日精度','相对时间','未知时间'])
})

test('recent selection uses the strict 168-hour instant window and keeps explicit uncertainty',()=>{
  const rows=[event('恰好现在',{start_at:null,end_at:'2026-10-15T12:00:00+08:00'}),event('窗口右端',{start_at:null,end_at:'2026-10-22T12:00:00+08:00'}),event('窗口外',{start_at:null,end_at:'2026-10-22T12:01:00+08:00'}),event('日期待确认',{start_at:null,end_at:null,start_date:'2026-12-01',start_precision:'day'}),event('相对开放',{start_precision:'relative',start_text:'后续版本开放',end_at:null}),event('显式未知',{start_precision:'unknown',end_at:null}),{name:'完全无日期'},event('失序',{start_at:'2026-10-17T12:00:00+08:00',end_at:'2026-10-16T12:00:00+08:00'})]
  assert.deepEqual(names(selectQqEvents(rows,'recent_events',now)),['窗口右端','日期待确认','相对开放','显式未知','失序'])
})

test('phase normalization merges source metadata, names every phase and deduplicates identical source rows',()=>{
  const source=event('阶段活动',{source_name:'官方',phases:[{start_at:'2026-10-14T12:00:00+08:00',end_at:'2026-10-15T12:00:00+08:00'},{start_at:'2026-10-15T12:00:00+08:00',end_at:'2026-10-17T12:00:00+08:00'}]})
  const normalized=normalizeCalendarEvents([source,source])
  assert.deepEqual(names(normalized),['阶段活动 · 阶段 1','阶段活动 · 阶段 2'])
  assert.ok(normalized.every(row=>row.source_name==='官方' && !('phases' in row)))
  assert.deepEqual(names(selectQqEvents([source],'events',now)),['阶段活动 · 阶段 2'])
  assert.equal(source.phases.length,2)
})

test('current command filtering does not replace the shared website geometry or precision text',()=>{
  const range=calendarRange(now,'rolling')
  const row=event('日精度',{start_at:'2026-10-14T00:00:00+08:00',start_precision:'day'})
  const selected=selectQqEvents([row],'events',now)
  assert.equal(selected.length,1)
  assert.deepEqual(eventGeometry(selected[0],range),eventGeometry(row,range))
  assert.equal(eventStatus(selected[0],now),eventStatus(row,now))
  assert.match(eventBoundaryText(row,'start'),/2026-10-14 · 时刻未确认/)
  assert.doesNotMatch(eventBoundaryText(row,'start'),/00:00/)
})

test('calendar commands retain the website exclusive date end rather than adding a whole day',()=>{
  const row={name:'日期范围',start_at:'2026-10-14',end_at:'2026-10-15',start_precision:'day',end_precision:'day'}
  const range=calendarRange(now,'rolling'),geometry=eventGeometry(row,range)
  assert.equal(geometry.kind,'range')
  assert.equal(geometry.end,Date.parse('2026-10-15T00:00:00+08:00'))
  assert.equal(eventStatus(row,now),'已结束')
  assert.equal(selectQqEvents([row],'calendar',now).length,1)
  assert.equal(eventBoundaryText(row,'end'),'2026-10-15 · 时刻未确认')
})

test('website and command-filtered calendar expand the same phases without filling source gaps',()=>{
  const phases=event('阶段活动',{source_name:'官方',phases:[
    {start_at:'2026-10-14T00:00:00+08:00',end_at:'2026-10-16T00:00:00+08:00'},
    {start_at:'2026-10-18T00:00:00+08:00',end_at:'2026-10-19T00:00:00+08:00'},
  ]})
  const games=[{game_id:'nte',display_name:'异环'}]
  const collect=payload=>collectCalendarEvents(games,{nte:{events:{payload}}})
  const website=collect([phases]), qq=collect(selectQqEvents([phases],'calendar',now))
  assert.deepEqual(qq,website)
  assert.equal(website.length,2)
  assert.equal(eventGeometry(website[0],calendarRange(now)).end,Date.parse('2026-10-16T00:00:00+08:00'))
  assert.equal(eventGeometry(website[1],calendarRange(now)).start,Date.parse('2026-10-18T00:00:00+08:00'))
})
