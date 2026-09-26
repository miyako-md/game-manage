import test from 'node:test'
import assert from 'node:assert/strict'
import { parseBeijingTime, formatBeijingDateTime, beijingDayStart, calendarRange, shiftCalendarAnchor, eventStatus, eventGeometry, collectCalendarEvents, groupCalendarEvents, safeUrl } from './calendar.js'

const at = parseBeijingTime
test('relative starts use date geometry without claiming midnight is the opening time', () => {
  const e = { start_at: null, start_date: '2026-08-20', start_text: '3.6版本更新后', end_at: '2026-09-29T03:59:00+08:00' }
  const geometry = eventGeometry(e, calendarRange(at('2026-09-16'), 'rolling'))
  assert.equal(geometry.kind, 'range')
  assert.equal(geometry.approximateStart, true)
  assert.equal(e.start_at, null)
  assert.equal(eventStatus(e, at('2026-08-20T08:00:00+08:00')), '更新后开放')
  assert.equal(eventStatus(e, at('2026-09-16')), '进行中')
})
test('rolling view starts three days before today and shifts thirty days without drifting', () => {
  const anchor = at('2026-12-31T23:00:00+08:00')
  const range = calendarRange(anchor, 'rolling')
  assert.equal(range.start, at('2026-12-28'))
  assert.equal(range.end, at('2027-01-27'))
  assert.equal(range.days.length, 30)
  assert.equal(range.days[3].timestamp, beijingDayStart(anchor))
  const next = shiftCalendarAnchor(anchor, 'rolling', 1)
  assert.equal(calendarRange(next, 'rolling').start, at('2027-01-27'))
  assert.equal(calendarRange(shiftCalendarAnchor(next, 'rolling', -1), 'rolling').start, range.start)
})
test('different activity types share one game group while preserving their row metadata', () => {
  const events = [
    { gameId: 'nte', gameName: '异环', category: '签到', name: '活动一' },
    { gameId: 'lol', gameName: '英雄联盟', category: '比赛', name: '活动二' },
    { gameId: 'nte', gameName: '异环', category: '卡池', name: '活动三' },
  ]
  const groups = groupCalendarEvents(events)
  assert.equal(groups.length, 2)
  assert.deepEqual(groups[0].events, [events[0], events[2]])
  assert.equal(groups[1].gameId, 'lol')
})
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
})

test('safeUrl keeps http(s) URLs and rejects script schemes, credentials and relative references', () => {
  for (const url of ['javascript:alert(1)', 'data:image/png;base64,AA==', '/image.png', '//example.com/image.png',
    'https://user:secret@example.com/a', '12345', null])
    assert.equal(safeUrl(url), null)
  assert.equal(safeUrl('https://example.com/post'), 'https://example.com/post')
})

test('formatBeijingDateTime rejects timestamps outside four-digit years', () => {
  assert.equal(formatBeijingDateTime(1.7e15), '未知')
  assert.equal(formatBeijingDateTime(-6e13), '未知')
  assert.equal(formatBeijingDateTime(-62135596800000), '未知')
  assert.equal(formatBeijingDateTime(253402300800000), '未知')
  assert.equal(formatBeijingDateTime(Date.UTC(2026, 8, 24, 2, 0)), '2026-09-24 10:00')
})
