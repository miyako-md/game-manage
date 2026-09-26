import test from 'node:test'
import assert from 'node:assert/strict'
import { value, list, stamp, sourceDateTime, starCount } from './wuwa-display.js'

test('unknown presentation never turns zero or false into missing data', () => {
  assert.equal(value(0), 0)
  assert.equal(value(false), '否')
  assert.equal(value(null), '未知')
  assert.deepEqual(list([null, 0, false, { num: null }]), [
    0,
    false,
    { num: null },
  ])
  assert.deepEqual(list({ length: 1 }), [])
})
test('date presentation crosses Beijing midnight and safely handles invalid numeric dates', () => {
  assert.match(stamp('2026-09-16T20:00:00Z'), /2026-09-17.*04:00/)
  assert.match(stamp(0), /1970-01-01.*08:00/)
  for (const date of [null, undefined, '', NaN, Infinity, 1e30, 'not-a-date'])
    assert.equal(stamp(date), '未知')
})

test('stamp shows numbers outside four-digit years as unknown', () => {
  assert.equal(stamp(1.7e15), '未知')
  assert.equal(stamp(-6e13), '未知')
  assert.equal(stamp(253402300800000), '未知')
})

test('source date-times read as Beijing wall time and everything else passes through as null', () => {
  assert.equal(sourceDateTime('2026-09-26 20:30:00'), stamp('2026-09-26 20:30:00'))
  assert.notEqual(sourceDateTime('2026-09-26T12:30:00Z'), null)
  for (const v of ['2026-09-26', 'soon', 20260926, null, '2026-13-40 99:99']) assert.equal(sourceDateTime(v), null, String(v))
})

test('star counts are whole numbers from one to six', () => {
  assert.equal(starCount(5), 5)
  assert.equal(starCount('4'), 4)
  for (const v of [0, 7, 4.5, null, undefined, 'x', -1]) assert.equal(starCount(v), 0, String(v))
})
