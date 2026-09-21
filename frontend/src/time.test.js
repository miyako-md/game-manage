import test from 'node:test'
import assert from 'node:assert/strict'
import { displayBeijing, monthDay, resetLabel } from './time.js'

test('display uses Beijing for UTC timestamps across midnight and preserves missing values', () => {
  assert.equal(displayBeijing('2026-09-14T17:20:00Z'), '2026-09-15 01:20')
  assert.equal(monthDay('2026-09-14T17:20:00Z'), '09-15')
  assert.equal(displayBeijing(null), '未提供')
  assert.equal(displayBeijing('bad'), '未提供')
})
test('reset label distinguishes passed, later today, tomorrow, and unknown without rounding errors', () => {
  const now = Date.parse('2026-09-14T12:00:00Z')
  assert.equal(resetLabel('2026-09-14T11:59:00Z', now), '已可重置')
  assert.equal(resetLabel('2026-09-14T12:00:00Z', now), '已可重置')
  assert.equal(resetLabel('2026-09-14T14:00:00Z', now), '今日重置')
  assert.equal(resetLabel('2026-09-14T17:00:00Z', now), '明日重置')
  assert.equal(resetLabel('2026-09-16T17:00:00Z', now), '3 天后重置')
  assert.equal(resetLabel(null, now), null)
})
