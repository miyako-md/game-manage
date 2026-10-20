import test from 'node:test'
import assert from 'node:assert/strict'
import { eventGeometry, eventStatus, versionCalendarRange } from './calendar.js'

import { beijingRange } from './test-utils/calendar.js'

test('an explicit permanent opening remains visible after its start without fabricating an end', () => {
  const event = { start_date:'2026-09-30', start_precision:'relative', permanent:true, end_precision:'permanent' }
  const range = beijingRange('2026-10-12', '2026-11-11')
  const geometry = eventGeometry(event, range)
  assert.equal(geometry.kind, 'range')
  assert.equal(geometry.visible, true)
  assert.equal(geometry.left, 0)
  assert.equal(geometry.width, 100)
  assert.equal(geometry.end, null)
  assert.equal(eventStatus(event, Date.parse('2026-10-15T08:00:00+08:00')), '常驻开放')
})

test('a date-only deadline stays on its known day in the full version grid', () => {
  const event = { end_date:'2027-02-05', end_precision:'day' }
  const range = versionCalendarRange([event], Date.parse('2027-01-01T08:00:00+08:00'))
  assert.equal(range.days.length, 1)
  const geometry = eventGeometry(event, range)
  assert.equal(geometry.visible, true)
  assert.equal(geometry.kind, 'point')
  assert.equal(geometry.left, 0)
})
