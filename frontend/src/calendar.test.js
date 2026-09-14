import test from 'node:test'
import assert from 'node:assert/strict'
import { parseBeijingTime, formatBeijingDateTime, beijingDayStart, calendarRange, shiftCalendarAnchor, eventStatus, eventGeometry, collectCalendarEvents, groupCalendarEvents, safeSourceUrl } from './calendar.js'

const at = parseBeijingTime
test('dates consistently cross midnight in Beijing, independent of machine timezone', () => {
  assert.equal(formatBeijingDateTime('2026-09-13T16:30:00Z'), '2026-09-14 00:30')
  assert.equal(at('2026-09-14T00:30:00'), at('2026-09-13T16:30:00Z'))
  assert.equal(beijingDayStart(at('2026-09-13T17:00:00Z')), at('2026-09-14T00:00:00+08:00'))
  assert.equal(at('2026-02-30T10:00:00+08:00'), null)
  assert.equal(at('版本更新后'), null)
  assert.equal(formatBeijingDateTime(null), '未知')
})
test('an event ended one hour ago is ended, not zero days remaining', () => {
  const now = at('2026-09-14T12:00:00+08:00')
  assert.equal(eventStatus({ end_at: '2026-09-14T11:00:00+08:00' }, now), '已结束')
  assert.equal(eventStatus({ end_at: '2026-09-14T12:00:00+08:00' }, now), '已结束')
  assert.equal(eventStatus({ start_at: '2026-09-15', end_at: '2026-09-20' }, now), '未开始')
  assert.equal(eventStatus({ start_at: '2026-09-10' }, now), '截止未知')
})
test('month and fourteen-day ranges use exclusive Beijing midnight endpoints and navigate across years', () => {
  const range = calendarRange(at('2026-12-31T12:00:00+08:00'), 'month')
  assert.equal(range.start, at('2026-12-01'))
  assert.equal(range.end, at('2027-01-01'))
  assert.equal(range.days.length, 31)
  assert.equal(formatBeijingDateTime(shiftCalendarAnchor(range.start, 'month', 1)), '2027-01-01 00:00')
  assert.equal(calendarRange(at('2026-02-17'), 'month').days.length, 28)
  const fortnight = calendarRange(at('2026-09-14'), 'fortnight')
  assert.equal(fortnight.end - fortnight.start, 14 * 86400000)
  assert.equal(shiftCalendarAnchor(fortnight.start, 'fortnight', -1), at('2026-08-31'))
})
test('event geometry uses exact hours and clips both edges without changing source dates', () => {
  const range = { start: at('2026-09-14'), end: at('2026-09-16') }
  const partial = eventGeometry({ start_at: '2026-09-14T12:00:00+08:00', end_at: '2026-09-15' }, range)
  assert.equal(partial.left, 25)
  assert.equal(partial.width, 25)
  const clipped = eventGeometry({ start_at: '2026-09-13', end_at: '2026-09-17' }, range)
  assert.equal(clipped.left, 0)
  assert.equal(clipped.width, 100)
  assert.equal(clipped.clippedStart, true)
  assert.equal(clipped.clippedEnd, true)
  assert.equal(clipped.start, at('2026-09-13'))
  assert.equal(eventGeometry({ start_at: '2026-09-17', end_at: '2026-09-18' }, range).visible, false)
})
test('single known endpoint is only a marker, missing and invalid dates remain distinct', () => {
  const range = calendarRange(at('2026-09-14'), 'fortnight')
  const endOnly = eventGeometry({ end_at: '2026-09-15' }, range)
  assert.equal(endOnly.kind, 'point')
  assert.equal(endOnly.endpoint, 'end')
  assert.equal(endOnly.width, 0)
  assert.equal(endOnly.reason, '开始时间未知')
  assert.equal(eventGeometry({ start_at: '2026-09-15' }, range).reason, '截止时间未知')
  assert.equal(eventGeometry({}, range).kind, 'undated')
  assert.equal(eventGeometry({ start_at: '错误', end_at: '2026-09-15' }, range).kind, 'invalid')
  assert.equal(eventGeometry({ start_at: '2026-09-16', end_at: '2026-09-15' }, range).reason, '截止早于开始')
  assert.equal(eventGeometry({ start_at: '2026-09-15', end_at: '2026-09-15' }, range).kind, 'point')
})
test('filtering and grouping retain source metadata and empty games do not fabricate events', () => {
  const games = [{ game_id: 'nte', display_name: '异环' }, { game_id: 'lol', display_name: '英雄联盟' }]
  const snapshots = { nte: { events: { payload: [{ name: '开服', category: '活动', source_title: '公告', end_at: '2026-09-15' }], fetched_at: '2026-09-14', stale: true } } }
  const events = collectCalendarEvents(games, snapshots)
  assert.equal(events.length, 1)
  assert.equal(events[0].gameName, '异环')
  assert.equal(events[0].source_title, '公告')
  assert.equal(events[0].stale, true)
  assert.equal(collectCalendarEvents(games, snapshots, 'lol').length, 0)
  assert.equal(groupCalendarEvents(events)[0].events.length, 1)
  assert.equal(safeSourceUrl('javascript:alert(1)'), null)
  assert.equal(safeSourceUrl('12345'), null)
  assert.equal(safeSourceUrl('https://example.com/post'), 'https://example.com/post')
})
