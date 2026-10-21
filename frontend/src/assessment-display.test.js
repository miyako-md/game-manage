import test from 'node:test'
import assert from 'node:assert/strict'
import { attributionLabel, echoBadges, gradeLabel, isDefaultScore } from './assessment-display.js'

test('grades read upper case and only the six known grades are shown', () => {
  assert.deepEqual(['c', 'b', 'a', 's', 'ss', 'sss', 'SS'].map(gradeLabel), ['C', 'B', 'A', 'S', 'SS', 'SSS', 'SS'])
  for (const grade of [null, undefined, '', 'x', 'ssss', 3]) assert.equal(gradeLabel(grade), '')
})

test('only a default score carries an attribution', () => {
  assert.equal(attributionLabel({ origin: 'builtin_default', attribution: 'gpl_snapshot' }), '权重改编自 WutheringWavesUID（GPL-3.0）')
  assert.equal(attributionLabel({ origin: 'builtin_default', attribution: 'self_made' }), '自制权重')
  assert.equal(attributionLabel({ origin: 'builtin_default', attribution: null }), '')
  assert.equal(attributionLabel({ origin: 'user_configured', attribution: 'gpl_snapshot' }), '')
  assert.equal(isDefaultScore(null), false)
})

test('echo badges follow the source position, skip unscorable items and a different echo at that position', () => {
  const echoes = [{ phantom_prop: { phantom_id: 7 } }, null, { phantom_prop: {} }, { phantom_prop: { phantom_id: 9 } }]
  const item = (item_id, extra = {}) => ({ item_id, status: 'scored', value: '30.05', grade: 'a', max_value: 50, ...extra })
  const badges = echoBadges({ origin: 'builtin_default', item_results: [
    item('echo:0:7', { grade: 'sss' }), item('echo:2:unknown'), item('echo:3:8'),
    item('echo:1:unknown'), item('echo:9:unknown'), { item_id: 'echo:3:unknown', status: 'unscorable', value: null, max_value: null },
  ] }, echoes)
  assert.deepEqual([...badges].map(([echo, badge]) => [echoes.indexOf(echo), badge]), [[0, { value: '30.05', grade: 'SSS' }], [2, { value: '30.05', grade: 'A' }]])
  assert.equal(echoBadges({ origin: 'user_configured', item_results: [item('echo:0:7', { grade: null, max_value: null })] }, echoes).size, 0)
  assert.equal(echoBadges(null, echoes).size, 0)
})
