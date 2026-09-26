import test from 'node:test'
import assert from 'node:assert/strict'
import { value, list, stamp } from './wuwa-display.js'

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
