import test from 'node:test'
import assert from 'node:assert/strict'
import { calendarRange } from './calendar.js'
import { eventBoundaryText, eventEndpoint, normalizeQqEvents, qqEventGeometry, qqEventStatus, selectQqEvents } from './qq-event-selection.js'

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
  const normalized=normalizeQqEvents([source,source])
  assert.deepEqual(names(normalized),['阶段活动 · 阶段 1','阶段活动 · 阶段 2'])
  assert.ok(normalized.every(row=>row.source_name==='官方' && !('phases' in row)))
  assert.deepEqual(names(selectQqEvents([source],'events',now)),['阶段活动 · 阶段 2'])
  assert.equal(source.phases.length,2)
})

test('uncertain event rows never become current intervals or fabricated midnight countdowns',()=>{
  const range=calendarRange(now,'rolling')
  const row=event('日精度',{start_at:'2026-10-14T00:00:00+08:00',start_precision:'day'})
  const geometry=qqEventGeometry(row,range,'events')
  assert.equal(geometry.kind,'undated')
  assert.equal(qqEventStatus(row,now,geometry),'时间待确认')
  assert.match(geometry.reason,/2026-10-14 · 时刻未确认/)
  assert.doesNotMatch(eventBoundaryText(row,'start'),/00:00/)
})

test('rolling calendar draws day coverage inclusively while keeping its time uncertain',()=>{
  const row={name:'日期范围',start_date:'2026-10-14',end_date:'2026-10-16',start_precision:'day',end_precision:'day'}
  const range=calendarRange(now,'rolling'),geometry=qqEventGeometry(row,range,'calendar')
  assert.equal(geometry.kind,'range')
  assert.equal(geometry.end,Date.parse('2026-10-17T00:00:00+08:00'))
  assert.equal(qqEventStatus(row,now,geometry),'时间待确认')
  assert.equal(selectQqEvents([row],'calendar',now).length,1)
  const relative={...row,start_precision:'relative',start_text:'维护完成后'}
  assert.equal(qqEventGeometry(relative,range,'calendar').kind,'undated')
})
